"""T73 随访域自动化处置测试：逾期自动标记、失访自动判定与恢复、随访小结。

覆盖：
1. 规则配置（followup_rule_configs 单例文档）：缺省回默认值（口径待临床确认：
   1 天 / 30 天 / 3 次提醒）、更新合并、非法值 fail-safe 回默认；
2. 逾期自动标记：原子条件更新（open 状态 + 超期天数内联在 update 查询中），
   多 worker 竞争只置一次；手工标记与自动标记来源可区分（metadata.overdue.source）；
3. 失访自动判定：overdue + 超 lost_days + 患者侧提醒投递 >= lost_reminders；
   手工 metadata.overdue 证据保留；
4. 失访人工恢复：lost -> awaiting_fill，恢复信息入 metadata.lost 并写审计；
   恢复后不再被失访扫描命中；
5. 随访小结：complete 一并提交、独立端点写入与覆盖、非 in_review/completed 拒绝、
   存量文档（无 followup_summary 顶层字段）映射为 None（增量兼容）。

真实副本集原子性（并发扫描只置一次）见文件尾 REHAB_TEST_REPLICA_URI 守卫的
集成用例；单测用内存 FakeCollection 打桩（不连库）。
"""

import asyncio
import os
import unittest
from datetime import datetime, timedelta
from uuid import uuid4

from bson import ObjectId, encode
from motor.motor_asyncio import AsyncIOMotorClient

from followup_transaction_fake import FakeTransactionalDatabase

from app.models.health_record import FollowUpRecord
from app.core.exceptions import AppBaseException
from app.schemas.followup import (
    CompleteFollowUpRequest, FollowUpSummaryPayload,
    FollowUpDispositionRulesUpdate,
)
from app.services.followup_service import (
    FollowupService, validated_disposition_rules,
    DEFAULT_DISPOSITION_RULES, DISPOSITION_RULES_COLLECTION, DISPOSITION_RULES_DOC_ID,
    FOLLOWUP_REMINDER_DELIVERIES,
)

# 复用既有随访契约测试的内存集合打桩（同一 FakeTransactionalDatabase 事务回滚双）
from test_followup_service_contract import FakeCollection, FakeCursor, _match


class AsyncFakeCursor(FakeCursor):
    """支持 async for 的游标（扫描服务用 async for 消费候选游标）。"""

    def __aiter__(self):
        self._iterator = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration:
            raise StopAsyncIteration from None


class AsyncFakeCollection(FakeCollection):
    def find(self, query):
        return AsyncFakeCursor([dict(d) for d in self.docs.values() if _match(d, query)])


def _make_service(extra_collections=()):
    names = (FollowUpRecord.collection_name, "medical_timelines", "audit_logs",
             DISPOSITION_RULES_COLLECTION, FOLLOWUP_REMINDER_DELIVERIES,
             *extra_collections)
    collections = {name: AsyncFakeCollection() for name in names}
    service = FollowupService(FakeTransactionalDatabase(collections))
    return service, collections


def _insert_node(collections, *, status="scheduled", days_ago=3, metadata=None,
                 created_by=None):
    record = FollowUpRecord(
        patient_id=str(ObjectId()), created_by=created_by or str(ObjectId()),
        follow_up_type="phone", scheduled_date=datetime.utcnow() - timedelta(days=days_ago),
        questions=[{"question_id": "q1", "question_text": "t", "question_type": "text", "order": 1}],
        metadata=dict(metadata or {}))
    record.status = status
    doc = record.to_mongo()
    return collections[FollowUpRecord.collection_name].docs, doc


async def _insert_doc(collections, doc):
    # FakeCollection 按 to_mongo 的 ObjectId _id 原样存键；断言用 docs[ObjectId(followup_id)]
    await collections[FollowUpRecord.collection_name].insert_one(dict(doc))


