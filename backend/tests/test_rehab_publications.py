"""Clinical publication safety on disposable local MongoDB replica sets."""
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
from pymongo.errors import OperationFailure

from app.core.exceptions import AppBaseException
from app.schemas.rehab_publication import PublicationItem, SavePublicationDraft, PublishDraft, WithdrawPublication
from app.schemas.rehab_plan_structure import PrescriptionItemCreate, ExecutionEventCreate
from app.services.rehab_publication_service import RehabPublicationService
from app.services.rehab_plan_structure_service import RehabPlanStructureService
from app.services.rehabilitation_service import RehabilitationService
from app.api.routers.rehab_publication_router import router, get_current_active_user, get_database

URI = os.environ.get("REHAB_TEST_PUBLICATION_MONGO_URI")


class PublicationSchemaTests(unittest.TestCase):
    def test_confirmation_and_dates_require_explicit_valid_values(self):
        with self.assertRaises(ValidationError):
            PublishDraft(request_id="request-one", draft_id=str(ObjectId()), expected_draft_revision=0,
                         confirmed=False, confirmation_note="reviewed")
        with self.assertRaises(ValidationError):
            SavePublicationDraft(request_id="request-one", content={"name": "x", "description": "x", "goal": "x", "start_date": "2026-11-09T00:00:00"})

    def test_cross_category_and_impossible_schedule_are_rejected(self):
        with self.assertRaises(ValidationError):
            PublicationItem(intervention_type="diet", name="x", medication_fields={"frequency": "daily"})
        with self.assertRaises(ValidationError):
            PublicationItem(intervention_type="exercise", name="x", schedule={"days_per_week": 8})


class EventIndexSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_index_failure_blocks_generic_event_writes(self):
        from unittest.mock import AsyncMock
        collection = SimpleNamespace(create_index=AsyncMock(side_effect=OperationFailure("index unavailable")))
        service = object.__new__(RehabPlanStructureService)
        service.events_collection, service._indexes_ready = collection, False
        with self.assertRaises(AppBaseException) as caught:
            await service._ensure_event_indexes()
        self.assertEqual(caught.exception.error_code, "REHAB_EXECUTION_INDEX_UNAVAILABLE")
        self.assertFalse(service._indexes_ready)


