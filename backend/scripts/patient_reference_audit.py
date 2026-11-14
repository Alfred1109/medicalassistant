"""历史患者引用只读盘点工具（第一波段 T6）。

盘什么：
  业务集合中指向「历史患者账号」（users 集合 role:"patient" 文档）的引用字段，
  以及患者账号文档自身（users role:"patient"）的存活分布、同 identity key
  多文档组、医护归属字段（practitioners / health_managers）的双形态与悬空。

本工具只读：仅执行 find / to_list 游标读取，绝不 insert / update / delete /
create_index / drop。连接串经 --uri 参数或 MONGODB_AUDIT_URI（缺省回退
MONGODB_URL）环境变量提供；缺省只允许连接 localhost / 127.0.0.1 / ::1，
连远程实例必须显式加 --allow-remote（虽然本工具不写，仍做主机闸门）。

运行方式（在 backend/ 目录下）：
    MONGODB_AUDIT_URI="mongodb://localhost:27017" \
        .venv/bin/python -m scripts.patient_reference_audit > audit.json
    .venv/bin/python -m scripts.patient_reference_audit --uri mongodb://localhost:27017 \
        --db rehabman --batch-size 2000 > audit.json

输出：JSON 报告写 stdout（可重定向），人类可读摘要写 stderr。

输出字段含义（JSON 顶层）：
  generated_at          ISO8601 生成时间
  database              盘点的库名
  batch_size            游标分批大小
  collections           每个业务集合一段，键为集合名（含 legacy 集合，不存在则全 0）
    field               该集合被盘的患者引用字段名
    total_documents     集合内扫描到的文档总数
    missing             字段在文档上不存在（键缺失）的文档数
    null                字段存在但值为 null 的文档数（如 devices 历史非患者绑定）
    objectid_form       值为 BSON ObjectId 形态的文档数
    string_form         值为 24 位 hex 字符串形态的文档数
    other_form          其他形态（非 hex 字符串、数值等）的文档数
    dangling            悬空引用数：identity_key 命中的 key 在 users 中无任何文档
    ambiguous           歧义引用数：identity_key 命中的 key 对应多个 users 文档
                        （判定口径与 core/patient_identity.load_identity_groups
                        一致：无 role 过滤，ObjectId 与 canonical string 同键）
    dangling_examples   悬空样本（默认最多 20 条）：{"key", "value", "form"}
    ambiguous_examples  歧义样本：{"key", "user_ids"}（users 各文档 _id 字符串）
    examples_truncated  样本是否被截断
  仅部分集合出现的字段：
    legacy_missing      仅 follow_ups：第一代形状「缺失」（missing+null）计数。
                        第一代造数文档缺 patient_id 属历史既定
                        （scripts/migrate_legacy_collections.py 映射表
                        「不映射项：patient_id」），不计入异常悬空口径。
    string_id_documents 仅 patientmanager.daily_records：_id 为字符串形态的
                        历史文档计数（router 以 object:/string: 前缀双形态
                        兼容读取，见 app/api/routers/patient_router.py）。
  legacy_followups      follow_ups（第一代）与 followup_records（第二代）的
                        患者引用口径并列对照段：
    note                口径说明（第一代缺 patient_id 属历史既定）
    first_generation    {"collection": "follow_ups", ...follow_ups 统计段}
    second_generation   {"collection": "followup_records", ...对应统计段}
  users_patients        患者账号文档（users role:"patient"）盘点
    total_patients      患者账号文档总数
    is_active           {"true" / "false" / "missing" / "other"} 分布
    duplicate_identity_groups  同 identity key 多文档组：{"key", "user_ids", "count"}
    attribution_fields  practitioners / health_managers 各一段：
      docs_without_field 缺该归属字段（或不是列表）的患者文档数
      entries            归属条目总数
      objectid_form / string_form / other_form  条目形态分布
      dangling           指向 users 中不存在文档的条目数
      ambiguous          指向同 key 多 users 文档的条目数
      resolved_roles     命中文档的 role 分布（如 {"doctor": n}）
  notes                 口径备注

本工具只产出事实清单，不做任何迁移/修复决策；迁移方案须另行制定并经业务确认。
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit

from bson import ObjectId

from app.core.patient_identity import identity_key

BATCH_SIZE_DEFAULT = 1000
MAX_EXAMPLES_DEFAULT = 20

# (集合名, 患者引用字段)。集合名与字段名均已在代码中核实：
# - daily_records 的真实集合名是字面量 "patientmanager.daily_records"
#   （app/api/routers/patient_router.py:92），患者字段是 user_id；
# - follow_ups 为第一代遗留集合（归档只读保留），其第一代形状文档缺 patient_id，
#   盘点仅作对照，缺失是已知历史形态而非异常。
# - rehab_progress 的患者字段见 app/models/rehabilitation.py:217。
PATIENT_REFERENCES = (
    ("followup_records", "patient_id"),
    ("follow_ups", "patient_id"),
    ("health_records", "patient_id"),
    ("health_data", "patient_id"),
    ("medical_timelines", "patient_id"),
    ("rehab_plans", "patient_id"),
    ("rehab_plan_versions", "patient_id"),
    ("rehab_prescription_items", "patient_id"),
    ("rehab_execution_events", "patient_id"),
    ("rehab_progress", "patient_id"),
    ("patient_feedback_media", "patient_id"),
    ("devices", "patient_id"),
    ("integration_fill_tasks", "patient_id"),
    ("patientmanager.daily_records", "user_id"),
    ("quality_issues", "patient_id"),
    ("external_patient_links", "local_patient_id"),
)

# 特定集合的附加盘点口径（键与 PATIENT_REFERENCES 的集合名对应）：
# - follow_ups：第一代造数形状缺 patient_id 属历史既定（不映射项，见
#   scripts/migrate_legacy_collections.py 映射表），单独计 legacy_missing；
# - patientmanager.daily_records：集合存在 string _id 的历史文档
#   （router 以 object:/string: 前缀双形态兼容读取），单独计
#   string_id_documents。
REFERENCE_AUDIT_OPTIONS = {
    "follow_ups": {"legacy_missing": True},
    "patientmanager.daily_records": {"track_string_ids": True},
}

PATIENT_ROLE = "patient"
ATTRIBUTION_FIELDS = ("practitioners", "health_managers")

_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"}


def classify_form(value):
    """引用值的形态分类；形态与判定（identity_key）解耦。

    返回 "missing" / "null" / "objectid" / "string" / "other"。
    "string" 仅指 24 位 hex 字符串；其余字符串（旧客户端自由字符串 ID）
    归入 "other"，但仍会用 identity_key 参与悬空/歧义判定，与适配器语义一致。
    """
    if isinstance(value, ObjectId):
        return "objectid"
    if isinstance(value, str):
        return "string" if ObjectId.is_valid(value) else "other"
    return "other"


def classify_is_active(value):
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "missing" if value is None else "other"


async def iter_batches(cursor, batch_size):
    """游标分批拉取；内存占用只与 batch_size 相关，不随集合大小线性膨胀。"""
    while True:
        batch = await cursor.to_list(length=batch_size)
        if not batch:
            return
        for doc in batch:
            yield doc


def new_reference_stats(field):
    return {
        "field": field,
        "total_documents": 0,
        "missing": 0,
        "null": 0,
        "objectid_form": 0,
        "string_form": 0,
        "other_form": 0,
        "dangling": 0,
        "ambiguous": 0,
        "dangling_examples": [],
        "ambiguous_examples": [],
        "examples_truncated": False,
    }


def _note_dangling_example(stats, max_examples, key, value):
    if any(ex["key"] == key for ex in stats["dangling_examples"]):
        return
    if len(stats["dangling_examples"]) < max_examples:
        stats["dangling_examples"].append(
            {"key": key, "value": str(value), "form": classify_form(value)})
    else:
        stats["examples_truncated"] = True


def _note_ambiguous_example(stats, max_examples, key, group):
    if any(ex["key"] == key for ex in stats["ambiguous_examples"]):
        return
    if len(stats["ambiguous_examples"]) < max_examples:
        stats["ambiguous_examples"].append(
            {"key": key, "user_ids": [item[0] for item in group]})
    else:
        stats["examples_truncated"] = True


def resolve_key(value, stats, index, max_examples):
    """按 identity_key 判定悬空/歧义；与 load_identity_groups 同口径（无 role 过滤）。

    other 形态（含自由字符串）也经 identity_key 归组判定，保证与适配器一致。
    """
    key = identity_key(value)
    group = index.get(key)
    if group is None:
        stats["dangling"] += 1
        _note_dangling_example(stats, max_examples, key, value)
        return
    if len(group) > 1:
        stats["ambiguous"] += 1
        _note_ambiguous_example(stats, max_examples, key, group)


async def audit_reference_collection(db, collection_name, field, index,
                                     batch_size, max_examples, *,
                                     legacy_missing=False,
                                     track_string_ids=False):
    stats = new_reference_stats(field)
    if legacy_missing:
        stats["legacy_missing"] = 0
    if track_string_ids:
        stats["string_id_documents"] = 0
    cursor = db[collection_name].find({}, None)
    async for doc in iter_batches(cursor, batch_size):
        stats["total_documents"] += 1
        if track_string_ids and isinstance(doc.get("_id"), str):
            stats["string_id_documents"] += 1
        if field not in doc:
            stats["missing"] += 1
            if legacy_missing:
                stats["legacy_missing"] += 1
            continue
        value = doc[field]
        if value is None:
            stats["null"] += 1
            if legacy_missing:
                stats["legacy_missing"] += 1
            continue
        form = classify_form(value)
        stats[f"{form}_form"] += 1
        resolve_key(value, stats, index, max_examples)
    return stats


def new_attribution_stats():
    return {
        "docs_without_field": 0,
        "entries": 0,
        "objectid_form": 0,
        "string_form": 0,
        "other_form": 0,
        "dangling": 0,
        "ambiguous": 0,
        "resolved_roles": {},
        "dangling_examples": [],
        "ambiguous_examples": [],
        "examples_truncated": False,
    }


def resolve_attribution_entry(value, stats, index, max_examples):
    key = identity_key(value)
    group = index.get(key)
    if group is None:
        stats["dangling"] += 1
        _note_dangling_example(stats, max_examples, key, value)
        return
    if len(group) > 1:
        stats["ambiguous"] += 1
        _note_ambiguous_example(stats, max_examples, key, group)
        return
    role = group[0][1]
    stats["resolved_roles"][role] = stats["resolved_roles"].get(role, 0) + 1


async def build_users_index(db, batch_size):
    """流式扫描 users，建 identity key -> [(str(_id), role), ...] 索引。

    索引无 role 过滤，与 load_identity_groups 的命中口径一致；患者子集统计
    （role:"patient"）与医护索引共用同一次扫描。
    """
    index = {}
    cursor = db["users"].find({}, None)
    async for doc in iter_batches(cursor, batch_size):
        key = identity_key(doc["_id"])
        role = doc.get("role")
        if not isinstance(role, str):
            role = "other"
        entry = index.get(key)
        if entry is None:
            index[key] = [(str(doc["_id"]), role)]
        else:
            entry.append((str(doc["_id"]), role))
    return index


def _trim_examples(stats, max_examples):
    truncated = stats.pop("examples_truncated") or \
        len(stats["dangling_examples"]) >= max_examples or \
        len(stats["ambiguous_examples"]) >= max_examples
    stats["examples_truncated"] = truncated


async def audit_user_patients(db, index, batch_size, max_examples):
    """users role:"patient" 子集：总数 / is_active / 同 key 多文档组 / 归属字段。"""
    total = 0
    is_active = {"true": 0, "false": 0, "missing": 0, "other": 0}
    duplicate_groups = {}  # key -> [str(_id) ...]
    attribution = {name: new_attribution_stats() for name in ATTRIBUTION_FIELDS}
    cursor = db["users"].find({"role": PATIENT_ROLE}, None)
    async for doc in iter_batches(cursor, batch_size):
        total += 1
        is_active[classify_is_active(doc.get("is_active"))] += 1
        key = identity_key(doc["_id"])
        if len(index.get(key, [])) > 1:
            duplicate_groups.setdefault(key, []).append(str(doc["_id"]))
        for name in ATTRIBUTION_FIELDS:
            stats = attribution[name]
            value = doc.get(name)
            if not isinstance(value, list):
                stats["docs_without_field"] += 1
                continue
            for entry in value:
                stats["entries"] += 1
                form = classify_form(entry)
                stats[f"{form}_form"] += 1
                resolve_attribution_entry(entry, stats, index, max_examples)
    for stats in attribution.values():
        _trim_examples(stats, max_examples)
    groups = [
        {"key": key, "user_ids": ids, "count": len(ids)}
        for key, ids in sorted(duplicate_groups.items())
    ]
    return {
        "total_patients": total,
        "is_active": is_active,
        "duplicate_identity_groups": groups,
        "attribution_fields": attribution,
    }


async def audit_database(db, *, batch_size=BATCH_SIZE_DEFAULT,
                         max_examples=MAX_EXAMPLES_DEFAULT,
                         reference_targets=PATIENT_REFERENCES):
    index = await build_users_index(db, batch_size)
    collections = {}
    for collection_name, field in reference_targets:
        options = REFERENCE_AUDIT_OPTIONS.get(collection_name, {})
        collections[collection_name] = await audit_reference_collection(
            db, collection_name, field, index, batch_size, max_examples,
            **options)
    for stats in collections.values():
        _trim_examples(stats, max_examples)
    users_patients = await audit_user_patients(
        db, index, batch_size, max_examples)
    legacy_followups = build_legacy_followups_section(collections)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database": getattr(db, "name", "<unknown>"),
        "batch_size": batch_size,
        "collections": collections,
        "legacy_followups": legacy_followups,
        "users_patients": users_patients,
        "notes": [
            "悬空/歧义判定与 app/core/patient_identity.load_identity_groups 同口径："
            "identity_key 归组、无 role 过滤、ObjectId 与 canonical string 同键。",
            "missing=字段不存在；null=字段为 None；两者合计即「缺失」。",
            "follow_ups 第一代形状缺 patient_id 属历史既定（不映射项，"
            "见 scripts/migrate_legacy_collections.py），计入其 legacy_missing，"
            "详见 legacy_followups 段。",
            "本报告仅为事实盘点，不产出迁移或修复决策。",
        ],
    }


def build_legacy_followups_section(collections):
    """follow_ups（第一代）与 followup_records（第二代）患者引用口径并列。

    第一代缺 patient_id 是历史既定（FU01 D-4 已决策归档只读；迁移脚本映射表
    「不映射项：patient_id」），记入 legacy_missing 而不作为异常悬空上报；
    悬空/歧义仍只统计 patient_id 有值的文档。统计段直接引用 collections
    中的对应 dict，保证与逐集合输出一致、不产生第二份独立计数。
    """
    first = collections.get("follow_ups")
    second = collections.get("followup_records")
    if first is None or second is None:
        return None
    return {
        "note": (
            "follow_ups 为第一代遗留集合（FU01 D-4 决策归档只读、冻结写入）。"
            "第一代造数形状文档缺 patient_id 属历史既定"
            "（scripts/migrate_legacy_collections.py 字段级映射表"
            "「不映射项：patient_id」），计入 legacy_missing（missing+null），"
            "不作为异常悬空上报；dangling/ambiguous 仅统计 patient_id 有值"
            "且 key 无法唯一命中的文档。"),
        "first_generation": {"collection": "follow_ups", **first},
        "second_generation": {"collection": "followup_records", **second},
    }


def render_summary(report):
    lines = []
    lines.append(f"患者引用盘点 {report['database']} @ {report['generated_at']}")
    lines.append(f"{'集合':<32}{'总数':>8}{'缺/空':>7}{'OID':>7}{'STR':>7}"
                 f"{'悬空':>7}{'歧义':>7}")
    for name, stats in report["collections"].items():
        lines.append(
            f"{name:<32}{stats['total_documents']:>8}"
            f"{stats['missing'] + stats['null']:>7}"
            f"{stats['objectid_form']:>7}{stats['string_form']:>7}"
            f"{stats['dangling']:>7}{stats['ambiguous']:>7}")
    daily = report["collections"].get("patientmanager.daily_records")
    if daily and "string_id_documents" in daily:
        lines.append(
            f"patientmanager.daily_records string _id 历史文档: "
            f"{daily['string_id_documents']}")
    legacy = report["legacy_followups"]
    if legacy:
        first, second = legacy["first_generation"], legacy["second_generation"]
        lines.append(
            f"follow_ups(一代) legacy_missing {first['legacy_missing']} / "
            f"followup_records(二代) missing {second['missing'] + second['null']}"
            f"；悬空 {first['dangling']}/{second['dangling']}，"
            f"歧义 {first['ambiguous']}/{second['ambiguous']}（一代/二代）"
            "——一代缺 patient_id 属历史既定")
    users = report["users_patients"]
    lines.append(f"users 患者: {users['total_patients']} (is_active: {users['is_active']})")
    lines.append(f"同 identity key 多文档组: {len(users['duplicate_identity_groups'])} 组")
    for name, stats in users["attribution_fields"].items():
        lines.append(
            f"{name}: 条目 {stats['entries']} "
            f"(OID {stats['objectid_form']} / STR {stats['string_form']} / "
            f"other {stats['other_form']}) 悬空 {stats['dangling']} 歧义 {stats['ambiguous']} "
            f"命中 role: {stats['resolved_roles']}")
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
        description="历史患者引用只读盘点（绝不写库）")
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