def _deliver_reminders(collections, followup_id, count):
    ledger = collections[FOLLOWUP_REMINDER_DELIVERIES]
    for index in range(count):
        ledger.docs[ObjectId()] = {
            "_id": ObjectId(), "followup_id": str(followup_id), "slot": "patient",
            "status": "persisted", "policy": "inapp-24h-v1", "index": index}


def _audit_actions(collections):
    return [doc["action"] for doc in collections["audit_logs"].docs.values()]


class DispositionRulesTests(unittest.IsolatedAsyncioTestCase):
    async def test_defaults_apply_when_no_document(self):
        service, _ = _make_service()
        rules = await service.get_disposition_rules()
        self.assertEqual(rules, DEFAULT_DISPOSITION_RULES)

    async def test_update_merges_and_persists(self):
        service, collections = _make_service()
        rules = await service.update_disposition_rules(FollowUpDispositionRulesUpdate(
            overdue_days=3, lost_days=45, enabled=False))
        self.assertEqual(rules, {"enabled": False, "overdue_days": 3, "lost_days": 45,
                                 "lost_reminders": 3, "scan_batch": 200})
        stored = await service.get_disposition_rules()
        self.assertEqual(stored, rules)
        self.assertIn(DISPOSITION_RULES_DOC_ID, collections[DISPOSITION_RULES_COLLECTION].docs)

    async def test_invalid_values_fall_back_to_defaults(self):
        # 非法/越界/布尔伪装的阈值一律回默认（fail-safe，不抛错）
        self.assertEqual(validated_disposition_rules({
            "overdue_days": -1, "lost_days": 0, "lost_reminders": "3",
            "scan_batch": 5000, "enabled": False}),
            {"enabled": False, "overdue_days": 1, "lost_days": 30,
             "lost_reminders": 3, "scan_batch": 200})
        self.assertEqual(validated_disposition_rules(None), DEFAULT_DISPOSITION_RULES)
        self.assertEqual(validated_disposition_rules({"enabled": True})["enabled"], True)


class AutomatedOverdueTests(unittest.IsolatedAsyncioTestCase):
    async def test_scan_marks_past_due_open_nodes_as_automated_overdue(self):
        service, collections = _make_service()
        docs = collections[FollowUpRecord.collection_name].docs
        await _insert_doc(collections, _insert_node(collections, status="scheduled", days_ago=3)[1])
        await _insert_doc(collections, _insert_node(collections, status="awaiting_fill", days_ago=2)[1])
        await _insert_doc(collections, _insert_node(collections, status="scheduled", days_ago=-1)[1])  # 未来
        await _insert_doc(collections, _insert_node(collections, status="completed", days_ago=9)[1])
        result = await service.run_automated_disposition_scan()
        self.assertEqual(result["overdue_marked"], 2)
        marked = [doc for doc in docs.values() if doc["status"] == "overdue"]
        self.assertEqual(len(marked), 2)
        for doc in marked:
            marker = doc["metadata"]["overdue"]
            self.assertEqual(marker["source"], "automated")
            self.assertIsNone(marker["operator_id"])
            self.assertEqual(marker["rule_overdue_days"], 1)
        # 时间线同步更新
        timelines = collections["medical_timelines"].docs
        self.assertTrue(any(item["metadata"]["status"] == "overdue" for item in timelines.values()))

    async def test_automated_mark_is_atomic_and_idempotent(self):
        # 条件更新内联全部前置条件：状态已被并发改动时 matched_count==0，不重复计数
        service, collections = _make_service()
        docs, doc = _insert_node(collections, status="scheduled", days_ago=3)
        await _insert_doc(collections, doc)
        now = datetime.utcnow()
        candidate = next(iter(docs.values()))
        self.assertTrue(await service._automated_overdue_mark(candidate, now, DEFAULT_DISPOSITION_RULES))
        stale = dict(candidate)
        stale["status"] = "canceled"  # 模拟另一 worker 先改为 canceled
        self.assertFalse(await service._automated_overdue_mark(stale, now, DEFAULT_DISPOSITION_RULES))
        # 幂等：已置 overdue 的节点不在候选游标内，重扫不再计数
        result = await service.run_automated_disposition_scan(now=now)
        self.assertEqual(result["overdue_marked"], 0)

    async def test_manual_marker_keeps_operator_and_automated_keeps_source(self):
        service, collections = _make_service()
        docs, manual = _insert_node(collections, status="scheduled", days_ago=3,
                                    metadata={"overdue": {"marked_at": datetime.utcnow(),
                                                          "operator_id": "doc-1"}})
        await _insert_doc(collections, manual)
        followup_id = next(iter(docs))
        await service.mark_overdue(str(followup_id), operator_id="doc-1", reason="手工确认")
        self.assertEqual(docs[ObjectId(followup_id)]["metadata"]["overdue"]["source"], "manual")
        self.assertEqual(docs[ObjectId(followup_id)]["metadata"]["overdue"]["operator_id"], "doc-1")


