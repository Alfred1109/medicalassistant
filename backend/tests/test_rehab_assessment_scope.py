"""Same-patient clinical references and atomic writes in disposable Mongo."""
import asyncio
import os
import unittest
from datetime import datetime, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock, patch

import httpx
from bson import ObjectId
from jose import jwt
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.core.dependencies import get_rehabilitation_service
from app.core.exceptions import AppBaseException
from app.db.mongodb import get_database
from app.main import app
from app.schemas.rehabilitation import AssessmentCreate, AssessmentUpdate
from app.schemas.user import UserResponse
from app.services.rehabilitation_service import RehabilitationService
from app.services.user_service import UserService

URI = os.environ.get("REHAB_TEST_ASSESSMENT_MONGO_URI")
STANDALONE = os.environ.get("REHAB_TEST_ASSESSMENT_STANDALONE_URI")


@unittest.skipUnless(URI, "set a disposable local REHAB_TEST_ASSESSMENT_MONGO_URI")
class AssessmentScopeMongoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue(URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")))
        self.mongo = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.mongo["rehab_assessment_scope_" + uuid4().hex]
        self.doctor, self.patient, self.outside = [str(ObjectId()) for _ in range(3)]
        self.plan, self.other_plan, self.assessment, self.other_assessment = [ObjectId() for _ in range(4)]
        self.when = datetime.utcnow().replace(microsecond=0)
        await self.db.users.insert_many([
            {"_id": ObjectId(self.patient), "role": "patient", "practitioners": [self.doctor]},
            {"_id": ObjectId(self.outside), "role": "patient", "practitioners": ["other"]}])
        await self.db.rehab_plans.insert_many([
            {"_id": self.plan, "patient_id": self.patient, "name": "own"},
            {"_id": self.other_plan, "patient_id": self.outside, "name": "outside"}])
        await self.db.rehab_assessments.insert_many([
            {"_id": self.assessment, "patient_id": self.patient, "created_at": self.when,
             "updated_at": self.when, "notes": "own", "content_revision": 0},
            {"_id": self.other_assessment, "patient_id": self.outside, "created_at": self.when,
             "updated_at": self.when, "notes": "outside-secret", "content_revision": 0}])
        self.service = RehabilitationService(self.db)
        self.llm = AsyncMock(return_value={"summary": "synthetic"})
        self.service.agent_service.generate_assessment_analysis = self.llm
        app.dependency_overrides[get_database] = lambda: self.db
        app.dependency_overrides[get_rehabilitation_service] = lambda: self.service
        self.actor = UserResponse(id=self.doctor, role="doctor", name="synthetic",
            email="actor@example.com", is_active=True, createdAt=self.when, updatedAt=self.when)
        self.lookup = patch.object(UserService, "get_user_by_id", new=AsyncMock(side_effect=lambda *_: self.actor))
        self.lookup.start()
        token = jwt.encode({"sub": self.doctor, "token_type": "access", "exp": self.when + timedelta(hours=1)},
                           settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
                                      headers={"Authorization": "Bearer " + token})

    async def asyncTearDown(self):
        await self.http.aclose()
        self.lookup.stop()
        app.dependency_overrides.clear()
        await self.mongo.drop_database(self.db.name)
        self.mongo.close()

    def payload(self, plan=None):
        return AssessmentCreate(patient_id=self.patient, plan_id=plan, assessment_type="initial")

    async def test_cross_patient_comparison_and_analysis_neither_read_nor_write_other_assessment(self):
        before = await self.db.rehab_assessments.find_one({"_id": self.other_assessment})
        base = f"/api/rehabilitation/assessments/{self.other_assessment}"
        for method, suffix in (("GET", "/comparison"), ("POST", "/analyze")):
            response = await self.http.request(method, base + suffix, params={"patient_id": self.patient})
            self.assertIn(response.status_code, (400, 404), response.text)
            self.assertNotIn("outside-secret", response.text)
        self.llm.assert_not_awaited()
        self.assertEqual(await self.db.rehab_assessments.find_one({"_id": self.other_assessment}), before)
        denied = await self.http.get(base + "/comparison", params={"patient_id": self.outside})
        self.assertEqual(denied.status_code, 403)

    async def test_same_patient_comparison_and_analysis_remain_usable(self):
        base = f"/api/rehabilitation/assessments/{self.assessment}"
        response = await self.http.get(base + "/comparison", params={"patient_id": self.patient})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["current"]["notes"], "own")
        response = await self.http.post(base + "/analyze", params={"patient_id": self.patient, "plan_id": str(self.plan)})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["content_revision"], 1)

    async def test_assessment_creation_rejects_cross_patient_plan_without_partial_insert(self):
        payload = self.payload(str(self.other_plan)).model_dump()
        response = await self.http.post("/api/rehabilitation/assessments", json=payload)
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(await self.db.rehab_assessments.count_documents({}), 2)
        self.assertNotIn("assessments", await self.db.rehab_plans.find_one({"_id": self.other_plan}))

    async def test_same_patient_creation_links_atomically_and_rolls_back_after_insert_failure(self):
        original_insert = self.service.assessments_collection.insert_one
        async def fail_after_insert(*args, **kwargs):
            await original_insert(*args, **kwargs)
            raise RuntimeError("injected assessment persistence failure")
        with patch.object(self.service.assessments_collection, "insert_one", side_effect=fail_after_insert):
            with self.assertRaises(RuntimeError):
                await self.service.create_assessment(self.payload(str(self.plan)))
        self.assertEqual(await self.db.rehab_assessments.count_documents({}), 2)
        self.assertNotIn("assessments", await self.db.rehab_plans.find_one({"_id": self.plan}))
        result = await self.service.create_assessment(self.payload(str(self.plan)))
        self.assertEqual((await self.db.rehab_plans.find_one({"_id": self.plan}))["assessments"], [result["_id"]])

    async def test_owner_change_during_creation_retries_and_rejects_cross_patient_relation(self):
        read, resume = asyncio.Event(), asyncio.Event()
        original = self.service._get_same_patient_plan
        first = True
        async def pause(*args, **kwargs):
            nonlocal first
            value = await original(*args, **kwargs)
            if first:
                first = False
                read.set()
                await resume.wait()
            return value
        with patch.object(self.service, "_get_same_patient_plan", side_effect=pause):
            task = asyncio.create_task(self.service.create_assessment(self.payload(str(self.plan))))
            await asyncio.wait_for(read.wait(), 5)
            await self.db.rehab_plans.update_one({"_id": self.plan}, {"$set": {"patient_id": self.outside}})
            resume.set()
            with self.assertRaises(AppBaseException) as caught:
                await task
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(await self.db.rehab_assessments.count_documents({}), 2)

    async def test_late_analysis_cannot_overwrite_a_changed_or_transferred_assessment(self):
        for changes in ({"notes": "edited", "content_revision": 1}, {"patient_id": self.outside}):
            await self.db.rehab_assessments.update_one({"_id": self.assessment},
                {"$set": {"patient_id": self.patient, "content_revision": 0, "notes": "own"}, "$unset": {"ai_analysis": ""}})
            async def during_analysis(_):
                await self.db.rehab_assessments.update_one({"_id": self.assessment}, {"$set": changes})
                return {"summary": "must-not-save"}
            self.llm.side_effect = during_analysis
            with self.assertRaises(AppBaseException) as caught:
                await self.service.generate_assessment_with_llm(self.patient, previous_assessment_id=str(self.assessment))
            self.assertEqual(caught.exception.status_code, 409)
            self.assertNotIn("ai_analysis", await self.db.rehab_assessments.find_one({"_id": self.assessment}))

    async def test_analysis_plan_and_direct_update_are_same_patient_checked(self):
        with self.assertRaises(AppBaseException) as caught:
            await self.service.generate_assessment_with_llm(self.patient, plan_id=str(self.other_plan),
                previous_assessment_id=str(self.assessment))
        self.assertEqual(caught.exception.status_code, 404)
        self.llm.assert_not_awaited()
        self.assertIsNone(await self.service.update_assessment(str(self.other_assessment),
            AssessmentUpdate(notes="forbidden"), patient_id=self.patient))

    async def test_hard_delete_preserves_published_and_withdrawn_history(self):
        for state in ({"has_publication_history": True, "published_version_id": str(ObjectId())},
                      {"has_publication_history": True, "published_version_id": None, "publication_revision": 2}):
            await self.db.rehab_plans.update_one({"_id": self.plan}, {"$set": state})
            with self.assertRaises(AppBaseException) as caught:
                await self.service.delete_rehab_plan(str(self.plan))
            self.assertEqual(caught.exception.status_code, 409)
            self.assertIsNotNone(await self.db.rehab_plans.find_one({"_id": self.plan}))
        self.assertTrue(await self.service.delete_rehab_plan(str(self.other_plan)))


@unittest.skipUnless(STANDALONE, "set a disposable local REHAB_TEST_ASSESSMENT_STANDALONE_URI")
class AssessmentStandaloneTests(unittest.IsolatedAsyncioTestCase):
    async def test_linked_assessment_refuses_nontransactional_storage(self):
        self.assertTrue(STANDALONE.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")))
        mongo = AsyncIOMotorClient(STANDALONE, serverSelectionTimeoutMS=3000)
        db = mongo["rehab_assessment_standalone_" + uuid4().hex]
        try:
            plan = ObjectId()
            await db.rehab_plans.insert_one({"_id": plan, "patient_id": "own"})
            with self.assertRaises(AppBaseException) as caught:
                await RehabilitationService(db).create_assessment(AssessmentCreate(
                    patient_id="own", plan_id=str(plan), assessment_type="initial"))
            self.assertEqual(caught.exception.status_code, 503)
            self.assertEqual(await db.rehab_assessments.count_documents({}), 0)
            self.assertNotIn("assessments", await db.rehab_plans.find_one({"_id": plan}))
        finally:
            await mongo.drop_database(db.name)
            mongo.close()
