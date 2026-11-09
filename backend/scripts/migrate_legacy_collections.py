"""BASE03 集合名收敛：遗留集合迁移脚本。

把遗留集合中的文档复制到收敛后的唯一集合（见 docs/wp0-domain-convergence-analysis-2026-11-07.md §五）。

FU01 S3 起对 follow_ups -> followup_records 的复制升级为「字段级映射 + 打标」
（docs/wp3-fu01-domain-design-draft-2026-11-07.md §2.4、§五 S3）：
第一代造数形状文档（title/content/doctor_id/completed_date，缺
patient_id/scheduled_date/status）直接复制进 followup_records 会是脏文档，
故复制时按下方映射表转换并打 legacy_source 标。

follow_ups 第一代形状 -> 第二代契约（FollowUpRecordDB）字段级映射表：
  ---------------------------------------------------------------
  目标字段          规则（按序取首个命中）
  ---------------------------------------------------------------
  status            1) 文档已有 status：拼写归一 cancelled -> canceled
                       （与 FollowUpStatus.CANCELED 枚举拼写一致，
                       schemas/followup.py:39），其余值原样保留；
                    2) 无 status 但有 completed_date -> "completed"；
                    3) 两者皆无 -> "scheduled"（FollowUpRecordDB 默认，
                       避免复制后仍是无状态脏文档）
  scheduled_date    1) 已有则不动；
                    2) 缺失且有 completed_date -> 以 completed_date 回填；
                    3) 皆无则保持缺失（计数上报）
  notes             1) 已有 notes 且无 title -> 不动；
                    2) 无 notes 有 title -> notes = title（并入，title 不删）；
                    3) 两者皆有 -> notes = title + "\\n" + notes（title 前置保留）
  created_by        enrich 别名：缺失且 doctor_id 存在 -> doctor_id
  legacy_source     复制时注入 {"collection": <来源集合名>, "batch": <迁移批次标识>}
  ---------------------------------------------------------------
  不映射项：patient_id（第一代文档无对应来源，缺失保持缺失，
  计数上报；造数数据是否值得迁移属设计稿 §六 D-4 业务决策）。

行为约束：
- 默认 dry-run：只统计并打印（含映射前后差异示例），不写任何数据；
- 传 --apply 才执行复制；
- 幂等：按 _id 已存在于目标集合则跳过，可重复执行（已复制文档不会被
  再次打标或改值）；
- 只复制、绝不删除或修改遗留集合本身（转换只作用于复制出的副本）；
- 结束时打印"遗留集合保留待人工处置"。

FU01 D-4 决策（2026-11-09，用户授权默认采纳设计稿「归档只读」方案，
见设计稿末尾实施记录）：
- follow_ups 遗留造数数据**归档只读，不迁移**：不复制进业务集合
  followup_records，遗留集合冻结写入、原样保留；
- 本脚本新增归档能力 archive_collection（--archive <集合名>）：把指定遗留
  集合文档**原样**复制到 archive_<集合名> 归档集合（只加来源/批次打标，
  不做任何字段映射），同样默认 dry-run、幂等、绝不删除或修改源集合；
- MIGRATIONS 中保留的 follow_ups 字段级映射能力不删除（供未来业务明确
  追认「迁移」方案时使用），但**任何真实迁移/归档执行前必须业务确认并
  在隔离实例演练**——本仓库严禁未经授权对真实业务库执行。

用法（在 backend/ 目录下）：
    .venv/bin/python -m scripts.migrate_legacy_collections            # dry-run
    .venv/bin/python -m scripts.migrate_legacy_collections --apply    # 执行复制
    .venv/bin/python -m scripts.migrate_legacy_collections --archive follow_ups              # 归档 dry-run
    .venv/bin/python -m scripts.migrate_legacy_collections --archive follow_ups --apply      # 执行归档复制
"""
import argparse
import asyncio
import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings

