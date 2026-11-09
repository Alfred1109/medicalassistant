"""Real Mongo replica-set verification; only uses a fresh synthetic database."""
import asyncio
import os
import unittest
from datetime import datetime, timedelta
from uuid import uuid4
from unittest.mock import patch

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo.errors import OperationFailure

from app.core.exceptions import AppBaseException
from app.models.health_record import FollowUpRecord
from app.schemas.followup import (
    CancelFollowUpRequest, CompleteFollowUpRequest, ReviewFollowUpRequest)
from app.services.followup_service import FollowupService
from app.integrations.forms import service, models
from test_integration_forms_contract import FakeRemote, make_remote_client, make_operator, OPERATOR_ID, PATIENT_ID


@unittest.skipUnless(os.environ.get("REHAB_TEST_MONGO_URI"), "isolated replica-set URI not supplied")
class FormsMongoTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        fill_feature = patch.dict(os.environ, {"FORM_PLATFORM_FILL_ENABLED": "true"})
        fill_feature.start()
        self.addCleanup(fill_feature.stop)
        uri = os.environ["REHAB_TEST_MONGO_URI"]
        if not uri.startswith("mongodb://127.0.0.1:"):
            raise RuntimeError("only an explicit loopback test instance is allowed")
        self.client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=4000)
        self.db_name = "rehab_forms_txn_" + uuid4().hex
        self.db = self.client[self.db_name]
        hello = await self.client.admin.command("hello")
        self.assertTrue(hello.get("setName"), "replica set required")
        self.patient_id = str(ObjectId())
        await self.db.users.insert_one({"_id": ObjectId(self.patient_id), "role": "patient",
                                        "practitioners": [OPERATOR_ID]})
        record = FollowUpRecord(patient_id=self.patient_id, created_by=OPERATOR_ID,
                                scheduled_date=datetime.utcnow() + timedelta(days=1),
                                follow_up_type="phone", status="awaiting_fill")
        record.visit_code = "V1"
        self.visit_id = record._id
        await self.db.followup_records.insert_one(record.to_mongo())
        self.remote = FakeRemote()
        self.remote_client = make_remote_client(self.remote)
        self.operator = make_operator()
        self.task = await service.create_fill_task(self.db, self.remote_client, self.operator, {
            "patient_id": self.patient_id, "followup_visit_id": self.visit_id,
            "remote_project_id": 1, "remote_center_id": 2, "remote_subject_id": 3,
            "remote_questionnaire_id": 4, "remote_operator_user_id": 7,
            "allowed_origin": "https://rehab.example", "visit_code": "V1"})
        self.task_id = self.task["id"]
        self.remote.session_body.update(status="submitted", response_id=42)

    async def asyncTearDown(self):
        if hasattr(self, "db_name"):
            await self.client.drop_database(self.db_name)
        if hasattr(self, "client"):
            self.client.close()

    async def test_confirmation_task_write_failure_rolls_back_real_node_write(self):
        original = AsyncIOMotorCollection.update_one

        async def fail_task_write(collection, query, update, **kwargs):
            if collection.name == models.COLLECTION_NAME and update.get("$set", {}).get("status") == "confirmed":
                raise OperationFailure("injected confirmation failure", code=2)
            return await original(collection, query, update, **kwargs)

        with patch.object(AsyncIOMotorCollection, "update_one", fail_task_write):
            with self.assertRaises(AppBaseException) as raised:
                await service.confirm_fill_task(self.db, self.remote_client, self.task_id, self.operator)
        self.assertEqual(raised.exception.status_code, 503)
        visit = await self.db.followup_records.find_one({"_id": ObjectId(self.visit_id)})
        task = await self.db[models.COLLECTION_NAME].find_one({"_id": ObjectId(self.task_id)})
        self.assertEqual(visit["status"], "awaiting_fill")
        self.assertNotIn("effective_response", visit)
        self.assertNotIn("current_evidence", visit)
        self.assertNotIn("submission_history", visit)
        self.assertNotEqual(task["status"], "confirmed")


    async def test_cancel_commits_after_confirmation_read_and_cannot_be_overwritten(self):
        original = AsyncIOMotorCollection.update_one
        reached_write = asyncio.Event()
        release_write = asyncio.Event()
        paused = False

        async def pause_confirmation(collection, query, update, **kwargs):
            nonlocal paused
            if (not paused and collection.name == "followup_records" and
                    update.get("$set", {}).get("status") == "in_review"):
                paused = True
                reached_write.set()
                await asyncio.wait_for(release_write.wait(), timeout=10)
            return await original(collection, query, update, **kwargs)

        with patch.object(AsyncIOMotorCollection, "update_one", pause_confirmation):
            confirmation = asyncio.create_task(service.confirm_fill_task(
                self.db, self.remote_client, self.task_id, self.operator))
            try:
                await asyncio.wait_for(reached_write.wait(), timeout=10)
                await FollowupService(self.db).cancel_followup(self.visit_id, CancelFollowUpRequest(
                    cancel_reason="synthetic concurrent cancellation", canceled_by=OPERATOR_ID))
            finally:
                release_write.set()
            with self.assertRaises(AppBaseException) as raised:
                await confirmation
        self.assertEqual(raised.exception.status_code, 409)
        visit = await self.db.followup_records.find_one({"_id": ObjectId(self.visit_id)})
        task = await self.db[models.COLLECTION_NAME].find_one({"_id": ObjectId(self.task_id)})
        self.assertEqual(visit["status"], "canceled")
        self.assertNotIn("effective_response", visit)
        self.assertNotEqual(task["status"], "confirmed")

    async def test_manual_return_external_confirmation_has_only_external_current_evidence(self):
        followups = FollowupService(self.db)
        node = await followups.get_followup_record(self.visit_id)
        submitted = await followups.complete_followup(self.visit_id,
            CompleteFollowUpRequest(expected_version=node.mutation_version,
                notes="manual result", follow_up_result="old manual result"), operator_id=OPERATOR_ID)
        returned = await followups.review_followup(self.visit_id,
            ReviewFollowUpRequest(expected_version=submitted.mutation_version, decision="returned"),
            reviewer_id=OPERATOR_ID)
        await service.confirm_fill_task(self.db, self.remote_client, self.task_id, self.operator)
        current = await followups.get_followup_record(self.visit_id)
        self.assertEqual(current.current_evidence["source"], "external_form")
        self.assertIsNone(current.completion_data)
        self.assertIsNone(current.follow_up_result)
        self.assertEqual(current.answers, [])
        self.assertEqual(current.effective_response["response_id"], 42)
        self.assertEqual([entry["source"] for entry in current.submission_history],
                         ["manual_entry", "external_form"])
        self.assertEqual(current.submission_history[0]["snapshot"]["notes"], "manual result")
        self.assertEqual(current.submission_history[-1]["confirmation"]["response_id"], 42)
        self.assertEqual(current.submission_history[-1]["submitted_by"], OPERATOR_ID)
        self.assertEqual(returned.review["history"][0]["current_evidence"]["source"], "manual_entry")
        approved = await followups.review_followup(self.visit_id,
            ReviewFollowUpRequest(expected_version=current.mutation_version, decision="approved"),
            reviewer_id=OPERATOR_ID)
        self.assertEqual(approved.review["history"][-1]["verified_confirmation"]["response_id"], 42)

    async def test_external_return_manual_submission_has_only_manual_current_evidence(self):
        followups = FollowupService(self.db)
        await service.confirm_fill_task(self.db, self.remote_client, self.task_id, self.operator)
        current = await followups.get_followup_record(self.visit_id)
        returned = await followups.review_followup(self.visit_id,
            ReviewFollowUpRequest(expected_version=current.mutation_version, decision="returned"),
            reviewer_id=OPERATOR_ID)
        manual = await followups.complete_followup(self.visit_id,
            CompleteFollowUpRequest(expected_version=returned.mutation_version, notes="new manual"),
            operator_id=OPERATOR_ID)
        self.assertEqual(manual.current_evidence["source"], "manual_entry")
        self.assertIsNone(manual.effective_response)
        self.assertEqual([entry["source"] for entry in manual.submission_history],
                         ["external_form", "manual_entry"])
        self.assertEqual(manual.submission_history[0]["confirmation"]["response_id"], 42)
        task = await self.db[models.COLLECTION_NAME].find_one({"_id": ObjectId(self.task_id)})
        self.assertEqual(task["status"], "confirmed")  # confirmed historical task remains intact

    async def test_manual_source_replacement_rolls_back_with_audit_failure(self):
        followups = FollowupService(self.db)
        await service.confirm_fill_task(self.db, self.remote_client, self.task_id, self.operator)
        before = await self.db.followup_records.find_one({"_id": ObjectId(self.visit_id)})
        with patch.object(followups, "_write_audit", side_effect=RuntimeError("synthetic audit failure")):
            with self.assertRaises(RuntimeError):
                await followups.complete_followup(self.visit_id,
                    CompleteFollowUpRequest(expected_version=before["mutation_version"], notes="replacement"),
                    operator_id=OPERATOR_ID)
        self.assertEqual(await self.db.followup_records.find_one({"_id": ObjectId(self.visit_id)}), before)


