"""Training review, supplement and plan-level cycle acceptance integration tests."""
import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from bson import ObjectId
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.exceptions import AppBaseException
from app.schemas.rehab_feedback import ClinicalFeedbackReview, PatientFeedbackCreate, PatientFeedbackSupplement
from app.schemas.rehab_training_cycle import TrainingCycleAcceptance, TrainingCycleCreate
from app.services.rehab_feedback_service import RehabFeedbackService, ensure_feedback_indexes
from app.services.rehab_training_cycle_service import RehabTrainingCycleService
from app.api.routers.rehab_feedback_router import router, get_current_active_user, get_database

URI = os.environ.get("REHAB_TEST_PATIENT_FEEDBACK_URI")


@unittest.skipUnless(URI, "set an isolated local replica-set REHAB_TEST_PATIENT_FEEDBACK_URI")
class TrainingCycleReplicaTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue(URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")))
        self.mongo = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.mongo["rehab_training_cycle_test_" + uuid4().hex]
        self.patient, self.doctor = ObjectId(), ObjectId()
        self.plan, self.version, self.item = ObjectId(), ObjectId(), ObjectId()
        await self.db.users.insert_many([
            {"_id": self.patient, "role": "patient", "is_active": True,
             "practitioners": [str(self.doctor)]},
            {"_id": self.doctor, "role": "doctor", "is_active": True},
        ])
        await self.db.rehab_plans.insert_one({"_id": self.plan,
            "patient_id": str(self.patient), "status": "active",
            "published_version_id": str(self.version), "content_revision": 1})
        await self.db.rehab_plan_versions.insert_one({"_id": self.version,
            "plan_id": str(self.plan), "patient_id": str(self.patient),
            "workflow": "patient_publication", "status": "published", "version_no": 1,
            "items_snapshot": [{"item_id": str(self.item), "name": "训练动作",
                                "intervention_type": "exercise"}]})
        self.patient_actor = SimpleNamespace(id=str(self.patient), role="patient", is_active=True)
        self.doctor_actor = SimpleNamespace(id=str(self.doctor), role="doctor", is_active=True)
        self.feedback = RehabFeedbackService(self.db)
        self.cycles = RehabTrainingCycleService(self.db)
        await ensure_feedback_indexes(self.db)
        self.route_actor = self.patient_actor
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[get_current_active_user] = lambda: self.route_actor
        app.dependency_overrides[get_database] = lambda: self.db

        @app.exception_handler(AppBaseException)
        async def domain_error(request, error):
            return JSONResponse(status_code=error.status_code, content={"code": error.error_code})
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.mongo.drop_database(self.db.name)
        self.mongo.close()

    async def _video(self):
        media_id = uuid4().hex
        await self.db.patient_feedback_media.insert_one({"_id": media_id,
            "plan_id": str(self.plan), "patient_id": str(self.patient),
            "content_type": "video/mp4", "name": "训练.mp4", "suffix": ".mp4",
            "bound_event_id": None, "created_at": datetime.now(timezone.utc)})
        return media_id

    async def test_review_return_requires_patient_supplement_before_verification_and_acceptance(self):
        await self.cycles.create(str(self.plan), self.doctor_actor,
            TrainingCycleCreate(request_id="create-cycle-0001", title="第一周期",
                start_date="2025-01-01", end_date="2025-01-31"))
        payload = PatientFeedbackCreate(event_id=uuid4(), version_id=str(self.version),
            prescription_item_id=str(self.item), execution_status="completed", feelings="完成训练",
            performed_at="2025-01-16T04:00:00Z", media_ids=[await self._video()])
        report = await self.feedback.submit(str(self.plan), payload, self.patient_actor)
        report_id = report.feedback.id
        self.assertIsNotNone(report.feedback.cycle_id)
        returned = await self.feedback.review(str(self.plan), report_id,
            ClinicalFeedbackReview(expected_revision=0, status="return_for_supplement", note="请补充完整训练视频"),
            self.doctor_actor)
        self.assertEqual(returned["feedback"].clinical_review["status"], "return_for_supplement")
        listed_cycle = (await self.cycles.list(str(self.plan), self.doctor_actor))["items"][0]
        with self.assertRaises(AppBaseException):
            await self.cycles.accept(str(self.plan), listed_cycle["id"], self.doctor_actor,
                TrainingCycleAcceptance(request_id="accept-cycle-pending", expected_revision=0, note="暂不验收"))
        with self.assertRaises(AppBaseException):
            await self.feedback.review(str(self.plan), report_id,
                ClinicalFeedbackReview(expected_revision=1, status="verified", note="复核"), self.doctor_actor)
        media_id = await self._video()
        supplemented = await self.feedback.supplement(str(self.plan), report_id,
            PatientFeedbackSupplement(event_id=uuid4(), note="补充完整视频", media_ids=[media_id]),
            self.patient_actor)
        self.assertEqual(supplemented["feedback"].clinical_review["status"], "pending")
        self.assertEqual(len(supplemented["feedback"].supplements), 1)
        await self.feedback.review(str(self.plan), report_id,
            ClinicalFeedbackReview(expected_revision=2, status="verified", note="视频已核验"), self.doctor_actor)
        cycle = (await self.cycles.list(str(self.plan), self.doctor_actor))["items"][0]
        self.assertEqual(cycle["feedback_count"], 1)
        self.assertEqual(cycle["verified_count"], 1)
        accepted = await self.cycles.accept(str(self.plan), cycle["id"], self.doctor_actor,
            TrainingCycleAcceptance(request_id="accept-cycle-0001", expected_revision=0, note="周期复核完成"))
        self.assertEqual(accepted["cycle"]["status"], "accepted")
        self.assertEqual(accepted["cycle"]["acceptance"]["note"], "周期复核完成")
        with self.assertRaises(AppBaseException):
            await self.feedback.review(str(self.plan), report_id,
                ClinicalFeedbackReview(expected_revision=3, status="verified", note="重复核验"), self.doctor_actor)

    async def test_acceptance_blocked_until_cycle_end(self):
        created = await self.cycles.create(str(self.plan), self.doctor_actor,
            TrainingCycleCreate(request_id="create-cycle-0002", title="第二周期",
                start_date="2099-02-01", end_date="2099-02-28"))
        cycle = created["cycle"]
        with self.assertRaises(AppBaseException):
            await self.cycles.accept(str(self.plan), cycle["id"], self.doctor_actor,
                TrainingCycleAcceptance(request_id="accept-cycle-0002", expected_revision=0, note="验收"))

    async def test_legacy_feedback_without_review_fields_cannot_pass_without_video(self):
        report_id = ObjectId()
        await self.db.rehab_execution_events.insert_one({
            "_id": report_id, "plan_id": str(self.plan), "patient_id": str(self.patient),
            "recorded_by": str(self.patient), "event_type": "patient_report", "schema_version": 1,
            "event_id": "legacy:training-report", "client_event_id": str(uuid4()),
            "version_id": str(self.version), "version_no": 1,
            "prescription_item_id": str(self.item), "execution_status": "completed",
            "feelings": "旧版反馈", "performed_at": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc), "attachments": [],
            "source": "patient_self_report"})
        with self.assertRaises(AppBaseException) as missing_video:
            await self.feedback.review(str(self.plan), str(report_id),
                ClinicalFeedbackReview(expected_revision=0, status="verified", note="核验通过"),
                self.doctor_actor)
        self.assertEqual(missing_video.exception.error_code, "REHAB_FEEDBACK_VIDEO_REQUIRED")
        returned = await self.feedback.review(str(self.plan), str(report_id),
            ClinicalFeedbackReview(expected_revision=0, status="return_for_supplement", note="请补视频"),
            self.doctor_actor)
        self.assertEqual(returned["feedback"].clinical_review["status"], "return_for_supplement")

    async def test_one_cycle_spans_publication_versions_and_locks_after_acceptance(self):
        created = await self.cycles.create(str(self.plan), self.doctor_actor,
            TrainingCycleCreate(request_id="create-cross-version-01", title="跨版本周期",
                start_date="2025-03-01", end_date="2025-03-31"))
        cycle = created["cycle"]
        first = await self.feedback.submit(str(self.plan), PatientFeedbackCreate(
            event_id=uuid4(), version_id=str(self.version), prescription_item_id=str(self.item),
            execution_status="completed", feelings="版本一训练",
            performed_at="2025-03-05T04:00:00Z", media_ids=[await self._video()]), self.patient_actor)

        version2, item2 = ObjectId(), ObjectId()
        await self.db.rehab_plan_versions.update_one({"_id": self.version}, {"$set": {"status": "withdrawn"}})
        await self.db.rehab_plan_versions.insert_one({"_id": version2, "plan_id": str(self.plan),
            "patient_id": str(self.patient), "workflow": "patient_publication", "status": "published",
            "version_no": 2, "items_snapshot": [{"item_id": str(item2), "name": "新版本训练",
                "intervention_type": "exercise"}]})
        await self.db.rehab_plans.update_one({"_id": self.plan}, {"$set": {
            "published_version_id": str(version2)}})
        second = await self.feedback.submit(str(self.plan), PatientFeedbackCreate(
            event_id=uuid4(), version_id=str(version2), prescription_item_id=str(item2),
            execution_status="partial", feelings="版本二训练",
            performed_at="2025-03-20T04:00:00Z", media_ids=[await self._video()]), self.patient_actor)
        self.assertEqual(first.feedback.cycle_id, cycle["id"])
        self.assertEqual(second.feedback.cycle_id, cycle["id"])
        await self.feedback.review(str(self.plan), first.feedback.id,
            ClinicalFeedbackReview(expected_revision=0, status="verified", note="版本一视频通过"),
            self.doctor_actor)
        counts = (await self.cycles.list(str(self.plan), self.doctor_actor))["items"][0]
        self.assertEqual((counts["feedback_count"], counts["verified_count"], counts["pending_reviews_count"]), (2, 1, 1))
        with self.assertRaises(AppBaseException):
            await self.cycles.accept(str(self.plan), cycle["id"], self.doctor_actor,
                TrainingCycleAcceptance(request_id="accept-cross-version-blocked", expected_revision=0,
                                        note="等待剩余反馈核验"))
        await self.feedback.review(str(self.plan), second.feedback.id,
            ClinicalFeedbackReview(expected_revision=0, status="verified", note="版本二视频通过"),
            self.doctor_actor)
        accepted = await self.cycles.accept(str(self.plan), cycle["id"], self.doctor_actor,
            TrainingCycleAcceptance(request_id="accept-cross-version-done", expected_revision=0,
                                    note="跨版本周期已统一审阅"))
        self.assertEqual(accepted["cycle"]["status"], "accepted")
        evidence = await self.db.rehab_training_cycles.find_one({"_id": cycle["id"]})
        self.assertEqual({entry["version_id"] for entry in evidence["acceptance"]["reviewed_feedback"]},
                         {str(self.version), str(version2)})
        with self.assertRaises(AppBaseException) as locked:
            await self.feedback.submit(str(self.plan), PatientFeedbackCreate(
                event_id=uuid4(), version_id=str(version2), prescription_item_id=str(item2),
                execution_status="completed", feelings="验收后不应补录",
                performed_at="2025-03-25T04:00:00Z", media_ids=[await self._video()]), self.patient_actor)
        self.assertEqual(locked.exception.error_code, "REHAB_TRAINING_CYCLE_ACCEPTED")

    async def test_http_routes_enforce_patient_and_clinician_roles(self):
        cycle = await self.cycles.create(str(self.plan), self.doctor_actor,
            TrainingCycleCreate(request_id="create-http-cycle-01", title="接口周期",
                start_date="2025-04-01", end_date="2025-04-30"))
        feedback_id = str(ObjectId())
        base = f"/api/rehabilitation/plans/{self.plan}"
        self.route_actor = self.patient_actor
        review = await self.client.post(f"{base}/patient-feedback/{feedback_id}/review", json={
            "expected_revision": 0, "status": "verified", "note": "不允许患者核验"})
        acceptance = await self.client.post(f"{base}/training-cycles/{cycle['cycle']['id']}/acceptance", json={
            "request_id": "patient-accept-cycle", "expected_revision": 0, "note": "不允许患者验收"})
        self.assertEqual(review.status_code, 403, review.text)
        self.assertEqual(acceptance.status_code, 403, acceptance.text)
        self.route_actor = self.doctor_actor
        supplement = await self.client.post(f"{base}/patient-feedback/{feedback_id}/supplements", json={
            "event_id": str(uuid4()), "note": "不允许医护代患者补充", "media_ids": []})
        self.assertEqual(supplement.status_code, 403, supplement.text)
