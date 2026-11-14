"""标签（tags 集合）唯一性只读盘点工具（§14 工程基线缺口）。

盘什么：
  标签字典集合 `tags`（app/directory/records.py 读写，前端经
  GET/POST /api/admin/tags 消费）在业务唯一键 (name, category) 上的
  重复键组，以及会影响唯一索引实施的异常形状（name/category 缺失、
  null、未 strip、超长），另附带盘点业务集合对标签名的软引用悬空。

为什么盘：标签创建目前「先查重再插入」（records.create_tag 的
  find_one + insert_one），查重与插入之间存在竞态，并发可产生重复；
  §14 明确「需先盘点历史数据和确定迁移方案，再实施约束，不应直接对
  未知现有数据建唯一索引」。本工具是实施唯一索引前的第一步——只产出
  事实清单，不产出清理决策，也绝不写库。

本工具只读：仅执行 find / to_list 游标读取，绝不 insert / update /
delete / create_index / drop。连接串经 --uri 参数或 MONGODB_AUDIT_URI
（缺省回退 MONGODB_URL）环境变量提供；缺省只允许连接
localhost / 127.0.0.1 / ::1，连远程实例必须显式加 --allow-remote
（虽然本工具不写，仍做主机闸门）。惯例与 scripts/patient_reference_audit.py
一致。

运行方式（在 backend/ 目录下）：
    MONGODB_AUDIT_URI="mongodb://localhost:27017" \
        .venv/bin/python -m scripts.label_uniqueness_audit > audit.json
    .venv/bin/python -m scripts.label_uniqueness_audit \
        --uri mongodb://localhost:27017 --db rehabman --batch-size 2000 \
        > audit.json

输出：JSON 报告写 stdout（可重定向），人类可读摘要写 stderr。

输出字段含义（JSON 顶层）：
  generated_at          ISO8601 生成时间
  database              盘点的库名
  batch_size            游标分批大小
  tags                  标签集合本体盘点段
    unique_key          业务唯一键说明（["name", "category"]）
    total_documents     集合内扫描到的文档总数
    missing_name / missing_category   字段键不存在的文档数
    null_name / null_category         字段存在但值为 null 的文档数
    blank_name / blank_category       值 strip 后为空的文档数（创建路径
                                      拒绝空名，属历史异常形状）
    unstripped          name 或 category 存在首尾空白的文档数（创建路径
                        落库前 strip，未 strip 值属历史异常形状）
    overlength_name / overlength_category   值长度超过 40 的文档数
                        （创建路径上限 40；不影响索引，仅事实记录）
    duplicate_key_groups  同 (name, category) 键多文档组数。归组按索引
                        语义：missing 与 null 同视为 null 键（MongoDB
                        唯一索引对缺失字段按 null 处理，两者会互撞）
    duplicate_documents   重复组覆盖的文档总数
    duplicate_examples    重复组样本（默认最多 20 组）：{"name",
                        "category", "ids"}（各文档 _id 字符串）
    examples_truncated   样本是否被截断
  references            软引用悬空段（标签无外键，业务集合仅按 name
                        字符串引用；无引用约束，此段仅为信息性对照）
    health_records / organizations（每个来源一段）
      field             引用字段名（tags，字符串数组）
      documents_with_field  tags 字段为非空列表的文档数
      tag_entries       引用条目（数组元素）总数
      other_form_entries  非字符串形态条目数（不参与悬空判定）
      dangling_name     条目值不在 tags 集合任何标签 name 中的条目数
                        （按原文精确匹配，与业务读取语义一致）
      dangling_examples 悬空样本（去重，默认最多 20 条）
      examples_truncated 样本是否被截断
  notes                 口径备注

唯一索引实施口径（详见 docs/tag-uniqueness-plan.md）：本报告仅为
「维护窗口手工建索引」前的清零依据——duplicate/异常形状计数须先经业务
清理归零，再手工建唯一索引；索引不进应用启动路径（app/db/indexes.py
不登记）。

本工具只产出事实清单，不做任何迁移/修复决策；清理方案须另行制定并经业务确认。
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit

BATCH_SIZE_DEFAULT = 1000
MAX_EXAMPLES_DEFAULT = 20

# 业务唯一键：与 app/directory/records.create_tag 的查重查询
# {"name": name, "category": category} 完全同口径（原文精确匹配，
# 无大小写折叠、无 collation）。唯一索引必须保持默认 binary collation，
# 否则应用层查重与数据库唯一性判定会分叉。
UNIQUE_KEY_FIELDS = ("name", "category")
UNIQUE_KEY_NAME = "uniq_tag_name_category"

# 对标签名做软引用的业务集合与字段（均为字符串数组，无外键约束）。
# - health_records.tags：健康档案自由标签（app/schemas/health_record.py:172）；
# - organizations.tags：机构导入模型的标签（app/schemas/user.py:207）。
# 两者均为自由字符串，悬空仅代表「不在当前标签字典中」，是事实对照
# 而非外键违规；name 匹配不含 category 维度（引用侧只有一维字符串）。
REFERENCE_SOURCES = (
    ("health_records", "tags"),
    ("organizations", "tags"),
)

_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"}

NAME_MAX_LENGTH = 40


_MISSING_DISPLAY = "<missing>"
_OTHER_DISPLAY = "<other>"


def normalize_group_key(doc):
    """按索引语义取 (name, category) 组键：缺失与 null 等价（MongoDB 唯一
    索引对缺失字段按 null 归组，两者会互撞）；其余形态按原值参与归组，
    不可哈希的值（历史脏数据）统一归入 "<other>" 占位组，避免崩溃。"""
    parts = []
    for field in UNIQUE_KEY_FIELDS:
        value = doc.get(field)
        try:
            hash(value)
        except TypeError:
            value = _OTHER_DISPLAY
        parts.append(value)
    return tuple(parts)


def display_key_part(value):
    """样本展示：null/缺失键以占位符呈现，其余按原值。"""
    return _MISSING_DISPLAY if value is None else value


async def iter_batches(cursor, batch_size):
    """游标分批拉取；内存占用只与 batch_size 相关，不随集合大小线性膨胀。"""
    while True:
        batch = await cursor.to_list(length=batch_size)
        if not batch:
            return
        for doc in batch:
            yield doc


async def audit_tags_collection(db, batch_size, max_examples):
    """tags 集合本体：异常形状计数 + 同 (name, category) 键重复组清单。"""
    stats = {
        "unique_key": list(UNIQUE_KEY_FIELDS),
        "total_documents": 0,
        "missing_name": 0,
        "missing_category": 0,
        "null_name": 0,
        "null_category": 0,
        "blank_name": 0,
        "blank_category": 0,
        "unstripped": 0,
        "overlength_name": 0,
        "overlength_category": 0,
        "duplicate_key_groups": 0,
        "duplicate_documents": 0,
        "duplicate_examples": [],
        "examples_truncated": False,
    }
    groups = {}  # (name, category) -> [str(_id) ...]，只收重复键
    name_values = set()
    cursor = db["tags"].find({}, None)
    async for doc in iter_batches(cursor, batch_size):
        stats["total_documents"] += 1
        for field in UNIQUE_KEY_FIELDS:
            if field not in doc:
                stats[f"missing_{field}"] += 1
            elif doc[field] is None:
                stats[f"null_{field}"] += 1
            elif isinstance(doc[field], str):
                value = doc[field]
                if value != value.strip():
                    stats["unstripped"] += 1
                if not value.strip():
                    stats[f"blank_{field}"] += 1
                if len(value) > NAME_MAX_LENGTH:
                    stats[f"overlength_{field}"] += 1
        name = doc.get("name")
        if isinstance(name, str):
            name_values.add(name)
        groups.setdefault(normalize_group_key(doc), []).append(str(doc["_id"]))
    duplicates = {key: ids for key, ids in groups.items() if len(ids) > 1}
    stats["duplicate_key_groups"] = len(duplicates)
    stats["duplicate_documents"] = sum(len(ids) for ids in duplicates.values())
    for key, ids in list(sorted(duplicates.items(), key=lambda kv: str(kv[0])))[:max_examples]:
        stats["duplicate_examples"].append(
            {"name": display_key_part(key[0]),
             "category": display_key_part(key[1]), "ids": ids})
    if len(duplicates) > max_examples:
        stats["examples_truncated"] = True
    return stats, name_values


def new_reference_stats(field):
    return {
        "field": field,
        "documents_with_field": 0,
        "tag_entries": 0,
        "other_form_entries": 0,
        "dangling_name": 0,
        "dangling_examples": [],
        "examples_truncated": False,
    }


async def audit_reference_collection(db, collection_name, field, name_values,
                                     batch_size, max_examples):
    """软引用悬空盘点：条目值不在标签字典 name 中的计数与样本。"""
    stats = new_reference_stats(field)
    reported = set()
    cursor = db[collection_name].find({}, None)
    async for doc in iter_batches(cursor, batch_size):
        entries = doc.get(field)
        if not isinstance(entries, list) or not entries:
            continue
        stats["documents_with_field"] += 1
        for entry in entries:
            stats["tag_entries"] += 1
            if not isinstance(entry, str):
                stats["other_form_entries"] += 1
                continue
            if entry in name_values:
                continue
            stats["dangling_name"] += 1
            if entry not in reported:
                reported.add(entry)
                if len(stats["dangling_examples"]) < max_examples:
                    stats["dangling_examples"].append(entry)
                else:
                    stats["examples_truncated"] = True
    return stats


async def audit_database(db, *, batch_size=BATCH_SIZE_DEFAULT,
                         max_examples=MAX_EXAMPLES_DEFAULT):
    tags_stats, name_values = await audit_tags_collection(
        db, batch_size, max_examples)
    references = {}
    for collection_name, field in REFERENCE_SOURCES:
        references[collection_name] = await audit_reference_collection(
            db, collection_name, field, name_values, batch_size, max_examples)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database": getattr(db, "name", "<unknown>"),
        "batch_size": batch_size,
        "tags": tags_stats,
        "references": references,
        "notes": [
            "业务唯一键为 (name, category)，与 app/directory.records."
            "create_tag 的查重查询同口径：原文精确匹配、无大小写折叠；"
            f"建议唯一索引名为 {UNIQUE_KEY_NAME}，保持默认 collation。",
            "组键按索引语义归并：name/category 缺失与 null 同视为 null，"
            "会在唯一索引上互撞；missing/null/blank/unstripped/overlength "
            "均为建索引前须人工处置的异常形状计数。",
            "references 为软引用对照：业务集合仅按标签 name 一维字符串引用，"
            "无外键约束；dangling_name 只代表「不在当前标签字典中」，"
            "不是违规计数。",
            "本报告仅为事实盘点，不产出清理决策；实施顺序见 "
            "docs/tag-uniqueness-plan.md（盘点清零 → 维护窗口手工建唯一"
            "索引 → 应用层 11000 兜底）。索引不进应用启动路径。",
        ],
    }


def render_summary(report):
    tags = report["tags"]
    lines = [f"标签唯一性盘点 {report['database']} @ {report['generated_at']}"]
    lines.append(
        f"tags 文档总数 {tags['total_documents']}；"
        f"missing(name/category) {tags['missing_name']}/{tags['missing_category']}，"
        f"null {tags['null_name']}/{tags['null_category']}，"
        f"blank {tags['blank_name']}/{tags['blank_category']}，"
        f"unstripped {tags['unstripped']}，"
        f"overlength {tags['overlength_name']}/{tags['overlength_category']}")
    lines.append(
        f"重复键组 {tags['duplicate_key_groups']} 组，覆盖文档 "
        f"{tags['duplicate_documents']} 个")
    for example in tags["duplicate_examples"]:
        lines.append(
            f"  ({example['name']!r}, {example['category']!r}): "
            f"{len(example['ids'])} 个 -> {example['ids']}")
    for collection, stats in report["references"].items():
        lines.append(
            f"{collection}.{stats['field']}: 文档 {stats['documents_with_field']}，"
            f"条目 {stats['tag_entries']}（other 形态 {stats['other_form_entries']}），"
            f"悬空名 {stats['dangling_name']}")
    return "\n".join(lines)


def check_host_allowed(uri, allow_remote):
    host = (urlsplit(uri).hostname or "").lower()
    if not host:
        raise SystemExit("无法从连接串解析主机名；请检查 --uri / MONGODB_AUDIT_URI")
    if host not in _ALLOWED_HOSTS and not allow_remote:
        raise SystemExit(
            f"目标主机 {host} 不在 localhost 白名单内；本工具默认仅允许本机。"
            "确需连远程实例请显式加 --allow-remote（工具仍只读）。")


async def run(uri, db_name, batch_size, max_examples, allow_remote):
    check_host_allowed(uri, allow_remote)
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(uri)
    try:
        db = client[db_name] if db_name else client.get_default_database()
        report = await audit_database(db, batch_size=batch_size,
                                      max_examples=max_examples)
    finally:
        client.close()
    return report


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="标签唯一性只读盘点（绝不写库）")
    parser.add_argument("--uri", default=os.environ.get("MONGODB_AUDIT_URI")
                        or os.environ.get("MONGODB_URL"),
                        help="MongoDB 连接串；缺省读 MONGODB_AUDIT_URI / MONGODB_URL")
    parser.add_argument("--db", default=os.environ.get("MONGODB_DB_NAME"),
                        help="库名；缺省读 MONGODB_DB_NAME 或连接串默认库")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE_DEFAULT)
    parser.add_argument("--max-examples", type=int, default=MAX_EXAMPLES_DEFAULT)
    parser.add_argument("--allow-remote", action="store_true",
                        help="允许连接非 localhost 主机（工具仍只读）")
    args = parser.parse_args(argv)
    if not args.uri:
        raise SystemExit("缺连接串：用 --uri 或环境变量 MONGODB_AUDIT_URI / MONGODB_URL")
    return args


def main(argv=None):
    args = parse_args(argv)
    report = asyncio.run(run(args.uri, args.db, args.batch_size,
                             args.max_examples, args.allow_remote))
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    sys.stderr.write(render_summary(report) + "\n")


if __name__ == "__main__":
    main()
