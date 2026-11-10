"""Patient self-report isolation, immutable references and transactional writes."""
import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from bson import ObjectId
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import ValidationError

from app.core.exceptions import AppBaseException
from app.schemas.rehab_feedback import PatientFeedbackCreate
from app.services.rehab_feedback_service import RehabFeedbackService, ensure_feedback_indexes
from app.api.routers.rehab_feedback_router import router, get_current_active_user, get_database

URI = os.environ.get("REHAB_TEST_PATIENT_FEEDBACK_URI")


class FeedbackSchemaTests(unittest.TestCase):
    def test_strict_input_rejects_forged_identity_unknown_status_and_ambiguous_time(self):
        base = {"event_id": str(uuid4()), "version_id": str(ObjectId()),
                "prescription_item_id": str(ObjectId()), "execution_status": "partial",
                "feelings": "需要休息后再继续", "performed_at": "2026-11-09T08:00:00Z"}
        for change in ({"patient_id": "someone"}, {"event_type": "patient_report"},
                       {"execution_status": "diagnosed"}, {"feelings": "   "},
                       {"performed_at": "2026-11-09T08:00:00"}, {"version_id": "bad"},
                       {"media_ids": ["not-a-file"]}, {"media_ids": ["a" * 32, "a" * 32]}):
            with self.assertRaises(ValidationError):
                PatientFeedbackCreate.model_validate({**base, **change})


