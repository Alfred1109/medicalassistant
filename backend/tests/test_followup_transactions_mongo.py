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
from app.schemas.followup import CancelFollowUpRequest, CompleteFollowUpRequest, FollowUpRecordUpdate, RescheduleFollowUpRequest
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
        self.assertIn(terminal["status"], {"completed", "canceled"})
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
