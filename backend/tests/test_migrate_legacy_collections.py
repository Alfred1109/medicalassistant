"""迁移脚本 scripts/migrate_legacy_collections.py 的单元测试。

用内存打桩集合验证：
- dry-run（默认）不写入任何数据；
- --apply 按遗留集合 -> 唯一集合复制文档，并按 enrich 补齐字段别名；
- 幂等：重复执行第二次复制数为 0；
- 不改动遗留集合本身（复制而非移动）；
- REPORT_ONLY 集合只统计不复制。
"""
import unittest

from scripts.migrate_legacy_collections import (
    MIGRATIONS,
    REPORT_ONLY,
    print_report,
    run,
)


class FakeCollection:
    """最小化 AsyncIOMotorCollection 打桩：内存字典存储。"""

    def __init__(self):
        self.docs = {}

    async def count_documents(self, _filter):
        return len(self.docs)

    def find(self, _filter, projection=None):
        return self

    def __aiter__(self):
        self._iter = iter(list(self.docs.values()))
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration

    async def insert_one(self, doc):
        assert doc["_id"] not in self.docs, "insert_one 不应覆盖已有 _id"
        self.docs[doc["_id"]] = dict(doc)


class FakeDatabase:
    def __init__(self):
        self._collections = {}

    def __getitem__(self, name):
        return self._collections.setdefault(name, FakeCollection())


def _doc(_id, **fields):
    doc = {"_id": _id}
    doc.update(fields)
    return doc


def _seed_legacy(db):
    legacy = db["follow_ups"]
    legacy.docs = {
        "f1": _doc("f1", doctor_id="d1", patient_id="p1"),
        "f2": _doc("f2", doctor_id="d2", patient_id="p2", created_by="already"),
        "f3": _doc("f3", doctor_id="d3", patient_id="p3"),
    }
    # 目标集合中已存在 f1（模拟此前已迁移过）
    db["followup_records"].docs = {
        "f1": _doc("f1", doctor_id="d1", patient_id="p1"),
    }


class MigrateLegacyCollectionsTests(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_does_not_write(self):
        db = FakeDatabase()
        _seed_legacy(db)

        report = await run(db, apply=False)

        # 目标集合保持原样
        self.assertEqual(set(db["followup_records"].docs), {"f1"})
        # 所有迁移项均为 would_copy，copied 为 0
        for item in report["migrations"]:
            self.assertEqual(item["copied"], 0)
        followup = next(i for i in report["migrations"] if i["legacy"] == "follow_ups")
        self.assertEqual(followup["legacy_count"], 3)
        self.assertEqual(followup["already_migrated"], 1)
        self.assertEqual(followup["would_copy"], 2)

    async def test_apply_copies_and_enriches_created_by(self):
        db = FakeDatabase()
        _seed_legacy(db)

        report = await run(db, apply=True)

        target = db["followup_records"]
        self.assertEqual(set(target.docs), {"f1", "f2", "f3"})
        # enrich：缺 created_by 时从 doctor_id 补齐
        self.assertEqual(target.docs["f3"]["created_by"], "d3")
        # 已有 created_by 不被覆盖
        self.assertEqual(target.docs["f2"]["created_by"], "already")
        followup = next(i for i in report["migrations"] if i["legacy"] == "follow_ups")
        self.assertEqual(followup["copied"], 2)
        self.assertEqual(followup["already_migrated"], 1)
        # 遗留集合不动（复制而非移动）
        self.assertEqual(set(db["follow_ups"].docs), {"f1", "f2", "f3"})

    async def test_apply_is_idempotent(self):
        db = FakeDatabase()
        _seed_legacy(db)

        await run(db, apply=True)
        second = await run(db, apply=True)

        for item in second["migrations"]:
            self.assertEqual(item["copied"], 0)
            self.assertEqual(item["already_migrated"], item["legacy_count"])
        self.assertEqual(set(db["followup_records"].docs), {"f1", "f2", "f3"})

    async def test_rehab_plan_migration_targets_unique_name(self):
        db = FakeDatabase()
        db["rehabilitation_plans"].docs = {
            "r1": _doc("r1", name="plan-a"),
            "r2": _doc("r2", name="plan-b"),
        }

        report = await run(db, apply=True)

        item = next(i for i in report["migrations"] if i["legacy"] == "rehabilitation_plans")
        self.assertEqual(item["target"], "rehab_plans")
        self.assertEqual(item["copied"], 2)
        self.assertEqual(set(db["rehab_plans"].docs), {"r1", "r2"})

    async def test_progress_record_migration_targets_unique_name(self):
        db = FakeDatabase()
        db["progress_records"].docs = {"g1": _doc("g1", plan_id="r1")}

        report = await run(db, apply=True)

        item = next(i for i in report["migrations"] if i["legacy"] == "progress_records")
        self.assertEqual(item["target"], "rehab_progress")
        self.assertEqual(item["copied"], 1)

    async def test_report_only_collections_are_counted_not_copied(self):
        db = FakeDatabase()
        db["patients"].docs = {"p1": _doc("p1", name="legacy-patient")}
        db["doctors"].docs = {"d1": _doc("d1", name="legacy-doctor")}

        report = await run(db, apply=True)

        self.assertEqual(report["report_only"]["patients"], 1)
        self.assertEqual(report["report_only"]["doctors"], 1)
        # users 唯一集合不受影响
        self.assertEqual(db["users"].docs, {})

    def test_migration_plan_covers_confirmed_legacy_names(self):
        targets = {(m["legacy"], m["target"]) for m in MIGRATIONS}
        self.assertIn(("follow_ups", "followup_records"), targets)
        self.assertIn(("rehabilitation_plans", "rehab_plans"), targets)
        self.assertIn(("progress_records", "rehab_progress"), targets)
        self.assertIn("patients", REPORT_ONLY)
        self.assertIn("doctors", REPORT_ONLY)

    async def test_print_report_smoke(self):
        db = FakeDatabase()
        _seed_legacy(db)
        report = await run(db, apply=False)
        # print_report 只打印不抛错（冒烟）
        print_report(report, apply=False)
