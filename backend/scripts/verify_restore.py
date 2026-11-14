"""恢复演练对账工具（只读）：比对恢复后的 Mongo 实例与备份 manifest。

配套 scripts/backup_mongodb.py 产出的 manifest
（format=rehab-mongodb-backup-manifest-v1）。恢复演练流程见
docs/backup-restore-plan.md：隔离环境 mongorestore 后，用本工具对账。

对账项（全部只读：list / count / find / list_indexes，绝不写库）：
- 数据库存在性：manifest 记录的每个用户库在恢复实例上必须存在；
- 集合存在性与文档数逐一比对（count_documents({})）；
- 索引抽查：manifest 记录的每个索引名在恢复实例上必须存在（只比名字，
  不比参数；mongorestore 重建索引参数以 dump 内容为准）；
- patient_domain_state 单例（patients/repository.py:20-22）：manifest 记录
  存在则恢复实例必须存在且 mode 一致；manifest 记录不存在则恢复实例也不应
  出现（出现说明恢复到了错误时点/错误库）；
- 恢复实例上多出的集合只记入 extra_collections 信息段，不算失败（可能是
  恢复目标库的本地残留），由人工判断。

输出：JSON 对账报告到 stdout（ok 字段为总体结论），人类可读摘要到 stderr。
退出码：0 无差异；1 有差异（差异明细见 differences）。
连接串经 --uri 或 MONGODB_VERIFY_URI 提供；主机闸门与备份工具同口径，
缺省仅允许本机（演练恢复实例通常就是本机临时容器）。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit

from scripts.backup_mongodb import (
    DEFAULT_URI,
    MANIFEST_FORMAT,
    STATE_COLLECTION,
    STATE_ID,
    check_host_allowed,
    mask_uri,
)

REPORT_FORMAT = "rehab-restore-verification-report-v1"


def connect_client(uri):
    """对账连接（只读操作）；测试打桩点。"""
    from pymongo import MongoClient
    return MongoClient(uri, serverSelectionTimeoutMS=10000)


def _collection_diff(manifest_info, actual_count, actual_indexes):
    """单个集合的比对：返回 (differences 列表, 实际索引名集合)。"""
    differences = []
    if manifest_info["count"] != actual_count:
        differences.append({
            "type": "count_mismatch",
            "expected": manifest_info["count"],
            "actual": actual_count,
        })
    missing = sorted(set(manifest_info.get("indexes", [])) - set(actual_indexes))
    for name in missing:
        differences.append({
            "type": "missing_index",
            "expected": name,
            "actual": None,
        })
    return differences


def verify_against_manifest(manifest, client):
    """比对 manifest 与恢复实例（client 为已连接的 Mongo client，只读使用）。"""
    report = {
        "format": REPORT_FORMAT,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest_format": manifest.get("format"),
        "manifest_created_at": manifest.get("created_at"),
        "ok": True,
        "differences": [],
        "extra_collections": [],
        "checked": {"databases": 0, "collections": 0, "indexes": 0},
    }
    if manifest.get("format") != MANIFEST_FORMAT:
        report["differences"].append({
            "type": "unsupported_manifest_format",
            "database": None,
            "collection": None,
            "expected": MANIFEST_FORMAT,
            "actual": manifest.get("format"),
        })
        report["ok"] = False
        return report

    live_databases = set(client.list_database_names())
    for db_name, db_info in sorted(manifest.get("databases", {}).items()):
        report["checked"]["databases"] += 1
        if db_name not in live_databases:
            report["differences"].append({
                "type": "missing_database",
                "database": db_name,
                "collection": None,
                "expected": "present",
                "actual": "missing",
            })
            continue
        db = client[db_name]
        live_collections = set(db.list_collection_names())
        for coll_name, coll_info in sorted(db_info.get("collections", {}).items()):
            report["checked"]["collections"] += 1
            report["checked"]["indexes"] += len(coll_info.get("indexes", []))
            if coll_name not in live_collections:
                report["differences"].append({
                    "type": "missing_collection",
                    "database": db_name,
                    "collection": coll_name,
                    "expected": coll_info["count"],
                    "actual": "missing",
                })
                continue
            collection = db[coll_name]
            actual_indexes = sorted(index["name"] for index in collection.list_indexes())
            for difference in _collection_diff(coll_info,
                                               collection.count_documents({}),
                                               actual_indexes):
                difference.update({"database": db_name, "collection": coll_name})
                report["differences"].append(difference)
        # patient_domain_state 由下方专项对账，不算「多出的集合」
        extra = sorted(live_collections - set(db_info.get("collections", {}))
                       - {STATE_COLLECTION})
        for coll_name in extra:
            report["extra_collections"].append({"database": db_name, "collection": coll_name})

    expected_state = manifest.get("patient_domain_state") or {"present": False, "mode": None}
    actual_state = {"present": False, "mode": None}
    for db_name in sorted(live_databases):
        if STATE_COLLECTION in set(client[db_name].list_collection_names()):
            doc = client[db_name][STATE_COLLECTION].find_one({"_id": STATE_ID})
            if doc:
                actual_state = {"present": True, "mode": doc.get("mode")}
                break
    if expected_state.get("present") != actual_state["present"] or (
            actual_state["present"] and expected_state.get("mode") != actual_state["mode"]):
        report["differences"].append({
            "type": "patient_domain_state_mismatch",
            "database": None,
            "collection": STATE_COLLECTION,
            "expected": expected_state,
            "actual": actual_state,
        })

    if report["differences"]:
        report["ok"] = False
    return report


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="恢复演练对账（只读；比对恢复实例与备份 manifest）")
    parser.add_argument("--manifest", type=open, required=True,
                        help="备份 manifest JSON 文件路径")
    parser.add_argument("--uri", default=os.environ.get("MONGODB_VERIFY_URI") or DEFAULT_URI,
                        help="恢复后的 Mongo 连接串；缺省 MONGODB_VERIFY_URI，再缺省本机")
    parser.add_argument("--allow-remote", action="store_true",
                        help="允许对账非本机实例（缺省仅 localhost）")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    uri = args.uri
    check_host_allowed(uri, args.allow_remote)
    manifest = json.load(args.manifest)
    client = connect_client(uri)
    try:
        report = verify_against_manifest(manifest, client)
    finally:
        client.close()
    report["target_uri_masked"] = mask_uri(uri)
    if report["ok"]:
        print(f"对账通过: {report['checked']['databases']} 库 / "
              f"{report['checked']['collections']} 集合 / "
              f"{report['checked']['indexes']} 索引全部一致", file=sys.stderr)
    else:
        for difference in report["differences"]:
            print(f"差异: {difference.get('database')}.{difference.get('collection')} "
                  f"{difference['type']} 期望={difference['expected']} 实际={difference['actual']}",
                  file=sys.stderr)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