@unittest.skipUnless(URI, "set REHAB_TEST_PUBLICATION_MONGO_URI to an isolated local replica set")
class PublicationMongoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue(URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")))
        self.mongo = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.mongo["rehab_publication_test_" + uuid4().hex]
        self.patient_id, self.doctor_id, self.other_id, self.plan_id = [ObjectId() for _ in range(4)]
        await self.db.users.insert_many([
            {"_id": self.patient_id, "role": "patient", "is_active": True,
             "name": "private patient", "practitioners": [str(self.doctor_id)], "password_hash": "secret"},
            {"_id": self.doctor_id, "role": "doctor", "is_active": True},
            {"_id": self.other_id, "role": "patient", "is_active": True},
        ])
        await self.db.rehab_plans.insert_one({"_id": self.plan_id, "patient_id": str(self.patient_id),
            "name": "old plan", "status": "active", "content_revision": 3,
            "notes": "internal note", "metadata": {"private": "do not leak"},
            "exercises": [{"exercise_id": str(ObjectId()), "schedule": {"sets": 3, "reps": 10}}]})
        self.svc = RehabPublicationService(self.db)
        self.plan = str(self.plan_id)
        self.doctor = SimpleNamespace(id=str(self.doctor_id), role="doctor")
        self.patient = SimpleNamespace(id=str(self.patient_id), role="patient")

    async def asyncTearDown(self):
        await self.mongo.drop_database(self.db.name)
        self.mongo.close()

    def draft_request(self, **updates):
        data = {"request_id": uuid4().hex, "content": {"name": "Clinician plan", "description": "Reviewed content",
            "goal": "A recorded goal", "start_date": "2026-11-09T08:00:00+08:00"},
            "items": [{"intervention_type": "diet", "name": "Clinician diet", "diet_fields": {"food_restrictions": ["explicit instruction"]}},
                      {"intervention_type": "exercise", "name": "Clinician exercise", "schedule": {"sets": 2}},
                      {"intervention_type": "medication", "name": "Clinician medication", "medication_fields": {"frequency": "explicit schedule"}},
                      {"intervention_type": "psychology", "name": "Clinician psychology", "psychology_fields": {"modality_ref": "manual instruction"}}]}
        data.update(updates)
        return SavePublicationDraft.model_validate(data)

    async def draft(self, **updates):
        return await self.svc.save_draft(self.plan, self.doctor, self.draft_request(**updates))

    def publish_request(self, draft, previous=None, **updates):
        data = {"request_id": uuid4().hex, "draft_id": draft["draft"]["id"],
            "expected_draft_revision": draft["draft"]["revision"], "expected_publication_id": previous,
            "confirmed": True, "confirmation_note": "Clinician checked all entered content"}
        data.update(updates)
        return PublishDraft.model_validate(data)

    async def published(self):
        draft = await self.draft()
        return await self.svc.publish(self.plan, self.doctor, self.publish_request(draft))

    async def test_active_legacy_and_draft_never_appear_until_explicit_publication(self):
        self.assertEqual((await self.svc.patient_list(self.patient))["total"], 0)
        with self.assertRaises(AppBaseException) as caught:
            await self.svc.patient_detail(self.plan, self.patient)
        self.assertEqual(caught.exception.status_code, 404)
        draft = await self.draft()
        self.assertEqual((await self.svc.patient_list(self.patient))["total"], 0)
        shown = await self.svc.publish(self.plan, self.doctor, self.publish_request(draft))
        self.assertEqual(len(shown["items"]), 4)
        self.assertNotIn("metadata", shown)
        self.assertNotIn("notes", shown["content"])
        self.assertNotIn("exercises", shown["content"])
        self.assertEqual(datetime.fromisoformat(shown["content"]["start_date"]), datetime(2026, 11, 9, tzinfo=timezone.utc))
        self.assertEqual((await self.svc.patient_detail(self.plan, self.patient))["version_id"], shown["version_id"])

    async def test_revising_draft_preserves_old_publication_until_republish(self):
        old = await self.published()
        draft = await self.draft(content={"name": "New draft", "description": "new", "goal": "new", "start_date": "2026-11-10T00:00:00Z"})
        self.assertEqual((await self.svc.patient_detail(self.plan, self.patient))["version_id"], old["version_id"])
        new = await self.svc.publish(self.plan, self.doctor, self.publish_request(draft, old["version_id"]))
        self.assertNotEqual(new["version_id"], old["version_id"])
        archived = await self.db.rehab_plan_versions.find_one({"_id": ObjectId(old["version_id"])})
        self.assertEqual(archived["snapshot"]["name"], "Clinician plan")
        self.assertEqual((await self.svc.patient_detail(self.plan, self.patient))["content"]["name"], "New draft")

    async def test_current_publication_can_seed_new_draft_with_stable_item_ids(self):
        first = await self.published()
        state = await self.svc.draft(self.plan, self.doctor)
        self.assertEqual(state["published"], first)
        items = [{**item, "description": "explicit revised instruction"} for item in first["items"]]
        draft = await self.draft(content=first["content"], items=items)
        self.assertEqual([x["item_id"] for x in draft["draft"]["items"]], [x["item_id"] for x in first["items"]])
        self.assertEqual((await self.svc.patient_detail(self.plan, self.patient))["items"], first["items"])
        second = await self.svc.publish(self.plan, self.doctor, self.publish_request(draft, first["version_id"]))
        self.assertNotEqual(first["version_id"], second["version_id"])
        self.assertEqual(first["items"][0]["item_id"], second["items"][0]["item_id"])
        self.assertEqual(second["items"][0]["description"], "explicit revised instruction")
        await self.db.rehab_prescription_items.update_many({"version_id": second["version_id"]}, {"$set": {"description": "direct source mutation"}})
        self.assertEqual((await self.svc.patient_detail(self.plan, self.patient))["items"][0]["description"], "explicit revised instruction")

    async def test_complete_publication_feedback_adjustment_archive_flow(self):
        from app.services.rehab_feedback_service import RehabFeedbackService
        from app.schemas.rehab_feedback import PatientFeedbackCreate
        draft = await self.draft()
        first = await self.svc.publish(self.plan, self.doctor, self.publish_request(draft))
        viewed = await self.svc.patient_detail(self.plan, self.patient)
        feedback = RehabFeedbackService(self.db)
        request = PatientFeedbackCreate(event_id=uuid4(), version_id=viewed["version_id"],
            prescription_item_id=viewed["items"][0]["item_id"], execution_status="partial",
            feelings="Patient recorded a real subjective observation",
            performed_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        submitted = await feedback.submit(self.plan, request, self.patient)
        self.assertTrue(submitted.created)
        seen = await feedback.list(self.plan, self.doctor)
        self.assertEqual(seen.total, 1)
        self.assertEqual(seen.items[0].version_id, first["version_id"])
        draft = await self.draft(content={**first["content"], "description": "Clinician adjusted instruction"}, items=first["items"])
        second = await self.svc.publish(self.plan, self.doctor, self.publish_request(draft, first["version_id"]))
        self.assertEqual((await self.svc.patient_detail(self.plan, self.patient))["version_id"], second["version_id"])
        self.assertEqual((await feedback.list(self.plan, self.patient)).items[0].version_id, first["version_id"])
        self.assertEqual((await feedback.list(self.plan, self.doctor, version_id=second["version_id"])).total, 0)
        await self.svc.withdraw(self.plan, self.doctor, WithdrawPublication(request_id=uuid4().hex,
            expected_publication_id=second["version_id"], action="archive", reason="Clinician archived this plan"))
        self.assertEqual((await self.svc.patient_list(self.patient))["total"], 0)
        self.assertEqual((await feedback.list(self.plan, self.patient)).items[0].version_id, first["version_id"])
        with self.assertRaises(AppBaseException):
            await feedback.submit(self.plan, request.model_copy(update={"event_id": uuid4(), "version_id": second["version_id"]}), self.patient)

    async def test_concurrent_different_publications_from_same_revision_have_one_winner(self):
        draft = await self.draft()
        results = await asyncio.gather(*(self.svc.publish(self.plan, self.doctor, self.publish_request(draft)) for _ in range(2)), return_exceptions=True)
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(sum(isinstance(result, AppBaseException) and result.status_code == 409 for result in results), 1)
        self.assertEqual(await self.db.rehab_plan_versions.count_documents({"status": "published"}), 1)

    async def test_cas_and_idempotency_reject_conflicting_replays(self):
        request = self.draft_request()
        first = await self.svc.save_draft(self.plan, self.doctor, request)
        second = await self.svc.save_draft(self.plan, self.doctor, request)
        self.assertEqual(first["draft"]["id"], second["draft"]["id"])
        with self.assertRaises(AppBaseException):
            await self.svc.save_draft(self.plan, self.doctor, self.draft_request())
        publish = self.publish_request(first)
        results = await asyncio.gather(*(self.svc.publish(self.plan, self.doctor, publish) for _ in range(3)))
        self.assertEqual(len({result["version_id"] for result in results}), 1)
        self.assertEqual(await self.db.rehab_plan_versions.count_documents({"status": "published"}), 1)
        with self.assertRaises(AppBaseException) as caught:
            await self.svc.publish(self.plan, self.doctor, publish.model_copy(update={"confirmation_note": "different"}))
        self.assertEqual(caught.exception.error_code, "REHAB_IDEMPOTENCY_CONFLICT")

    async def test_other_patient_and_revoked_doctor_cannot_read_or_publish(self):
        shown = await self.published()
        other = SimpleNamespace(id=str(self.other_id), role="patient")
        with self.assertRaises(AppBaseException) as caught:
            await self.svc.patient_detail(self.plan, other)
        self.assertEqual(caught.exception.status_code, 403)
        with self.assertRaises(AppBaseException):
            await self.svc.draft(self.plan, self.patient)
        await self.db.users.update_one({"_id": self.patient_id}, {"$set": {"practitioners": []}})
        with self.assertRaises(AppBaseException):
            await self.svc.draft(self.plan, self.doctor)
        self.assertEqual((await self.svc.patient_detail(self.plan, self.patient))["version_id"], shown["version_id"])

    async def test_system_admin_is_not_a_clinical_publisher_and_manager_uses_own_assignment(self):
        draft = await self.draft()
        admin_id, manager_id = ObjectId(), ObjectId()
        await self.db.users.insert_many([
            {"_id": admin_id, "role": "admin", "is_active": True},
            {"_id": manager_id, "role": "health_manager", "is_active": True}])
        for actor in (SimpleNamespace(id=str(admin_id), role="admin"), SimpleNamespace(id=str(manager_id), role="health_manager")):
            with self.assertRaises(AppBaseException) as caught:
                await self.svc.publish(self.plan, actor, self.publish_request(draft))
            self.assertEqual(caught.exception.status_code, 403)
        await self.db.users.update_one({"_id": self.patient_id}, {"$set": {"health_managers": [manager_id]}})
        result = await self.svc.publish(self.plan, SimpleNamespace(id=str(manager_id), role="health_manager"), self.publish_request(draft))
        self.assertEqual(result["version_id"], draft["draft"]["id"])

    async def test_stopped_patient_account_cannot_read_published_plan(self):
        await self.published()
        await self.db.users.update_one({"_id": self.patient_id}, {"$set": {"is_active": False}})
        with self.assertRaises(AppBaseException) as caught:
            await self.svc.patient_detail(self.plan, self.patient)
        self.assertEqual(caught.exception.status_code, 403)

    async def test_withdraw_cancel_archive_preserve_history_and_never_resurrect(self):
        for action in ("withdraw", "cancel", "archive"):
            await self.db.rehab_plans.update_one({"_id": self.plan_id}, {"$set": {"status": "active"}})
            draft = await self.draft()
            shown = await self.svc.publish(self.plan, self.doctor, self.publish_request(draft))
            request = WithdrawPublication(request_id=uuid4().hex, expected_publication_id=shown["version_id"], reason="clinical reason", action=action)
            await self.svc.withdraw(self.plan, self.doctor, request)
            await self.svc.withdraw(self.plan, self.doctor, request)
            await self.db.rehab_plans.update_one({"_id": self.plan_id}, {"$set": {"status": "active"}})
            self.assertEqual((await self.svc.patient_list(self.patient))["total"], 0)
            record = await self.db.rehab_plan_versions.find_one({"_id": ObjectId(shown["version_id"])})
            self.assertEqual(record["status"], "withdrawn")
            self.assertIn("items_snapshot", record)
            self.assertTrue((await self.db.rehab_plans.find_one({"_id": self.plan_id}))["has_publication_history"])

    async def test_transaction_failure_rolls_back_version_pointer_and_access_fences(self):
        draft = await self.draft()
        before = await self.db.users.find_one({"_id": self.patient_id})
        with patch.object(self.svc, "_record_operation", side_effect=RuntimeError("injected failure")):
            with self.assertRaises(RuntimeError):
                await self.svc.publish(self.plan, self.doctor, self.publish_request(draft))
        plan = await self.db.rehab_plans.find_one({"_id": self.plan_id})
        self.assertIsNone(plan.get("published_version_id"))
        self.assertEqual((await self.db.rehab_plan_versions.find_one({"_id": ObjectId(draft["draft"]["id"])}))["status"], "draft")
        self.assertEqual((await self.db.users.find_one({"_id": self.patient_id}))["_access_fence"], before["_access_fence"])

    async def _race_publish(self, change):
        draft = await self.draft()
        original = self.svc._authorize
        observed = asyncio.Event()
        resume = asyncio.Event()
        paused = False
        async def pause(plan, actor, session, **kwargs):
            nonlocal paused
            if not paused:
                paused = True
                await original(plan, actor, session, write=False, fence=False)
                observed.set()
                await resume.wait()
            return await original(plan, actor, session, **kwargs)
        with patch.object(self.svc, "_authorize", new=pause):
            task = asyncio.create_task(self.svc.publish(self.plan, self.doctor, self.publish_request(draft)))
            await asyncio.wait_for(observed.wait(), 3)
            await change()
            resume.set()
            with self.assertRaises(AppBaseException):
                await task
        self.assertIsNone((await self.db.rehab_plans.find_one({"_id": self.plan_id})).get("published_version_id"))

    async def test_concurrent_account_disable_rechecks_authority(self):
        await self._race_publish(lambda: self.db.users.update_one({"_id": self.doctor_id}, {"$set": {"is_active": False}}))

    async def test_concurrent_patient_assignment_revocation_rechecks_authority(self):
        await self._race_publish(lambda: self.db.users.update_one({"_id": self.patient_id}, {"$set": {"practitioners": []}}))

    async def test_old_item_write_cannot_modify_publication_workflow_and_reserved_event_is_rejected(self):
        draft = await self.draft()
        structure = RehabPlanStructureService(self.db)
        with self.assertRaises(AppBaseException) as caught:
            await structure.add_prescription_item(self.plan, draft["draft"]["id"], PrescriptionItemCreate(name="bypass"),
                operator_id=self.doctor.id, operator_role="doctor")
        self.assertEqual(caught.exception.error_code, "REHAB_VERSION_IMMUTABLE")
        with self.assertRaises(AppBaseException) as caught:
            await structure.record_execution_event(self.plan, "unknown", ExecutionEventCreate(event_id="patient-report:forged"),
                operator_id=self.doctor.id, operator_role="doctor")
        self.assertEqual(caught.exception.error_code, "REHAB_RESERVED_EVENT_ID")

    async def test_publish_wins_then_legacy_delete_cannot_remove_history(self):
        await self.published()
        with self.assertRaises(AppBaseException) as caught:
            await RehabilitationService(self.db).delete_rehab_plan(self.plan)
        self.assertEqual(caught.exception.status_code, 409)

    async def test_delete_wins_then_publish_cannot_leave_orphan_publication(self):
        draft = await self.draft()
        original = self.svc._touch_plan
        paused = False
        async def remove_first(plan, session, **kwargs):
            nonlocal paused
            if not paused:
                paused = True
                await self.db.rehab_plans.delete_one({"_id": self.plan_id})
            return await original(plan, session, **kwargs)
        with patch.object(self.svc, "_touch_plan", new=remove_first):
            with self.assertRaises(AppBaseException):
                await self.svc.publish(self.plan, self.doctor, self.publish_request(draft))
        self.assertEqual(await self.db.rehab_plan_versions.count_documents({"status": "published"}), 0)

    async def test_patient_route_projects_only_published_content_and_denies_drafts(self):
        await self.published()
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[get_current_active_user] = lambda: self.patient
        app.dependency_overrides[get_database] = lambda: self.db
        @app.exception_handler(AppBaseException)
        async def fail(request, exc):
            return JSONResponse(status_code=exc.status_code, content={"code": exc.error_code})
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/rehabilitation/publications/my-plans/" + self.plan)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertNotIn("private", response.text)
            denied = await client.get("/api/rehabilitation/publications/plans/" + self.plan + "/draft")
            self.assertEqual(denied.status_code, 403)

    async def test_canonical_domain_stops_legacy_mapping_and_empty_items_cannot_publish(self):
        draft = await self.draft(items=[])
        with self.assertRaises(AppBaseException) as caught:
            await self.svc.publish(self.plan, self.doctor, self.publish_request(draft))
        self.assertEqual(caught.exception.error_code, "REHAB_ITEMS_REQUIRED")
        await self.db.patient_domain_state.insert_one({"_id": "clinical-patients-v1", "mode": "canonical"})
        with self.assertRaises(AppBaseException) as caught:
            await self.svc.patient_list(self.patient)
        self.assertEqual(caught.exception.error_code, "REHAB_PATIENT_DOMAIN_UNSUPPORTED")