class AutomatedLostTests(unittest.IsolatedAsyncioTestCase):
    async def test_lost_requires_threshold_days_and_reminders(self):
        service, collections = _make_service()
        marked_at = datetime.utcnow() - timedelta(days=40)
        docs, doc = _insert_node(collections, status="overdue", days_ago=40, metadata={
            "overdue": {"marked_at": marked_at, "operator_id": "doc-9", "source": "manual"}})
        await _insert_doc(collections, doc)
        followup_id = str(next(iter(docs)))
        _deliver_reminders(collections, followup_id, 2)  # 默认阈值 3 次未达
        result = await service.run_automated_disposition_scan()
        self.assertEqual(result["lost_marked"], 0)
        self.assertEqual(next(iter(docs.values()))["status"], "overdue")
        _deliver_reminders(collections, followup_id, 1)  # 累计 3 次
        result = await service.run_automated_disposition_scan()
        self.assertEqual(result["lost_marked"], 1)
        stored = docs[ObjectId(followup_id)]
        self.assertEqual(stored["status"], "lost")
        self.assertEqual(stored["metadata"]["lost"]["source"], "automated")
        self.assertEqual(stored["metadata"]["lost"]["delivered_reminders"], 3)
        # 手工逾期标记证据保留
        self.assertEqual(stored["metadata"]["overdue"]["source"], "manual")

    async def test_lost_window_counts_from_overdue_marked_at(self):
        # 计划日已超 30 天，但刚刚才标记逾期：失访窗口从 marked_at 起算，不命中
        service, collections = _make_service()
        docs, doc = _insert_node(collections, status="overdue", days_ago=40, metadata={
            "overdue": {"marked_at": datetime.utcnow(), "operator_id": "doc-9",
                        "source": "manual"}})
        await _insert_doc(collections, doc)
        _deliver_reminders(collections, str(next(iter(docs))), 10)
        result = await service.run_automated_disposition_scan()
        self.assertEqual(result["lost_marked"], 0)
        self.assertEqual(next(iter(docs.values()))["status"], "overdue")

    async def test_recent_overdue_not_lost_before_lost_days(self):
        service, collections = _make_service()
        docs, doc = _insert_node(collections, status="overdue", days_ago=5)
        await _insert_doc(collections, doc)
        _deliver_reminders(collections, str(next(iter(docs))), 10)
        result = await service.run_automated_disposition_scan()
        self.assertEqual(result["lost_marked"], 0)
        self.assertEqual(next(iter(docs.values()))["status"], "overdue")

    async def test_atomic_lost_mark_rejects_concurrent_status_change(self):
        service, collections = _make_service()
        docs, doc = _insert_node(collections, status="overdue", days_ago=40)
        await _insert_doc(collections, doc)
        candidate = next(iter(docs.values()))
        stale = dict(candidate)
        stale["status"] = "awaiting_fill"
        now = datetime.utcnow()
        self.assertTrue(await service._automated_lost_mark(
            candidate, now, DEFAULT_DISPOSITION_RULES, 3))
        self.assertFalse(await service._automated_lost_mark(
            stale, now, DEFAULT_DISPOSITION_RULES, 3))


class LostRestoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_restore_moves_lost_to_awaiting_fill_with_audit(self):
        service, collections = _make_service()
        docs, doc = _insert_node(collections, status="overdue", days_ago=40)
        await _insert_doc(collections, doc)
        followup_id = str(next(iter(docs)))
        _deliver_reminders(collections, followup_id, 3)
        await service.run_automated_disposition_scan()
        self.assertEqual(docs[ObjectId(followup_id)]["status"], "lost")

        restored = await service.restore_lost(followup_id, operator_id="doc-2", reason="患者恢复联系")
        self.assertEqual(restored.status, "awaiting_fill")
        marker = docs[ObjectId(followup_id)]["metadata"]["lost"]
        self.assertEqual(marker["restored_by"], "doc-2")
        self.assertEqual(marker["restore_reason"], "患者恢复联系")
        self.assertIn("followup_lost_restore", _audit_actions(collections))

    async def test_restored_node_gets_a_fresh_lost_window(self):
        service, collections = _make_service()
        docs, doc = _insert_node(collections, status="overdue", days_ago=40)
        await _insert_doc(collections, doc)
        followup_id = str(next(iter(docs)))
        _deliver_reminders(collections, followup_id, 3)
        await service.run_automated_disposition_scan()
        await service.restore_lost(followup_id, operator_id="doc-2", reason="恢复")
        # 恢复后的同一轮扫描会先重新置 overdue（观察窗口起算点重置为标记时间），
        # 失访窗口未满不再立即判失访
        result = await service.run_automated_disposition_scan()
        self.assertEqual(result["overdue_marked"], 1)
        self.assertEqual(result["lost_marked"], 0)
        self.assertEqual(docs[ObjectId(followup_id)]["status"], "overdue")
        # 重扫稳定：不再产生新的流转
        result = await service.run_automated_disposition_scan()
        self.assertEqual(result, {"enabled": True, "overdue_marked": 0, "lost_marked": 0})

    async def test_restore_rejects_non_lost_nodes(self):
        service, collections = _make_service()
        docs, doc = _insert_node(collections, status="scheduled", days_ago=3)
        await _insert_doc(collections, doc)
        followup_id = str(next(iter(docs)))
        with self.assertRaises(AppBaseException):
            await service.restore_lost(followup_id, operator_id="doc-2", reason="误操作")