# 拼写归一表：统一到 FollowUpStatus 枚举拼写（schemas/followup.py 用 "canceled"，
# 设计稿 §2.2 明确「全部采用 schema 现有拼写 canceled」）
STATUS_SPELLING_MAP = {"cancelled": "canceled"}


def transform_followup_doc(doc, source_collection, batch_id):
    """对 follow_ups 遗留文档做字段级映射（只作用于副本，不改动入参）。

    返回 (转换后文档, 变更字典)；变更字典形如
    {"status": {"before": None, "after": "completed"}, ...}，
    before=None 表示原文档缺失该字段。
    """
    doc = dict(doc)  # 复制副本，绝不改动遗留集合文档
    changes = {}

    # ---- status 映射（拼写归一 -> completed_date 推导 -> 第二代默认） ----
    status = doc.get("status")
    if status is not None:
        normalized = STATUS_SPELLING_MAP.get(str(status), status)
        if normalized != status:
            doc["status"] = normalized
            changes["status"] = {"before": status, "after": normalized}
    elif "completed_date" in doc and doc["completed_date"] is not None:
        doc["status"] = "completed"
        changes["status"] = {"before": None, "after": "completed"}
    else:
        doc["status"] = "scheduled"
        changes["status"] = {"before": None, "after": "scheduled"}

    # ---- scheduled_date 回填 ----
    if doc.get("scheduled_date") is None and doc.get("completed_date") is not None:
        doc["scheduled_date"] = doc["completed_date"]
        changes["scheduled_date"] = {"before": None, "after": doc["completed_date"]}

    # ---- title 并入 notes ----
    title = doc.get("title")
    notes = doc.get("notes")
    if title:
        if not notes:
            doc["notes"] = title
        else:
            doc["notes"] = f"{title}\n{notes}"
        changes["notes"] = {"before": notes, "after": doc["notes"]}

    # ---- legacy_source 打标（来源集合名 + 迁移批次标识） ----
    doc["legacy_source"] = {"collection": source_collection, "batch": batch_id}
    changes["legacy_source"] = {"before": None, "after": doc["legacy_source"]}

    return doc, changes


# 遗留集合 -> 唯一集合 的复制清单
# enrich: 复制时补齐的字段别名 {目标字段: 来源字段}，
# 仅当目标字段缺失且来源字段存在时补齐，不改动文档其余内容；
# transform: 复制时的字段级映射函数（FU01 S3，仅 follow_ups 需要）
# 注：integration_fill_tasks（FU01 S4 起模型名 FollowUpFillTask，集合名不变）不在本
# 脚本范围——设计稿 §3.1：试点数据零迁移，集合原样沿用，无需复制/打标。
MIGRATIONS = [
    {
        "legacy": "follow_ups",
        "target": "followup_records",
        "enrich": {"created_by": "doctor_id"},
        "transform": transform_followup_doc,
    },
    {
        "legacy": "rehabilitation_plans",
        "target": "rehab_plans",
        "enrich": {},
    },
    {
        "legacy": "progress_records",
        "target": "rehab_progress",
        "enrich": {},
    },
]

# 同为遗留集合名，但与唯一集合（users）文档形状差异过大，
# 或全库没有任何对应写入路径，不做自动复制，只报告计数，需人工决策
REPORT_ONLY = [
    "patients",
    "doctors",
    "rehabilitation_records",
    "rehabilitation_sessions",
]


def _new_batch_id():
    """迁移批次标识：一次脚本运行内所有复制文档共用同一个批次号。"""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