@unittest.skipUnless(URI, "set an isolated local replica-set REHAB_TEST_PATIENT_FEEDBACK_URI")
class FeedbackReplicaTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue(URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")))
        self.mongo = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.mongo["rehab_patient_feedback_test_" + uuid4().hex]
        self.patient, self.other, self.doctor, self.manager = [ObjectId() for _ in range(4)]
        self.plan, self.version, self.item = [ObjectId() for _ in range(3)]
        await self.db.users.insert_many([
            {"_id": self.patient, "role": "patient", "is_active": True,
             "practitioners": [str(self.doctor)], "health_managers": [str(self.manager)]},
            {"_id": self.other, "role": "patient", "is_active": True},
            {"_id": self.doctor, "role": "doctor", "is_active": True},
            {"_id": self.manager, "role": "health_manager", "is_active": True},
        ])
        await self.db.rehab_plans.insert_one({"_id": self.plan, "patient_id": str(self.patient),
            "status": "active", "published_version_id": str(self.version), "content_revision": 8,
            "updated_at": datetime(2026, 1, 1)})
        await self.db.rehab_plan_versions.insert_one({"_id": self.version,
            "plan_id": str(self.plan), "patient_id": str(self.patient),
            "workflow": "patient_publication", "status": "published", "version_no": 1,
            "snapshot": {"name": "已发布方案"},
            "items_snapshot": [{"item_id": str(self.item), "name": "医护确认项目", "intervention_type": "exercise"}]})
        self.actor = SimpleNamespace(id=str(self.patient), role="patient", is_active=True)
        self.service = RehabFeedbackService(self.db)
        await ensure_feedback_indexes(self.db)
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[get_current_active_user] = lambda: self.actor
        app.dependency_overrides[get_database] = lambda: self.db

        @app.exception_handler(AppBaseException)
        async def domain_error(request, error):
            return JSONResponse(status_code=error.status_code, content={"code": error.error_code})
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.mongo.drop_database(self.db.name)
        self.mongo.close()

    def payload(self, **changes):
        return PatientFeedbackCreate.model_validate({"event_id": str(uuid4()),
            "version_id": str(self.version), "prescription_item_id": str(self.item),
            "execution_status": "partial", "feelings": "需要休息后再继续",
            "performed_at": datetime.now(timezone.utc) - timedelta(minutes=10), **changes})

    async def submit(self, payload=None, actor=None):
        return await self.service.submit(str(self.plan), payload or self.payload(), actor or self.actor)

    async def test_concurrent_identical_submit_is_one_immutable_report_and_no_derived_progress(self):
        payload = self.payload()
        results = await asyncio.gather(*(self.submit(payload) for _ in range(5)))
        self.assertEqual(sum(result.created for result in results), 1)
        self.assertEqual(len({result.feedback.id for result in results}), 1)
        stored = await self.db.rehab_execution_events.find_one({})
        self.assertEqual(stored["event_type"], "patient_report")
        self.assertEqual(stored["version_id"], str(self.version))
        self.assertEqual(stored["prescription_item_id"], str(self.item))
        self.assertEqual(stored["recorded_by"], str(self.patient))
        self.assertEqual(await self.db.rehab_execution_events.count_documents({}), 1)
        plan = await self.db.rehab_plans.find_one({"_id": self.plan})
        self.assertEqual(plan["content_revision"], 8)
        self.assertEqual(plan["updated_at"], datetime(2026, 1, 1))
        self.assertNotIn("execution_status", plan)
        self.assertNotIn("completed_exercises", plan)

    async def test_same_event_different_content_is_conflict_and_old_success_replays_after_new_publication(self):
        payload = self.payload()
        first = await self.submit(payload)
        with self.assertRaises(AppBaseException) as failure:
            await self.submit(payload.model_copy(update={"feelings": "其他内容"}))
        self.assertEqual(failure.exception.status_code, 409)
        await self.db.rehab_plans.update_one({"_id": self.plan}, {"$set": {"published_version_id": str(ObjectId())}})
        replay = await self.submit(payload)
        self.assertFalse(replay.created)
        self.assertEqual(replay.feedback.id, first.feedback.id)
        with self.assertRaises(AppBaseException) as stale:
            await self.submit()
        self.assertEqual(stale.exception.error_code, "REHAB_FEEDBACK_VERSION_CHANGED")

    async def test_cross_patient_clinical_submission_and_invalid_item_are_rejected(self):
        for actor in (SimpleNamespace(id=str(self.other), role="patient", is_active=True),
                      SimpleNamespace(id=str(self.doctor), role="doctor", is_active=True)):
            with self.assertRaises(AppBaseException) as denied:
                await self.submit(actor=actor)
            self.assertEqual(denied.exception.status_code, 403)
        with self.assertRaises(AppBaseException) as mismatch:
            await self.submit(self.payload(prescription_item_id=str(ObjectId())))
        self.assertEqual(mismatch.exception.error_code, "REHAB_FEEDBACK_ITEM_MISMATCH")
        self.assertEqual(await self.db.rehab_execution_events.count_documents({}), 0)

    async def test_history_is_role_scoped_typed_and_paginated_and_revocation_is_immediate(self):
        for status in ("completed", "partial", "not_done"):
            await self.submit(self.payload(execution_status=status))
        await self.db.rehab_execution_events.insert_many([
            {"plan_id": str(self.plan), "event_id": "legacy", "notes": "not a patient report"},
            {"plan_id": str(self.plan), "event_id": "forged", "event_type": "patient_report",
             "schema_version": 1, "patient_id": str(self.patient), "recorded_by": str(self.doctor)},
        ])
        doctor = SimpleNamespace(id=str(self.doctor), role="doctor", is_active=True)
        first = await self.service.list(str(self.plan), doctor, limit=2)
        second = await self.service.list(str(self.plan), self.actor, skip=2, limit=2)
        self.assertEqual(first.total, 3)
        self.assertEqual(len(first.items), 2)
        self.assertEqual(len(second.items), 1)
        self.assertEqual(len({item.id for item in first.items + second.items}), 3)
        await self.db.users.update_one({"_id": self.patient}, {"$set": {"practitioners": []}})
        with self.assertRaises(AppBaseException) as denied:
            await self.service.list(str(self.plan), doctor)
        self.assertEqual(denied.exception.status_code, 403)

    async def test_rest_contract_is_private_and_replay_uses_200(self):
        url = f"/api/rehabilitation/plans/{self.plan}/patient-feedback"
        body = self.payload().model_dump(mode="json")
        first = await self.client.post(url, json=body)
        self.assertEqual(first.status_code, 201, first.text)
        replay = await self.client.post(url, json=body)
        self.assertEqual(replay.status_code, 200)
        history = await self.client.get(url)
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["total"], 1)
        self.assertEqual(history.headers["cache-control"], "no-store")
        self.assertTrue(history.json()["items"][0]["performed_at"].endswith("Z"))
        self.assertNotIn("request_fingerprint", str(history.json()))

    async def test_publication_change_during_submit_conflicts_and_rolls_back(self):
        entered, resume = asyncio.Event(), asyncio.Event()
        original = self.service.publication._authorize
        first = True
        async def paused(*args, **kwargs):
            nonlocal first
            result = await original(*args, **kwargs)
            if first:
                first = False
                entered.set()
                await resume.wait()
            return result
        with patch.object(self.service.publication, "_authorize", new=paused):
            task = asyncio.create_task(self.submit())
            await asyncio.wait_for(entered.wait(), 3)
            await self.db.rehab_plans.update_one({"_id": self.plan}, {"$set": {"published_version_id": str(ObjectId())}})
            resume.set()
            with self.assertRaises(AppBaseException) as changed:
                await asyncio.wait_for(task, 10)
        self.assertEqual(changed.exception.error_code, "REHAB_FEEDBACK_VERSION_CHANGED")
        self.assertEqual(await self.db.rehab_execution_events.count_documents({}), 0)

    async def test_failure_after_insert_rolls_back_report_and_fences(self):
        original = self.service.events.insert_one
        async def fail_after_insert(*args, **kwargs):
            await original(*args, **kwargs)
            raise RuntimeError("synthetic post-insert failure")
        with patch.object(self.service.events, "insert_one", new=fail_after_insert):
            with self.assertRaises(RuntimeError):
                await self.submit()
        self.assertEqual(await self.db.rehab_execution_events.count_documents({}), 0)
        self.assertNotIn("_publication_fence", await self.db.rehab_plans.find_one({"_id": self.plan}))
        self.assertNotIn("_access_fence", await self.db.users.find_one({"_id": self.patient}))

    async def test_deactivation_between_authorization_read_and_fence_rechecks_identity(self):
        entered, resume = asyncio.Event(), asyncio.Event()
        original = self.service.publication._access_fence
        first = True
        async def paused(*args, **kwargs):
            nonlocal first
            if first:
                first = False
                entered.set()
                await resume.wait()
            return await original(*args, **kwargs)
        with patch.object(self.service.publication, "_access_fence", new=paused):
            task = asyncio.create_task(self.submit())
            await asyncio.wait_for(entered.wait(), 3)
            await self.db.users.update_one({"_id": self.patient}, {"$set": {"is_active": False}})
            resume.set()
            with self.assertRaises(AppBaseException) as denied:
                await asyncio.wait_for(task, 10)
        self.assertEqual(denied.exception.status_code, 403)
        self.assertEqual(await self.db.rehab_execution_events.count_documents({}), 0)

    async def test_canonical_domain_never_falls_back_to_same_id_account(self):
        await self.db.patient_domain_state.insert_one({"_id": "clinical-patients-v1", "mode": "canonical"})
        with self.assertRaises(AppBaseException) as unavailable:
            await self.submit()
        self.assertEqual(unavailable.exception.error_code, "REHAB_PATIENT_DOMAIN_UNSUPPORTED")
        self.assertEqual(await self.db.rehab_execution_events.count_documents({}), 0)

    async def test_old_event_namespace_collision_cannot_return_or_overwrite_old_content(self):
        payload = self.payload()
        await self.db.rehab_execution_events.insert_one({"plan_id": str(self.plan),
            "event_id": f"patient-report:{self.patient}:{payload.event_id}", "notes": "old raw content"})
        with self.assertRaises(AppBaseException) as collision:
            await self.submit(payload)
        self.assertEqual(collision.exception.error_code, "REHAB_FEEDBACK_EVENT_CONFLICT")
        self.assertEqual((await self.service.list(str(self.plan), self.actor)).total, 0)

    async def test_historical_snapshot_reference_is_validated_and_cancel_does_not_erase_history(self):
        report = await self.submit()
        await self.db.rehab_plans.update_one({"_id": self.plan}, {"$set": {
            "status": "cancelled", "published_version_id": None}})
        await self.db.rehab_plan_versions.update_one({"_id": self.version}, {"$set": {"status": "withdrawn"}})
        history = await self.service.list(str(self.plan), self.actor)
        self.assertEqual(history.items[0].id, report.feedback.id)
        await self.db.rehab_plan_versions.update_one({"_id": self.version}, {"$set": {"items_snapshot": []}})
        with self.assertRaises(AppBaseException) as corrupt:
            await self.service.list(str(self.plan), self.actor)
        self.assertEqual(corrupt.exception.error_code, "REHAB_FEEDBACK_INVALID_HISTORY")

    async def test_missing_unique_index_fails_closed_and_never_uses_old_collision(self):
        await self.db.rehab_execution_events.drop_index("uniq_plan_event_id")
        await self.db.rehab_execution_events.insert_many([
            {"plan_id": str(self.plan), "event_id": "duplicate"},
            {"plan_id": str(self.plan), "event_id": "duplicate"}])
        with self.assertRaises(AppBaseException) as failure:
            await self.submit()
        self.assertEqual(failure.exception.error_code, "REHAB_FEEDBACK_INDEX_UNAVAILABLE")
        self.assertEqual(await self.db.rehab_execution_events.count_documents({"event_type": "patient_report"}), 0)

    async def test_completed_plan_allows_self_report_but_cancelled_and_archived_do_not(self):
        await self.db.rehab_plans.update_one({"_id": self.plan}, {"$set": {"status": "completed"}})
        self.assertTrue((await self.submit()).created)
        for state in ("cancelled", "archived"):
            await self.db.rehab_plans.update_one({"_id": self.plan}, {"$set": {"status": state}})
            with self.assertRaises(AppBaseException) as denied:
                await self.submit()
            self.assertEqual(denied.exception.error_code, "REHAB_FEEDBACK_PLAN_INACTIVE")
