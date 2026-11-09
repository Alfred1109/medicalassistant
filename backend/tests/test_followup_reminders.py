"""Reminder concurrency and authorization against an isolated real replica set."""
import asyncio
import os
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from app.models.user import User
from app.services.user_service import UserService
from app.services.followup_reminder_service import (
    FollowupReminderService, ReminderRuntime, ensure_reminder_storage, DELIVERIES,
)
from app.services.followup_service import followup_from_mongo, map_followup_record_to_response
from app.core.exceptions import AppBaseException
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from app.api.routers.followup_reminder_router import router, get_current_user, get_database

URI = os.environ.get("REHAB_TEST_REMINDER_MONGO_URI")


class ReminderRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_does_not_access_database(self):
        runtime = ReminderRuntime()
        await runtime.start(None, enabled=False, interval=30)
        self.assertEqual(runtime.status["state"], "disabled")
        self.assertFalse(runtime.status["running"])

    async def test_storage_failure_is_visible_and_does_not_start_dispatch(self):
        runtime = ReminderRuntime()
        with patch("app.services.followup_reminder_service.ensure_reminder_storage", side_effect=RuntimeError("private error")):
            await runtime.start(None, enabled=True, interval=30)
        self.assertEqual(runtime.status["state"], "error")
        self.assertEqual(runtime.status["last_error_code"], "REMINDER_STORAGE_UNAVAILABLE")
        self.assertIsNone(runtime.task)
        self.assertNotIn("private error", str(runtime.status))

    async def test_scan_failure_retries_and_shutdown_cancels_task(self):
        recovered = asyncio.Event()
        attempts = 0
        async def scan():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("temporary storage failure")
            recovered.set()
        runtime = ReminderRuntime()
        with patch("app.services.followup_reminder_service.ensure_reminder_storage", new=AsyncMock()), \
             patch("app.services.followup_reminder_service.FollowupReminderService", return_value=SimpleNamespace(scan=scan)):
            await runtime.start(None, enabled=True, interval=.01)
            await asyncio.wait_for(recovered.wait(), 2)
            self.assertEqual(runtime.status["state"], "ready")
            self.assertIsNone(runtime.status["last_error_code"])
            await runtime.stop()
        self.assertFalse(runtime.status["running"])
        self.assertIsNone(runtime.task)


