"""MongoDB 全库备份包装工具（mongodump --gzip --archive + manifest 清单）。

定位（docs/backup-restore-plan.md）：业务 JSON 导出（app/operations/data_export.py，
由 runtime.backup_schedule 定时落盘）只是「字段与条数有限、不可恢复」的业务层
归档；数据库恢复的唯一依据是本工具产出的 mongodump archive + manifest 清单。
本工具是 mongodump 的薄包装：不实现任何备份协议本身，只负责
  1) 参数化 URI 并做主机闸门（缺省仅允许 localhost / 127.0.0.1 / ::1）；
  2) 组装并执行 mongodump 子进程（--gzip --archive 单文件归档）；
  3) 备份完成后经 Mongo 只读连接采集 manifest：Mongo 版本、各库各集合文档数、
     索引名清单、patient_domain_state 单例状态（恢复对账的基准）；
  4) 全程不把连接串明文写进日志/manifest（统一经 mask_uri / mask_text 掩码）。

副本集一致性：deploy/mongodb 是单节点副本集 rehab_rs。--oplog 时 mongodump
追加捕获备份窗口期 oplog，得到时间点一致快照；单机（非副本集）实例不可用
--oplog。副本集建议优先在 secondary 上执行，减轻 primary 压力。

安全边界：
- 连接串经命令行 --uri 传入会出现在进程列表（ps）里；受控本机环境可接受，
  更严格场景应改用 mongodump 支持的配置文件方式并自行处置权限；
- manifest 只含计数/索引名/库名等元数据，不含任何文档内容；但库名集合名
  本身即部署信息，manifest 与 archive 同级存放、同等加密保管。

用法（backend/ 目录下）：
    .venv/bin/python -m scripts.backup_mongodb
    MONGODB_BACKUP_URI="mongodb://127.0.0.1:37021/?replicaSet=rehab_rs&directConnection=true" \
        .venv/bin/python -m scripts.backup_mongodb --oplog
    .venv/bin/python -m scripts.backup_mongodb --uri mongodb://somehost:27017 --allow-remote

退出码：0 成功；1 失败（主机闸门 / mongodump 非零退出 / 归档缺失）；
argparse 参数错误为 2。manifest JSON 同时打印到 stdout（末段），
人类可读摘要到 stderr。
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

MANIFEST_FORMAT = "rehab-mongodb-backup-manifest-v1"
DEFAULT_URI = "mongodb://127.0.0.1:27017"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "mongodb-backups"
# manifest 里对账所需的 patient_domain_state 单例（patients/repository.py:20-22）
STATE_COLLECTION = "patient_domain_state"
STATE_ID = "clinical-patients-v1"
# 系统库不进 manifest（admin/config/local 的内容随 mongodump 全量，但对账
# 无业务意义，且 local.oplog 巨大且时效性强）
SYSTEM_DATABASES = {"admin", "config", "local"}
_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"}

# 匹配 mongodb(+srv)://user:pass@ 的 userinfo 段；掩码后保留主机/端口/库/参数
_CRED_PATTERN = re.compile(r"(//)[^@/\s]+(@)")


def mask_uri(uri):
    """掩去连接串 userinfo（用户名:密码），保留其余部分。"""
    return _CRED_PATTERN.sub(r"\1***\2", uri or "")


def mask_text(text):
    """对任意工具输出做连接串掩码（mongodump 输出可能回显 URI）。"""
    return _CRED_PATTERN.sub(r"\1***\2", text or "")


def check_host_allowed(uri, allow_remote):
    """主机闸门：缺省仅允许本机（与 patient_reference_audit 同一口径）。"""
    host = (urlsplit(uri).hostname or "").lower()
    if not host:
        raise SystemExit("无法从连接串解析主机名；请检查 --uri / MONGODB_BACKUP_URI")
    if host not in _ALLOWED_HOSTS and not allow_remote:
        raise SystemExit(
            f"目标主机 {host} 不在 localhost 白名单内；备份缺省仅允许本机。"
            "确需备份远程实例请显式加 --allow-remote。")


def build_command(uri, archive_path, mongodump_bin="mongodump", oplog=False):
    """组装 mongodump 命令行。archive 单文件 + gzip；oplog 为时间点一致性。"""
    command = [mongodump_bin, "--uri", uri, "--gzip", f"--archive={archive_path}"]
    if oplog:
        command.append("--oplog")
    return command


def connect_client(uri):
    """备份完成后的 manifest 采集连接（只读操作）；测试打桩点。"""
    from pymongo import MongoClient
    return MongoClient(uri, serverSelectionTimeoutMS=10000)


def snapshot_client(client):
    """只读采集 manifest 快照：版本、拓扑、各用户库集合计数与索引名。

    只执行 buildInfo / hello / list / count / list_indexes，绝不写库。
    """
    info = client.admin.command("buildInfo")
    hello = client.admin.command("hello")
    databases = {}
    state_present = False
    state_mode = None
    for db_name in sorted(client.list_database_names()):
        if db_name in SYSTEM_DATABASES:
            continue
        db = client[db_name]
        collections = {}
        for coll_name in sorted(db.list_collection_names()):
            collection = db[coll_name]
            collections[coll_name] = {
                "count": collection.count_documents({}),
                "indexes": sorted(index["name"] for index in collection.list_indexes()),
            }
            if coll_name == STATE_COLLECTION and state_present is False:
                doc = collection.find_one({"_id": STATE_ID})
                if doc:
                    state_present = True
                    state_mode = doc.get("mode")
        databases[db_name] = {"collections": collections}
    return {
        "mongo_version": info.get("version"),
        "topology": {"replica_set": hello.get("setName")},
        "databases": databases,
        "patient_domain_state": {"present": state_present, "mode": state_mode},
    }


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="MongoDB 全库备份（mongodump 包装 + manifest 清单）")
    parser.add_argument("--uri", default=os.environ.get("MONGODB_BACKUP_URI") or DEFAULT_URI,
                        help="Mongo 连接串；缺省 MONGODB_BACKUP_URI 环境变量，再缺省本机")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help="archive 与 manifest 输出目录")
    parser.add_argument("--mongodump", dest="mongodump_bin", default="mongodump",
                        help="mongodump 可执行文件路径")
    parser.add_argument("--oplog", action="store_true",
                        help="副本集上捕获 oplog，得到时间点一致快照")
    parser.add_argument("--allow-remote", action="store_true",
                        help="允许备份非本机实例（缺省仅 localhost）")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    check_host_allowed(args.uri, args.allow_remote)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = args.output_dir / f"rehab-mongodb-{stamp}.archive.gz"
    manifest_path = args.output_dir / f"rehab-mongodb-{stamp}.manifest.json"

    # 连接串会出现在 argv 里（进程列表可见），所以绝不打印完整命令行
    command = build_command(args.uri, archive_path, args.mongodump_bin, oplog=args.oplog)
    print(f"执行 mongodump -> {archive_path}（uri 已掩码: {mask_uri(args.uri)}）", file=sys.stderr)
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        # 输出内容先过掩码再上日志，防 mongodump 回显连接串
        print(mask_text(completed.stderr)[-2000:], file=sys.stderr)
        # mongodump 中途失败（如源库断连）可能留下半成品归档，必须删除，
        # 否则会被误当作可用备份（与 manifest 一一对应，缺 manifest 即无效）
        archive_path.unlink(missing_ok=True)
        raise SystemExit(f"mongodump 失败（退出码 {completed.returncode}），未生成 manifest")
    if not archive_path.is_file():
        raise SystemExit(f"mongodump 报告成功但归档文件不存在: {archive_path}")

    client = connect_client(args.uri)
    try:
        snapshot = snapshot_client(client)
    finally:
        client.close()

    manifest = {
        "format": MANIFEST_FORMAT,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "archive_file": archive_path.name,
        "archive_size_bytes": archive_path.stat().st_size,
        "archive_sha256": sha256_file(archive_path),
        "source_uri_masked": mask_uri(args.uri),
        "oplog_captured": bool(args.oplog),
        "manifest_note": "manifest 只含元数据（计数/索引名），不含任何文档内容",
        **snapshot,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    total_docs = sum(c["count"] for db in manifest["databases"].values() for c in db["collections"].values())
    print(f"备份完成: {archive_path}（{manifest['archive_size_bytes']} 字节, "
          f"{len(manifest['databases'])} 个库, {total_docs} 条文档）", file=sys.stderr)
    print(f"manifest: {manifest_path}", file=sys.stderr)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


if __name__ == "__main__":
    main()
