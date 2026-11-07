"""BASE03 集合名收敛：遗留集合迁移脚本。

把遗留集合中的文档复制到收敛后的唯一集合（见 docs/wp0-domain-convergence-analysis-2026-11-07.md §五）。

行为约束：
- 默认 dry-run：只统计并打印，不写任何数据；
- 传 --apply 才执行复制；
- 幂等：按 _id 已存在于目标集合则跳过，可重复执行；
- 只复制、只补齐字段别名，绝不删除或修改遗留集合；
- 结束时打印"遗留集合保留待人工处置"。

用法（在 backend/ 目录下）：
    .venv/bin/python -m scripts.migrate_legacy_collections            # dry-run
    .venv/bin/python -m scripts.migrate_legacy_collections --apply    # 执行复制
"""
import argparse
import asyncio

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings

# 遗留集合 -> 唯一集合 的复制清单
# enrich: 复制时补齐的字段别名 {目标字段: 来源字段}，
# 仅当目标字段缺失且来源字段存在时补齐，不改动文档其余内容
MIGRATIONS = [
    {
        "legacy": "follow_ups",
        "target": "followup_records",
        "enrich": {"created_by": "doctor_id"},
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


async def migrate_collection(db, migration, apply=False):
    """迁移单个遗留集合，返回统计报告。

    db 只需支持 db[name] 取集合、count_documents / find / insert_one，
    便于测试用内存打桩替换。
    """
    legacy_name = migration["legacy"]
    target_name = migration["target"]
    enrich = migration.get("enrich") or {}

    legacy = db[legacy_name]
    target = db[target_name]

    legacy_count = await legacy.count_documents({})
    target_ids = {doc["_id"] async for doc in target.find({}, {"_id": 1})}

    copied = 0
    skipped = 0
    would_copy = 0

    async for doc in legacy.find({}):
        if doc["_id"] in target_ids:
            skipped += 1
            continue
        if not apply:
            would_copy += 1
            continue
        for dest_field, source_field in enrich.items():
            if dest_field not in doc and source_field in doc:
                doc[dest_field] = doc[source_field]
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
    }


async def run(db, apply=False):
    """执行全部迁移计划，返回汇总报告（不打印）。"""
    report = {"migrations": [], "report_only": {}}
    for migration in MIGRATIONS:
        report["migrations"].append(await migrate_collection(db, migration, apply=apply))
    for name in REPORT_ONLY:
        report["report_only"][name] = await db[name].count_documents({})
    return report


def print_report(report, apply):
    mode = "APPLY（已写入）" if apply else "DRY-RUN（未写入）"
    print(f"遗留集合迁移计划 [{mode}]")
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
    for name, count in report["report_only"].items():
        print(f"  [仅报告] {name}: 文档 {count}（无安全自动映射，需人工决策）")


async def main(argv=None):
    parser = argparse.ArgumentParser(description="遗留集合迁移脚本（默认 dry-run）")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="执行复制；缺省为 dry-run，只统计不写入",
    )
    args = parser.parse_args(argv)

    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    report = await run(db, apply=args.apply)
    print_report(report, args.apply)
    print("遗留集合保留待人工处置")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