@unittest.skipUnless(URI, "set isolated local REHAB_TEST_REMINDER_MONGO_URI")
class ReminderReplicaTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue(URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")))
        self.mongo = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.mongo["rehab_reminder_test_" + uuid4().hex]
        await ensure_reminder_storage(self.db)
        self.patient, self.doctor = ObjectId(), ObjectId()
        await self.db.users.insert_many([
            {"_id": self.patient, "role": "patient", "is_active": True,
             "name": "Sensitive patient name", "email": "p@example.test", "password_hash": "secret",
             "practitioners": [str(self.doctor)], "updated_at": datetime(2020, 1, 1)},
            {"_id": self.doctor, "role": "doctor", "is_active": True,
             "name": "Clinician", "email": "d@example.test", "password_hash": "secret"},
        ])
        self.now = datetime(2026, 11, 9, 8)
        self.followup = ObjectId()
        await self.db.followup_records.insert_one({"_id": self.followup, "patient_id": str(self.patient),
            "created_by": str(self.doctor), "provider_id": str(self.doctor), "follow_up_type": "phone",
            "status": "scheduled", "scheduled_date": self.now + timedelta(hours=24),
            "notes": "Sensitive clinical findings", "mutation_version": 4,
            "reminder_before": 99, "reminder_settings": {"days_before": 9}})
        self.service = FollowupReminderService(self.db, clock=lambda: self.now)
        self.push = patch("app.api.websockets.get_connection_manager", return_value=SimpleNamespace(send_notification=AsyncMock()))
        self.push.start()

    async def asyncTearDown(self):
        self.push.stop()
        await self.mongo.drop_database(self.db.name)
        self.mongo.close()

    async def test_two_recipients_once_under_concurrent_runs_and_notification_deletion(self):
        await asyncio.gather(*(self.service.dispatch_one(str(self.followup)) for _ in range(5)))
        self.assertEqual(await self.db.notifications.count_documents({}), 2)
        self.assertEqual(await self.db[DELIVERIES].count_documents({"status": "persisted"}), 2)
        notices = await self.db.notifications.find({}).to_list(None)
        self.assertEqual({row["recipient_id"] for row in notices}, {str(self.patient), str(self.doctor)})
        for row in notices:
            self.assertEqual(row["notification_type"], "followup")
            self.assertEqual(row["related_entity_type"], "followup")
            self.assertNotIn("Sensitive", row["content"])
        await self.db.notifications.delete_many({})
        self.assertEqual((await self.service.dispatch_one(str(self.followup)))["generated"], 0)
        self.assertEqual(await self.db.notifications.count_documents({}), 0)

    async def test_before_window_and_passed_time_never_send_or_catch_up(self):
        self.now -= timedelta(microseconds=1)
        self.assertEqual((await self.service.dispatch_one(str(self.followup)))["generated"], 0)
        self.now += timedelta(hours=24, microseconds=1)
        result = await self.service.dispatch_one(str(self.followup))
        self.assertEqual(result["generated"], 0)
        reasons = await self.db[DELIVERIES].distinct("reason")
        self.assertEqual(reasons, ["PLAN_PASSED"])
        self.assertEqual(await self.service.scan(), 0)

    async def test_paused_patient_is_skipped_then_can_recover_before_plan(self):
        await self.db.users.update_one({"_id": self.patient}, {"$set": {"is_active": False}})
        self.assertEqual((await self.service.dispatch_one(str(self.followup)))["generated"], 0)
        self.assertEqual(await self.db[DELIVERIES].count_documents({"reason": "PATIENT_ACCOUNT_UNAVAILABLE"}), 2)
        await self.db.users.update_one({"_id": self.patient}, {"$set": {"is_active": True}})
        self.assertEqual((await self.service.dispatch_one(str(self.followup)))["generated"], 2)

    async def test_missing_patient_account_can_be_added_without_guessing_identity(self):
        patient = await self.db.users.find_one({"_id": self.patient})
        await self.db.users.delete_one({"_id": self.patient})
        self.assertEqual((await self.service.dispatch_one(str(self.followup)))["generated"], 0)
        await self.db.users.insert_one(patient)
        self.assertEqual((await self.service.dispatch_one(str(self.followup)))["generated"], 2)

    async def test_provider_must_be_explicit_active_and_currently_assigned(self):
        await self.db.followup_records.update_one({"_id": self.followup}, {"$unset": {"provider_id": ""}})
        self.assertEqual((await self.service.dispatch_one(str(self.followup)))["generated"], 1)
        self.assertIsNotNone(await self.db[DELIVERIES].find_one({"reason": "PROVIDER_ACCOUNT_UNAVAILABLE"}))
        await self.db.followup_records.update_one({"_id": self.followup}, {"$set": {"provider_id": str(self.doctor)}})
        await self.db.users.update_one({"_id": self.patient}, {"$set": {"practitioners": []}})
        self.assertEqual((await self.service.dispatch_one(str(self.followup)))["generated"], 0)
        self.assertIsNotNone(await self.db[DELIVERIES].find_one({"reason": "PROVIDER_NOT_ASSIGNED"}))
        await self.db.users.update_one({"_id": self.patient}, {"$set": {"practitioners": [self.doctor]}})
        self.assertEqual((await self.service.dispatch_one(str(self.followup)))["generated"], 1)

    async def test_canonical_domain_stops_dispatch_without_users_fallback(self):
        await self.db.patient_domain_state.insert_one({"_id": "clinical-patients-v1", "mode": "canonical"})
        with self.assertRaises(AppBaseException) as caught:
            await self.service.scan()
        self.assertEqual(caught.exception.error_code, "REMINDER_PATIENT_DOMAIN_UNSUPPORTED")
        with self.assertRaises(AppBaseException):
            await self.service.dispatch_one(str(self.followup))
        self.assertEqual(await self.db.notifications.count_documents({}), 0)

    async def test_fences_do_not_change_public_user_or_clinical_revision(self):
        before = await self.db.users.find_one({"_id": self.patient})
        await self.service.dispatch_one(str(self.followup))
        patient = await self.db.users.find_one({"_id": self.patient})
        self.assertGreater(patient.pop("_reminder_fence"), 0)
        self.assertEqual(patient, before)
        self.assertNotIn("_reminder_fence", User(email="p@example.test", name="Patient",
            password_hash="secret", _reminder_fence=7).to_dict())
        public = UserService(self.db)._map_user_to_schema({**patient, "_reminder_fence": 7,
            "created_at": self.now, "updated_at": self.now, "email": "patient@example.com"}).model_dump()
        self.assertNotIn("_reminder_fence", public)
        followup = await self.db.followup_records.find_one({"_id": self.followup})
        self.assertEqual(followup["mutation_version"], 4)
        self.assertNotIn("_reminder_fence", map_followup_record_to_response(followup_from_mongo(followup)).model_dump())

    async def race_after_read(self, change):
        original = self.service._recipients
        read, resume = asyncio.Event(), asyncio.Event()
        first = True
        async def gate(record, session):
            nonlocal first
            result = await original(record, session)
            if first:
                first = False
                read.set()
                await resume.wait()
            return result
        self.service._recipients = gate
        dispatch = asyncio.create_task(self.service.dispatch_one(str(self.followup)))
        await asyncio.wait_for(read.wait(), 5)
        await change()
        resume.set()
        return await asyncio.wait_for(dispatch, 10)

    async def test_concurrent_patient_deactivation_prevents_stale_notification(self):
        await self.race_after_read(lambda: self.db.users.update_one({"_id": self.patient}, {"$set": {"is_active": False}}))
        self.assertEqual(await self.db.notifications.count_documents({}), 0)

    async def test_concurrent_assignment_revocation_prevents_provider_notification(self):
        await self.race_after_read(lambda: self.db.users.update_one({"_id": self.patient}, {"$set": {"practitioners": []}}))
        self.assertEqual(await self.db.notifications.count_documents({"recipient_id": str(self.doctor)}), 0)
        self.assertEqual(await self.db.notifications.count_documents({"recipient_id": str(self.patient)}), 1)

    async def test_concurrent_provider_deactivation_prevents_provider_notification(self):
        await self.race_after_read(lambda: self.db.users.update_one({"_id": self.doctor}, {"$set": {"is_active": False}}))
        self.assertEqual(await self.db.notifications.count_documents({"recipient_id": str(self.doctor)}), 0)

    async def test_concurrent_reschedule_rechecks_window(self):
        await self.race_after_read(lambda: self.db.followup_records.update_one({"_id": self.followup},
            {"$set": {"scheduled_date": self.now + timedelta(days=3)}}))
        self.assertEqual(await self.db.notifications.count_documents({}), 0)

    async def test_concurrent_cancel_or_complete_prevents_stale_notification(self):
        for status in ("canceled", "completed", "in_review"):
            await self.db.followup_records.update_one({"_id": self.followup}, {"$set": {"status": "scheduled"}})
            self.service = FollowupReminderService(self.db, clock=lambda: self.now)
            await self.race_after_read(lambda: self.db.followup_records.update_one({"_id": self.followup}, {"$set": {"status": status}}))
            self.assertEqual(await self.db.notifications.count_documents({}), 0)

    async def test_failure_rolls_back_notifications_fences_and_ledger_then_retry_succeeds(self):
        original = self.service._fence
        async def fail_after_fence(collection, document, session):
            await original(collection, document, session)
            raise RuntimeError("synthetic transaction failure")
        self.service._fence = fail_after_fence
        with self.assertRaises(RuntimeError):
            await self.service.dispatch_one(str(self.followup))
        self.assertEqual(await self.db.notifications.count_documents({}), 0)
        self.assertEqual(await self.db[DELIVERIES].count_documents({}), 0)
        self.assertNotIn("_reminder_fence", await self.db.followup_records.find_one({"_id": self.followup}))
        self.service._fence = original
        self.assertEqual((await self.service.dispatch_one(str(self.followup)))["generated"], 2)

    async def test_ledger_failure_after_notification_insert_is_atomic_and_retryable(self):
        collection_type = type(self.db[DELIVERIES])
        original = collection_type.update_one
        async def fail_ledger(collection, *args, **kwargs):
            if collection.name == DELIVERIES:
                raise RuntimeError("synthetic ledger failure after notification insert")
            return await original(collection, *args, **kwargs)
        with patch.object(collection_type, "update_one", new=fail_ledger):
            with self.assertRaises(RuntimeError):
                await self.service.dispatch_one(str(self.followup))
        self.assertEqual(await self.db.notifications.count_documents({}), 0)
        self.assertEqual(await self.db[DELIVERIES].count_documents({}), 0)
        self.assertNotIn("_reminder_fence", await self.db.users.find_one({"_id": self.patient}))
        self.assertEqual((await self.service.dispatch_one(str(self.followup)))["generated"], 2)

    async def test_history_and_runtime_endpoints_are_medical_and_scope_limited(self):
        await self.service.dispatch_one(str(self.followup))
        app = FastAPI()
        app.include_router(router, prefix="/api")
        actor = SimpleNamespace(id=str(self.doctor), role="doctor")
        app.dependency_overrides[get_current_user] = lambda: actor
        app.dependency_overrides[get_database] = lambda: self.db
        @app.exception_handler(AppBaseException)
        async def domain_error(request, error):
            return JSONResponse(status_code=error.status_code, content={"code": error.error_code})
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            result = await client.get("/api/health-records/followup-reminders", params={"followup_id": str(self.followup)})
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()["total"], 2)
            self.assertTrue(result.json()["items"][0]["planned_at"].endswith("+00:00"))
            self.assertNotIn("recipient_id", result.json()["items"][0])
            actor.id = str(ObjectId())
            self.assertEqual((await client.get("/api/health-records/followup-reminders")).json()["total"], 0)
            self.assertEqual((await client.get("/api/health-records/followup-reminders", params={"followup_id": str(self.followup)})).status_code, 403)
            actor.role = "patient"
            self.assertEqual((await client.get("/api/health-records/followup-reminders/status")).status_code, 403)
            self.assertEqual((await client.get("/api/health-records/followup-reminders")).status_code, 403)

    async def test_persistent_failure_is_visible_retryable_and_does_not_starve_other_plans(self):
        second = await self.db.followup_records.find_one({"_id": self.followup})
        second["_id"] = ObjectId()
        await self.db.followup_records.insert_one(second)
        original = self.service.dispatch_one
        first = True
        async def transient_failure(identifier):
            nonlocal first
            if first:
                first = False
                raise RuntimeError("synthetic persistence outage")
            return await original(identifier)
        self.service.dispatch_one = transient_failure
        with self.assertRaises(AppBaseException):
            await self.service.scan()
        self.assertEqual(await self.db[DELIVERIES].count_documents({"status": "failed", "reason": "PERSISTENCE_FAILED"}), 2)
        self.assertEqual(await self.db.notifications.count_documents({}), 2)
        self.assertEqual(await self.service.scan(), 2)
        self.assertEqual(await self.db.notifications.count_documents({}), 4)
        self.assertEqual(await self.db[DELIVERIES].count_documents({"status": "failed"}), 0)