async def migrate_collection(db, migration, apply=False, batch_id=None):
    """迁移单个遗留集合，返回统计报告。

    db 只需支持 db[name] 取集合、count_documents / find / insert_one，
    便于测试用内存打桩替换。
    """
    legacy_name = migration["legacy"]
    target_name = migration["target"]
    enrich = migration.get("enrich") or {}
    transform = migration.get("transform")

    legacy = db[legacy_name]
    target = db[target_name]

    legacy_count = await legacy.count_documents({})
    target_ids = {doc["_id"] async for doc in target.find({}, {"_id": 1})}

    copied = 0
    skipped = 0
    would_copy = 0
    # 字段级映射命中计数（key 与 transform_followup_doc 的 changes 对齐）
    mapped = {
        "status": 0,
        "scheduled_date": 0,
        "notes": 0,
        "spelling_normalized": 0,
        "legacy_source": 0,
    }
    sample_diffs = []  # 映射前后差异示例（最多 5 条）

    async for doc in legacy.find({}):
        if doc["_id"] in target_ids:
            skipped += 1
            continue
        # 复制副本上做 enrich + transform，绝不改动遗留集合文档本身
        doc = dict(doc)
        for dest_field, source_field in enrich.items():
            if dest_field not in doc and source_field in doc:
                doc[dest_field] = doc[source_field]
        changes = {}
        if transform is not None:
            doc, changes = transform(doc, legacy_name, batch_id)
            for key in ("status", "scheduled_date", "notes", "legacy_source"):
                if key in changes:
                    mapped[key] += 1
            if "status" in changes and changes["status"]["before"] is not None:
                mapped["spelling_normalized"] += 1
            if len(sample_diffs) < 5 and changes:
                sample_diffs.append({"_id": doc["_id"], "changes": changes})
        if not apply:
            would_copy += 1
            continue
        await target.insert_one(doc)
        target_ids.add(doc["_id"])
        copied += 1

    return {
        "legacy": legacy_name,
        "target": target_name,
        "legacy_count": legacy_count,
        "already_migrated": skipped,
        "copied": copied,
        "would_copy": would_copy,
        "mapped": mapped,
        "sample_diffs": sample_diffs,
    }


async def run(db, apply=False, batch_id=None):
    """执行全部迁移计划，返回汇总报告（不打印）。

    batch_id 缺省时自动生成；测试可显式传入以便断言打标内容。
    """
    if batch_id is None:
        batch_id = _new_batch_id()
    report = {"migrations": [], "report_only": {}, "batch_id": batch_id}
    for migration in MIGRATIONS:
        report["migrations"].append(
            await migrate_collection(db, migration, apply=apply, batch_id=batch_id)
        )
    for name in REPORT_ONLY:
        report["report_only"][name] = await db[name].count_documents({})
    return report


def archive_target_name(legacy_name):
    """归档集合命名：archive_ 前缀 + 原集合名（同一库内，与业务集合隔离）。"""
    return f"archive_{legacy_name}"


async def archive_collection(db, legacy_name, apply=False, batch_id=None):
    """把遗留集合文档原样归档到 archive_<集合名>（FU01 D-4 归档只读能力）。

    与 migrate_collection 的区别：归档是**保真复制**——不做字段级映射、
    不补别名，只加 legacy_source 打标（kind=archive），保证归档可审计、
    可回溯；源集合只读，绝不删除或修改。

    db 只需支持 db[name] 取集合、count_documents / find / insert_one。
    返回统计报告（不打印）。
    """
    if batch_id is None:
        batch_id = _new_batch_id()
    legacy = db[legacy_name]
    target = db[archive_target_name(legacy_name)]

    legacy_count = await legacy.count_documents({})
    target_ids = {doc["_id"] async for doc in target.find({}, {"_id": 1})}

    copied = 0
    skipped = 0
    would_copy = 0

    async for doc in legacy.find({}):
        if doc["_id"] in target_ids:
            skipped += 1
            continue
        # 归档副本：原样复制 + 打标，绝不改动源集合文档
        archived = dict(doc)
        archived["legacy_source"] = {
            "collection": legacy_name, "batch": batch_id, "kind": "archive",
        }
        if not apply:
            would_copy += 1
            continue
        await target.insert_one(archived)
        target_ids.add(doc["_id"])
        copied += 1

    return {
        "legacy": legacy_name,
        "target": archive_target_name(legacy_name),
        "legacy_count": legacy_count,
        "already_archived": skipped,
        "copied": copied,
        "would_copy": would_copy,
    }


