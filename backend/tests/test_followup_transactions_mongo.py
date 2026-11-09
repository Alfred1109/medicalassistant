"""Real replica-set atomicity tests, enabled only for an explicitly provided local test URI."""
import asyncio
import os
import unittest
from copy import deepcopy
from datetime import datetime, timedelta
from uuid import uuid4
from unittest.mock import patch

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.exceptions import AppBaseException
from app.models.health_record import FollowUpRecord, MedicalTimeline
from app.schemas.followup import (
    CancelFollowUpRequest, CompleteFollowUpRequest, FollowUpRecordUpdate,
    ReEvaluateFollowUpRequest, RescheduleFollowUpRequest,
    ReviewDecision, ReviewFollowUpRequest,
)
from app.services.followup_service import FollowupService


URI = os.environ.get("REHAB_TEST_REPLICA_URI")
STANDALONE_URI = os.environ.get("REHAB_TEST_STANDALONE_URI")


@unittest.skipUnless(URI, "set REHAB_TEST_REPLICA_URI to an isolated local replica set")
class FollowupMongoTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if not URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")):
            self.fail("test URI must use a local explicit port")
        self.client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.client["rehab_txn_" + uuid4().hex]
        self.service = FollowupService(self.db)
        record = FollowUpRecord(
            patient_id=str(ObjectId()), created_by=str(ObjectId()),
            scheduled_date=datetime.utcnow() + timedelta(days=1), follow_up_type="phone",
            questions=[{"question_id": "q1", "question_text": "test", "question_type": "text", "order": 1}],
            reminder_settings={"enabled": True, "minutes_before": 60},
            answers=[{"question_id": "q1", "answer_value": "old"}])
        self.doc = record.to_mongo()
        self.doc.update(provider_id=str(ObjectId()), template_id="template", reminder_before=60,
                        form_binding={"questionnaire_id": 1}, fill_task_ids=[ObjectId()],
                        effective_response={"response_id": "old"}, review={"old": True})
        await self.db.followup_records.insert_one(deepcopy(self.doc))
        await self.db.medical_timelines.insert_one(MedicalTimeline.from_follow_up(record).to_mongo())
        self.followup_id = str(record._id)
        self.request = CancelFollowUpRequest(cancel_reason="reschedule", canceled_by=record.created_by,
                                            reschedule_date=datetime.utcnow() + timedelta(days=2))

    async def asyncTearDown(self):
        await self.client.drop_database(self.db.name)
        self.client.close()

    async def test_same_request_concurrent_and_sequential_retry_has_one_successor(self):
        responses = await asyncio.gather(*[
            self.service.cancel_followup(self.followup_id, self.request) for _ in range(8)])
        await self.service.cancel_followup(self.followup_id, self.request.model_copy())
        self.assertEqual(len({response.next_follow_up_id for response in responses}), 1)
        self.assertEqual(await self.db.followup_records.count_documents({}), 2)
        self.assertEqual(await self.db.medical_timelines.count_documents({}), 2)
        child = await self.db.followup_records.find_one({"previous_visit_id": self.followup_id})
        for key in ("provider_id", "template_id", "reminder_before", "reminder_settings", "form_binding", "questions"):
            self.assertEqual(child[key], self.doc[key])
        self.assertEqual(child["answers"], [])
        for key in ("effective_response", "review", "fill_task_ids", "completion_data"):
            self.assertNotIn(key, child)

    async def test_different_cancel_requests_compete_one_conflicts(self):
        other = self.request.model_copy(update={"cancel_reason": "other"})
        results = await asyncio.gather(
            self.service.cancel_followup(self.followup_id, self.request),
            self.service.cancel_followup(self.followup_id, other), return_exceptions=True)
        self.assertEqual(sum(isinstance(value, AppBaseException) and value.status_code == 409 for value in results), 1)
        self.assertEqual(await self.db.followup_records.count_documents({}), 2)

    async def test_failure_after_successor_insert_rolls_back_all_documents(self):
        before = await self.db.followup_records.find_one({"_id": self.doc["_id"]})
        original = self.service._create_successor
        async def fail_after_insert(*args, **kwargs):
            await original(*args, **kwargs)
            raise RuntimeError("injected before parent link")
        with patch.object(self.service, "_create_successor", side_effect=fail_after_insert):
            with self.assertRaises(RuntimeError):
                await self.service.cancel_followup(self.followup_id, self.request)
        self.assertEqual(await self.db.followup_records.find_one({"_id": self.doc["_id"]}), before)
        self.assertEqual(await self.db.followup_records.count_documents({}), 1)
        self.assertEqual(await self.db.medical_timelines.count_documents({}), 1)
        await self.service.cancel_followup(self.followup_id, self.request)
        self.assertEqual(await self.db.followup_records.count_documents({}), 2)

    async def test_complete_cancel_race_cannot_reopen_terminal_node(self):
        results = await asyncio.gather(
            self.service.cancel_followup(self.followup_id, self.request),
            self.service.complete_followup(self.followup_id, CompleteFollowUpRequest()), return_exceptions=True)
        self.assertEqual(sum(isinstance(value, AppBaseException) and value.status_code == 409 for value in results), 1)
        terminal = await self.db.followup_records.find_one({"_id": self.doc["_id"]})
        # FU01 S5：手工录入只到 in_review（completed 只能由审阅通过置达）
        self.assertIn(terminal["status"], {"in_review", "canceled"})
        for operation in (
            self.service.update_followup_record(self.followup_id, FollowUpRecordUpdate(status="scheduled")),
            self.service.reschedule_followup(self.followup_id, RescheduleFollowUpRequest(new_date=datetime.utcnow(), reason="retry")),
        ):
            with self.assertRaises(AppBaseException):
                await operation

    async def test_default_completion_time_does_not_break_request_retry(self):
        first = await self.service.complete_followup(self.followup_id, CompleteFollowUpRequest())
        second = await self.service.complete_followup(self.followup_id, CompleteFollowUpRequest())
        self.assertEqual(first.actual_date.replace(microsecond=first.actual_date.microsecond // 1000 * 1000), second.actual_date)
        self.assertEqual(await self.db.followup_records.count_documents({}), 1)

    async def test_missing_original_timeline_is_created_in_same_transaction(self):
        await self.db.medical_timelines.delete_many({})
        await self.service.cancel_followup(self.followup_id, self.request)
        self.assertEqual(await self.db.medical_timelines.count_documents({}), 2)
        original_timeline = await self.db.medical_timelines.find_one({"related_ids": self.followup_id})
        self.assertEqual(original_timeline["metadata"]["status"], "canceled")

    async def test_each_late_failure_rolls_back_parent_child_and_timelines(self):
        before = await self.db.followup_records.find_one({"_id": self.doc["_id"]})
        for method in ("_write_node", "_write_timeline"):
            original = getattr(self.service, method)
            async def fail_after_write(*args, **kwargs):
                await original(*args, **kwargs)
                raise RuntimeError("injected after " + method)
            with self.subTest(method=method):
                with patch.object(self.service, method, side_effect=fail_after_write):
                    with self.assertRaises(RuntimeError):
                        await self.service.cancel_followup(self.followup_id, self.request)
                self.assertEqual(await self.db.followup_records.find_one({"_id": self.doc["_id"]}), before)
                self.assertEqual(await self.db.followup_records.count_documents({}), 1)
                self.assertEqual(await self.db.medical_timelines.count_documents({}), 1)

    # -------- FU01 S5/S6 事务：审阅、手工录入审计、复评（副本集真实并发/回滚） --------

    async def _seed_in_review(self):
        """把节点置为 in_review（模拟填报 confirm 后的待审阅状态）。"""
        await self.db.followup_records.update_one(
            {"_id": self.doc["_id"]},
            {"$set": {"status": "in_review",
                      "effective_response": {"task_id": str(ObjectId()), "response_id": "resp-1"}}})
        self.doc = await self.db.followup_records.find_one({"_id": self.doc["_id"]})

    async def test_review_approval_and_cancel_race_one_conflicts(self):
        """in_review 节点上审阅通过与取消并发：一个 409，节点停在唯一终态。"""
        await self._seed_in_review()
        results = await asyncio.gather(
            self.service.review_followup(
                self.followup_id, ReviewFollowUpRequest(decision=ReviewDecision.APPROVED),
                reviewer_id=self.doc["provider_id"], reviewer_role="doctor"),
            self.service.cancel_followup(self.followup_id, CancelFollowUpRequest(cancel_reason="x")),
            return_exceptions=True)
        self.assertEqual(sum(isinstance(v, AppBaseException) and v.status_code == 409 for v in results), 1)
        terminal = await self.db.followup_records.find_one({"_id": self.doc["_id"]})
        self.assertIn(terminal["status"], {"completed", "canceled"})
        # 审计与节点写入同事务：胜出方只留一条审计
        self.assertEqual(await self.db.audit_logs.count_documents({}), 1)

    async def test_review_failure_rolls_back_node_history_and_audit(self):
        """审阅写节点后注入失败：状态、review.history 与审计整体回滚。"""
        await self._seed_in_review()
        before = await self.db.followup_records.find_one({"_id": self.doc["_id"]})
        original = self.service._write_node
        async def fail_after_write(*args, **kwargs):
            await original(*args, **kwargs)
            raise RuntimeError("injected after review write")
        with patch.object(self.service, "_write_node", side_effect=fail_after_write):
            with self.assertRaises(RuntimeError):
                await self.service.review_followup(
                    self.followup_id, ReviewFollowUpRequest(decision=ReviewDecision.APPROVED),
                    reviewer_id=self.doc["provider_id"], reviewer_role="doctor")
        self.assertEqual(
            await self.db.followup_records.find_one({"_id": self.doc["_id"]}), before)
        self.assertEqual(await self.db.audit_logs.count_documents({}), 0)
        # 失败后重试成功
        response = await self.service.review_followup(
            self.followup_id, ReviewFollowUpRequest(decision=ReviewDecision.APPROVED),
            reviewer_id=self.doc["provider_id"], reviewer_role="doctor")
        self.assertEqual(response.status.value, "completed")
        self.assertEqual(await self.db.audit_logs.count_documents({}), 1)

    async def test_review_returned_clears_effective_response_atomically(self):
        await self._seed_in_review()
        response = await self.service.review_followup(
            self.followup_id, ReviewFollowUpRequest(decision=ReviewDecision.RETURNED),
            reviewer_id=self.doc["provider_id"], reviewer_role="doctor")
        self.assertEqual(response.status.value, "awaiting_fill")
        node = await self.db.followup_records.find_one({"_id": self.doc["_id"]})
        self.assertIsNone(node.get("effective_response"))
        self.assertEqual(node["review"]["history"][0]["decision"], "returned")
        self.assertEqual(await self.db.audit_logs.count_documents({}), 1)

    async def test_re_evaluate_concurrent_and_retry_has_one_successor(self):
        """复评并发与重试：同一后继节点、原节点链接唯一、审计不重复。"""
        await self.db.followup_records.update_one(
            {"_id": self.doc["_id"]}, {"$set": {"status": "completed"}})
        self.doc = await self.db.followup_records.find_one({"_id": self.doc["_id"]})
        request = ReEvaluateFollowUpRequest(
            scheduled_date=datetime.utcnow() + timedelta(days=14), reason="按计划复评")
        responses = await asyncio.gather(*[
            self.service.re_evaluate_followup(self.followup_id, request, operator_id="op")
            for _ in range(6)])
        retry = await self.service.re_evaluate_followup(self.followup_id, request.model_copy(), operator_id="op")
        self.assertEqual(len({response.id for response in responses}), 1)
        self.assertEqual(retry.id, responses[0].id)
        self.assertEqual(await self.db.followup_records.count_documents({}), 2)
        child = await self.db.followup_records.find_one({"previous_visit_id": self.followup_id})
        # 复评继承处方配置；答案/结果/审阅/任务引用从空状态开始；visit_code 不继承
        for key in ("provider_id", "template_id", "reminder_before", "form_binding", "questions"):
            self.assertEqual(child[key], self.doc[key])
        self.assertNotIn("visit_code", child)
        self.assertNotIn("effective_response", child)
        self.assertNotIn("review", child)
        self.assertNotIn("fill_task_ids", child)
        parent = await self.db.followup_records.find_one({"_id": self.doc["_id"]})
        self.assertEqual(parent["next_visit_id"], str(child["_id"]))
        self.assertEqual(await self.db.audit_logs.count_documents({}), 1)

    async def test_re_evaluate_conflicting_requests_one_wins(self):
        """不同复评请求并发：一个 409，库里只有一个后继节点。"""
        await self.db.followup_records.update_one(
            {"_id": self.doc["_id"]}, {"$set": {"status": "completed"}})
        results = await asyncio.gather(
            self.service.re_evaluate_followup(
                self.followup_id,
                ReEvaluateFollowUpRequest(scheduled_date=datetime.utcnow() + timedelta(days=7)),
                operator_id="op"),
            self.service.re_evaluate_followup(
                self.followup_id,
                ReEvaluateFollowUpRequest(scheduled_date=datetime.utcnow() + timedelta(days=10),
                                          reason="other"),
                operator_id="op"),
            return_exceptions=True)
        self.assertEqual(sum(isinstance(v, AppBaseException) and v.status_code == 409 for v in results), 1)
        self.assertEqual(await self.db.followup_records.count_documents({}), 2)

    async def test_manual_entry_writes_audit_in_same_transaction(self):
        """手工录入（D-2）：节点转 in_review 与审计同事务落库。"""
        response = await self.service.complete_followup(
            self.followup_id, CompleteFollowUpRequest(notes="电话录入"), operator_id="op")
        self.assertEqual(response.status.value, "in_review")
        node = await self.db.followup_records.find_one({"_id": self.doc["_id"]})
        self.assertEqual(node["completion_data"]["source"], "manual_entry")
        # 手工录入不创建/不改写表单答卷状态：种子节点既有的 effective_response 原样保留
        self.assertEqual(node["effective_response"], {"response_id": "old"})
        audit = await self.db.audit_logs.find_one({})
        self.assertEqual(audit["action"], "followup_manual_entry")
        self.assertEqual(audit["resource_id"], self.followup_id)


@unittest.skipUnless(STANDALONE_URI, "set REHAB_TEST_STANDALONE_URI to an isolated local standalone")
class FollowupStandaloneRejectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_transaction_required_without_any_partial_write(self):
        if not STANDALONE_URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")):
            self.fail("test URI must use a local explicit port")
        client = AsyncIOMotorClient(STANDALONE_URI, serverSelectionTimeoutMS=3000)
        db = client["rehab_txn_" + uuid4().hex]
        try:
            record = FollowUpRecord(patient_id=str(ObjectId()), created_by=str(ObjectId()),
                                    scheduled_date=datetime.utcnow())
            await db.followup_records.insert_one(record.to_mongo())
            before = await db.followup_records.find_one({})
            service = FollowupService(db)
            with self.assertRaises(AppBaseException) as error:
                await service.cancel_followup(record._id, CancelFollowUpRequest(
                    cancel_reason="test", reschedule_date=datetime.utcnow() + timedelta(days=1)))
            self.assertEqual(error.exception.status_code, 503)
            self.assertEqual(error.exception.error_code, "FOLLOWUP_TRANSACTION_UNAVAILABLE")
            self.assertEqual(await db.followup_records.find_one({}), before)
            self.assertEqual(await db.followup_records.count_documents({}), 1)
            self.assertEqual(await db.medical_timelines.count_documents({}), 0)
        finally:
            await client.drop_database(db.name)
            client.close()