class FollowUpSummaryTests(unittest.IsolatedAsyncioTestCase):
    SUMMARY = FollowUpSummaryPayload(conclusion="血压控制平稳",
                                     next_plan_suggestion="两周后电话复访",
                                     abnormal_findings="夜间心率偏高")

    async def test_complete_with_summary_persists_structured_fields(self):
        service, collections = _make_service()
        docs, doc = _insert_node(collections, status="awaiting_fill", days_ago=1,
                                 created_by="doc-3")
        await _insert_doc(collections, doc)
        followup_id = str(next(iter(docs)))
        response = await service.complete_followup(followup_id, CompleteFollowUpRequest(
            expected_version=0, summary=self.SUMMARY), operator_id="doc-3")
        self.assertEqual(response.followup_summary["conclusion"], "血压控制平稳")
        stored = docs[ObjectId(followup_id)]
        self.assertEqual(stored["followup_summary"]["conclusion"], "血压控制平稳")
        self.assertEqual(stored["followup_summary"]["next_plan_suggestion"], "两周后电话复访")
        self.assertEqual(stored["followup_summary"]["abnormal_findings"], "夜间心率偏高")
        self.assertEqual(stored["followup_summary"]["recorded_by"], "doc-3")

    async def test_set_summary_on_completed_and_overwrite_keeps_audit(self):
        service, collections = _make_service()
        docs, doc = _insert_node(collections, status="completed", days_ago=2)
        await _insert_doc(collections, doc)
        followup_id = str(next(iter(docs)))
        first = await service.set_followup_summary(followup_id, self.SUMMARY, operator_id="doc-4")
        self.assertEqual(first.followup_summary["conclusion"], "血压控制平稳")
        overwrite = await service.set_followup_summary(followup_id, FollowUpSummaryPayload(
            conclusion="结论修订"), operator_id="doc-4")
        self.assertEqual(overwrite.followup_summary["conclusion"], "结论修订")
        self.assertIsNone(overwrite.followup_summary["next_plan_suggestion"])
        self.assertEqual(_audit_actions(collections).count("followup_summary_update"), 2)

    async def test_summary_rejected_for_unfilled_nodes(self):
        service, collections = _make_service()
        docs, doc = _insert_node(collections, status="scheduled", days_ago=0)
        await _insert_doc(collections, doc)
        followup_id = str(next(iter(docs)))
        with self.assertRaises(AppBaseException):
            await service.set_followup_summary(followup_id, self.SUMMARY, operator_id="doc-4")

    async def test_legacy_document_without_summary_maps_to_none(self):
        service, collections = _make_service()
        docs, doc = _insert_node(collections, status="completed", days_ago=2)
        await _insert_doc(collections, doc)
        followup_id = str(next(iter(docs)))
        response = await service.get_followup_record(followup_id)
        self.assertIsNone(response.followup_summary)
        # FollowUpRecordDB 能直接校验存量文档（无增量字段）
        from app.schemas.followup import FollowUpRecordDB
        FollowUpRecordDB(**{**doc, "_id": docs[ObjectId(followup_id)]["_id"]})


@unittest.skipUnless(os.environ.get("REHAB_TEST_REPLICA_URI"),
                     "set REHAB_TEST_REPLICA_URI to an isolated local replica set")
class DispositionReplicaTests(unittest.IsolatedAsyncioTestCase):
    """真实副本集上的多 worker 并发安全：两个服务实例并发扫描，节点只标记一次。"""

    async def asyncSetUp(self):
        uri = os.environ["REHAB_TEST_REPLICA_URI"]
        if not uri.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")):
            self.fail("test URI must use a local explicit port")
        self.client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=3000)
        self.db = self.client["rehab_disp_" + uuid4().hex]
        self.collection = self.db[FollowUpRecord.collection_name]

    async def asyncTearDown(self):
        self.client.drop_database(self.db.name)
        self.client.close()

    async def _insert(self, *, status, days_ago):
        record = FollowUpRecord(
            patient_id=str(ObjectId()), created_by=str(ObjectId()), follow_up_type="phone",
            scheduled_date=datetime.utcnow() - timedelta(days=days_ago))
        record.status = status
        await self.collection.insert_one(dict(record.to_mongo()))
        return str(record._id)

    async def test_concurrent_scans_mark_each_node_once(self):
        service_a, service_b = FollowupService(self.db), FollowupService(self.db)
        await self._insert(status="scheduled", days_ago=3)
        await self._insert(status="overdue", days_ago=40)
        followup_id = str((await self.collection.find_one({}))["_id"])
        for _ in range(3):
            await self.db[FOLLOWUP_REMINDER_DELIVERIES].insert_one(
                {"followup_id": followup_id, "slot": "patient", "status": "persisted"})
        results = await asyncio.gather(
            service_a.run_automated_disposition_scan(),
            service_b.run_automated_disposition_scan())
        overdue_marked = sum(result["overdue_marked"] for result in results)
        lost_marked = sum(result["lost_marked"] for result in results)
        self.assertEqual(overdue_marked, 1)
        self.assertEqual(lost_marked, 1)
        self.assertEqual(await self.collection.count_documents({"status": "overdue"}), 0)
        self.assertEqual(await self.collection.count_documents({"status": "lost"}), 1)
        stored = await self.collection.find_one({"status": "lost"})
        self.assertEqual(stored["metadata"]["lost"]["delivered_reminders"], 3)
