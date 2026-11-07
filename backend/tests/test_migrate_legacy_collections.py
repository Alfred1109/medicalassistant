"""迁移脚本 scripts/migrate_legacy_collections.py 的单元测试。

用内存打桩集合验证：
- dry-run（默认）不写入任何数据；
- --apply 按遗留集合 -> 唯一集合复制文档，并按 enrich 补齐字段别名；
- 幂等：重复执行第二次复制数为 0；
- 不改动遗留集合本身（复制而非移动）；
- REPORT_ONLY 集合只统计不复制。

FU01 S3 扩展（follow_ups -> followup_records 字段级映射 + 打标）：
- status 映射（completed_date 推导 / cancelled 拼写归一 / 默认 scheduled）；
- scheduled_date 缺失回填；
- title 并入 notes；
- legacy_source 打标（来源集合名 + 迁移批次）；
- 重复 apply 不重复打标、不改值；
- dry-run 报告含映射前后差异示例且不写库。
"""
import unittest

from scripts.migrate_legacy_collections import (
    MIGRATIONS,
    REPORT_ONLY,
    print_report,
    run,
    transform_followup_doc,
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

    # -------- FU01 S3：follow_ups 字段级映射 + 打标 --------

    BATCH = "batch-test-001"

    def _seed_legacy_followups(self, db):
        """第一代造数形状：title/content/doctor_id/completed_date，缺 status/scheduled_date。"""
        db["follow_ups"].docs = {
            "g1": _doc("g1", doctor_id="d1", title="术后回访", content="一周后",
                       completed_date="2026-01-01T08:00:00"),
            "g2": _doc("g2", doctor_id="d2", title="取消的随访", status="cancelled"),
            "g3": _doc("g3", doctor_id="d3", status="missed"),
            "g4": _doc("g4", doctor_id="d4", title="有备注", notes="原有备注"),
        }

    def _followup_item(self, report):
        return next(i for i in report["migrations"] if i["legacy"] == "follow_ups")

    async def test_status_mapping_completed_date_derives_completed(self):
        db = FakeDatabase()
        self._seed_legacy_followups(db)

        report = await run(db, apply=True, batch_id=self.BATCH)
        target = db["followup_records"]

        # 无 status 但有 completed_date -> completed，且 scheduled_date 回填
        self.assertEqual(target.docs["g1"]["status"], "completed")
        self.assertEqual(target.docs["g1"]["scheduled_date"], "2026-01-01T08:00:00")
        # g1(completed 推导) + g2(拼写归一) + g4(默认 scheduled) 命中；g3 保持 missed 不计
        self.assertEqual(self._followup_item(report)["mapped"]["status"], 3)
        self.assertEqual(self._followup_item(report)["mapped"]["scheduled_date"], 1)

    async def test_status_spelling_normalized_to_canceled(self):
        db = FakeDatabase()
        self._seed_legacy_followups(db)

        await run(db, apply=True, batch_id=self.BATCH)

        # cancelled -> canceled（与 FollowUpStatus.CANCELED 枚举拼写一致）
        self.assertEqual(db["followup_records"].docs["g2"]["status"], "canceled")
        # 其他已知状态值原样保留
        self.assertEqual(db["followup_records"].docs["g3"]["status"], "missed")

    async def test_status_defaults_to_scheduled_when_no_signal(self):
        doc, changes = transform_followup_doc(
            _doc("x1", doctor_id="d1"), "follow_ups", self.BATCH)
        self.assertEqual(doc["status"], "scheduled")
        self.assertEqual(changes["status"], {"before": None, "after": "scheduled"})
        # scheduled_date 无 completed_date 可回填 -> 保持缺失
        self.assertNotIn("scheduled_date", doc)

    async def test_title_merged_into_notes(self):
        db = FakeDatabase()
        self._seed_legacy_followups(db)

        await run(db, apply=True, batch_id=self.BATCH)
        target = db["followup_records"]

        # 无 notes 有 title -> notes = title
        self.assertEqual(target.docs["g1"]["notes"], "术后回访")
        # 两者皆有 -> title 前置并入，原 notes 保留
        self.assertEqual(target.docs["g4"]["notes"], "有备注\n原有备注")

    async def test_legacy_source_tag_written_on_copy(self):
        db = FakeDatabase()
        self._seed_legacy_followups(db)

        report = await run(db, apply=True, batch_id=self.BATCH)
        target = db["followup_records"]

        for doc_id in ("g1", "g2", "g3", "g4"):
            tag = target.docs[doc_id]["legacy_source"]
            self.assertEqual(tag["collection"], "follow_ups")
            self.assertEqual(tag["batch"], self.BATCH)
        # 批次标识回传报告
        self.assertEqual(report["batch_id"], self.BATCH)
        self.assertEqual(self._followup_item(report)["mapped"]["legacy_source"], 4)

    async def test_other_collections_not_tagged_or_transformed(self):
        db = FakeDatabase()
        db["rehabilitation_plans"].docs = {"r1": _doc("r1", name="plan-a", title="t")}

        await run(db, apply=True, batch_id=self.BATCH)

        doc = db["rehab_plans"].docs["r1"]
        self.assertNotIn("legacy_source", doc)
        self.assertNotIn("status", doc)

    async def test_apply_idempotent_no_retag_no_mutation(self):
        db = FakeDatabase()
        self._seed_legacy_followups(db)

        await run(db, apply=True, batch_id=self.BATCH)
        snapshot = {k: dict(v) for k, v in db["followup_records"].docs.items()}

        second = await run(db, apply=True, batch_id="batch-second")

        # 第二次全部跳过：不复制、不重复打标、值不变
        item = self._followup_item(second)
        self.assertEqual(item["copied"], 0)
        self.assertEqual(item["already_migrated"], item["legacy_count"])
        self.assertEqual(item["mapped"]["legacy_source"], 0)
        for doc_id, doc in snapshot.items():
            self.assertEqual(db["followup_records"].docs[doc_id], doc)
            self.assertEqual(db["followup_records"].docs[doc_id]
                             ["legacy_source"]["batch"], self.BATCH)

    async def test_dry_run_reports_diffs_and_writes_nothing(self):
        db = FakeDatabase()
        self._seed_legacy_followups(db)
        legacy_snapshot = {k: dict(v) for k, v in db["follow_ups"].docs.items()}

        report = await run(db, apply=False, batch_id=self.BATCH)
        item = self._followup_item(report)

        # 目标集合未被写入
        self.assertEqual(db["followup_records"].docs, {})
        # 遗留集合文档内容未被转换改动
        for doc_id, doc in legacy_snapshot.items():
            self.assertEqual(db["follow_ups"].docs[doc_id], doc)
        # would_copy 覆盖全部 4 条，映射计数已统计
        self.assertEqual(item["would_copy"], 4)
        self.assertEqual(item["mapped"]["status"], 3)
        # dry-run 报告含映射前后差异示例（含 before/after）
        self.assertTrue(item["sample_diffs"])
        first = item["sample_diffs"][0]
        self.assertIn("status", first["changes"])
        self.assertIsNone(first["changes"]["status"]["before"])
        self.assertEqual(first["changes"]["status"]["after"], "completed")

        # print_report dry-run 分支（差异示例展示）只打印不抛错
        print_report(report, apply=False)

    async def test_legacy_documents_never_mutated_by_transform_helper(self):
        original = _doc("x1", doctor_id="d1", title="标题", status="cancelled")

        transformed, _ = transform_followup_doc(original, "follow_ups", self.BATCH)

        self.assertEqual(original["status"], "cancelled")  # 入参未被改动
        self.assertEqual(transformed["status"], "canceled")
        self.assertIsNot(original, transformed)