@unittest.skipUnless(os.environ.get("REHAB_TEST_STANDALONE_URI"), "isolated standalone URI not supplied")
class FormsStandaloneRejectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        fill_feature = patch.dict(os.environ, {"FORM_PLATFORM_FILL_ENABLED": "true"})
        fill_feature.start()
        self.addCleanup(fill_feature.stop)

    async def test_unlinked_creation_is_rejected_before_remote_side_effect(self):
        uri = os.environ["REHAB_TEST_STANDALONE_URI"]
        if not uri.startswith("mongodb://127.0.0.1:"):
            raise RuntimeError("only an explicit loopback test instance is allowed")
        client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=4000)
        db = client["rehab_forms_standalone_" + uuid4().hex]
        remote = FakeRemote()
        remote_client = make_remote_client(remote)
        try:
            with self.assertRaises(service.FormIntegrationError) as raised:
                await service.create_fill_task(db, remote_client, make_operator(role="admin"), {
                    "patient_id": PATIENT_ID,
                    "remote_project_id": 1, "remote_center_id": 2, "remote_subject_id": 3,
                    "remote_questionnaire_id": 4, "remote_operator_user_id": 7,
                    "allowed_origin": "https://rehab.example"})
            self.assertEqual(raised.exception.status_code, 503)
            self.assertEqual(raised.exception.error_code, "FOLLOWUP_TRANSACTION_UNAVAILABLE")
            self.assertEqual(remote.requests, [])
            self.assertEqual(await db.list_collection_names(), [])
        finally:
            await client.drop_database(db.name)
            client.close()