async def run_archive(db, names, apply=False, batch_id=None):
    """归档多个遗留集合，返回汇总报告（不打印）。"""
    if batch_id is None:
        batch_id = _new_batch_id()
    return {"archive": [
        await archive_collection(db, name, apply=apply, batch_id=batch_id)
        for name in names
    ], "batch_id": batch_id}


def print_archive_report(report, apply):
    mode = "APPLY（已写入归档集合）" if apply else "DRY-RUN（未写入）"
    print(f"遗留集合归档计划 [{mode}]  批次: {report.get('batch_id')}")
    for item in report["archive"]:
        line = (
            f"  {item['legacy']} -> {item['target']}（原样保真归档，只加打标）: "
            f"源集合文档 {item['legacy_count']}，"
            f"归档已存在(跳过) {item['already_archived']}"
        )
        if apply:
            line += f"，本次归档 {item['copied']}"
        else:
            line += f"，将归档 {item['would_copy']}"
        print(line)
    print("归档为只读保真副本；源遗留集合冻结写入、保留待人工处置（D-4 归档只读方案）")


def _fmt_value(value):
    return "(缺失)" if value is None else repr(value)


def print_report(report, apply):
    mode = "APPLY（已写入）" if apply else "DRY-RUN（未写入）"
    print(f"遗留集合迁移计划 [{mode}]  批次: {report.get('batch_id')}")
    for item in report["migrations"]:
        line = (
            f"  {item['legacy']} -> {item['target']}: "
            f"遗留文档 {item['legacy_count']}，"
            f"目标已存在(跳过) {item['already_migrated']}"
        )
        if apply:
            line += f"，本次复制 {item['copied']}"
        else:
            line += f"，将复制 {item['would_copy']}"
        print(line)
        mapped = item.get("mapped") or {}
        if any(mapped.values()):
            print(
                "    字段映射命中:"
                f" status {mapped.get('status', 0)}"
                f"（其中拼写归一 cancelled->canceled {mapped.get('spelling_normalized', 0)}）"
                f"，scheduled_date 回填 {mapped.get('scheduled_date', 0)}"
                f"，title 并入 notes {mapped.get('notes', 0)}"
                f"，legacy_source 打标 {mapped.get('legacy_source', 0)}"
            )
        # dry-run：展示映射前后差异示例
        if not apply and item.get("sample_diffs"):
            print("    映射前后差异示例（最多 5 条）:")
            for sample in item["sample_diffs"]:
                parts = [
                    f"{field}: {_fmt_value(change['before'])} -> {_fmt_value(change['after'])}"
                    for field, change in sample["changes"].items()
                ]
                print(f"      _id={sample['_id']}: " + "; ".join(parts))
    for name, count in report["report_only"].items():
        print(f"  [仅报告] {name}: 文档 {count}（无安全自动映射，需人工决策）")


async def main(argv=None):
    parser = argparse.ArgumentParser(description="遗留集合迁移脚本（默认 dry-run）")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="执行复制；缺省为 dry-run，只统计不写入",
    )
    parser.add_argument(
        "--archive",
        nargs="+",
        metavar="集合名",
        help="把指定遗留集合原样归档到 archive_<集合名>（D-4 归档只读能力）；"
             "缺省为 dry-run，配合 --apply 执行写入",
    )
    args = parser.parse_args(argv)

    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    if args.archive:
        report = await run_archive(db, args.archive, apply=args.apply)
        print_archive_report(report, args.apply)
    else:
        report = await run(db, apply=args.apply)
        print_report(report, args.apply)
    print("遗留集合保留待人工处置")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
