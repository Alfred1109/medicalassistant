"""Patient-link invariants against an explicitly isolated Mongo instance."""
import asyncio
import os
import unittest
from types import SimpleNamespace
from uuid import uuid4

from bson import ObjectId
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import ValidationError

from app.integrations.forms.patient_links import (
    PatientLinkRequest, bind_reviewed_patient, router,
)
from app.integrations.forms.catalog_router import get_catalog_client, require_catalog_admin
from app.db.mongodb import get_database

URI = os.environ.get("REHAB_TEST_PATIENT_LINK_MONGO_URI")


class Source:
    source_origin = "https://forms.example.test"

    async def get_patient_reference(self, project, center, subject):
        return {"source": {"system": "form-platform-11344", "environment": "production"},
                "project_id": project, "center_id": center, "subject_id": subject,
                "patient_id": subject + 100, "patient_archive_id": subject + 200}


class PatientLinkValidation(unittest.TestCase):
    def test_requires_explicit_boolean_review_and_no_extra_data(self):
        base = dict(local_patient_id=str(ObjectId()), project_id=4, center_id=1,
                    subject_id=2, evidence_reference="review-1")
        for extra in ({"identity_verified": False}, {"identity_verified": 1},
                      {"identity_verified": True, "patient_name": "untrusted"}):
            with self.assertRaises(ValidationError):
                PatientLinkRequest(**base, **extra)


@unittest.skipUnless(URI, "set isolated local REHAB_TEST_PATIENT_LINK_MONGO_URI")
class PatientLinkMongoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue(URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")))
        self.mongo = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.mongo["rehab_patient_link_test_" + uuid4().hex]
        self.patient = ObjectId()
        await self.db.users.insert_one({"_id": self.patient, "role": "patient", "is_active": True})
        self.actor = SimpleNamespace(id=str(ObjectId()), role="admin")
        self.source = Source()

    async def asyncTearDown(self):
        await self.mongo.drop_database(self.db.name)
        self.mongo.close()

    def payload(self, **overrides):
        values = dict(local_patient_id=str(self.patient), project_id=4, center_id=1,
                      subject_id=2, evidence_reference="review-record-1", identity_verified=True)
        return PatientLinkRequest(**(values | overrides))

    async def test_creates_one_audited_link_and_never_creates_a_user(self):
        link = await bind_reviewed_patient(self.db, self.source, self.actor, self.payload())
        self.assertEqual(link["status"], "verified")
        self.assertEqual(await self.db.users.count_documents({}), 1)
        stored = await self.db.external_patient_links.find_one({"_id": ObjectId(link["id"])})
        self.assertEqual(stored["verified_by"], self.actor.id)
        self.assertEqual(stored["audit"][0]["action"], "verify_link")
        self.assertEqual(stored["source_origin"], self.source.source_origin)

    async def test_concurrent_competing_matches_allow_only_one(self):
        other = ObjectId()
        await self.db.users.insert_one({"_id": other, "role": "patient", "is_active": True})
        out = await asyncio.gather(
            bind_reviewed_patient(self.db, self.source, self.actor, self.payload()),
            bind_reviewed_patient(self.db, self.source, self.actor, self.payload(local_patient_id=str(other))),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(x, dict) for x in out), 1)
        self.assertEqual(await self.db.external_patient_links.count_documents({"status": "verified"}), 1)

    async def test_object_id_case_variants_cannot_bind_same_local_patient_twice(self):
        await bind_reviewed_patient(self.db, self.source, self.actor, self.payload())
        with self.assertRaises(HTTPException) as error:
            await bind_reviewed_patient(self.db, self.source, self.actor,
                                        self.payload(local_patient_id=str(self.patient).upper(), subject_id=3))
        self.assertEqual(error.exception.status_code, 409)

    async def test_wrong_reference_or_untrusted_production_origin_never_writes(self):
        source = Source()
        original = source.get_patient_reference
        async def wrong(*args):
            return dict(await original(*args), center_id=999)
        source.get_patient_reference = wrong
        with self.assertRaises(HTTPException):
            await bind_reviewed_patient(self.db, source, self.actor, self.payload())
        source = Source()
        source.source_origin = "http://forms.example.test"
        with self.assertRaises(HTTPException):
            await bind_reviewed_patient(self.db, source, self.actor, self.payload())
        self.assertEqual(await self.db.external_patient_links.count_documents({}), 0)

    async def test_revoke_preserves_history_and_allows_explicit_corrected_link(self):
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[require_catalog_admin] = lambda: self.actor
        app.dependency_overrides[get_database] = lambda: self.db
        app.dependency_overrides[get_catalog_client] = lambda: self.source
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            first = await c.post("/api/integrations/forms/patient-links", json=self.payload().model_dump())
            self.assertEqual(first.status_code, 201)
            link_id = first.json()["id"]
            revoked = await c.post(f"/api/integrations/forms/patient-links/{link_id}/revoke", json={"reason": "核对纠错"})
            self.assertEqual(revoked.status_code, 200)
            second = await c.post("/api/integrations/forms/patient-links", json=self.payload(subject_id=3).model_dump())
            self.assertEqual(second.status_code, 201)
            rows = await self.db.external_patient_links.find({}).to_list(None)
            self.assertEqual(sorted(row["status"] for row in rows), ["revoked", "verified"])
            old = next(row for row in rows if row["status"] == "revoked")
            self.assertEqual([e["action"] for e in old["audit"]], ["verify_link", "revoke_link"])

    async def test_non_admin_cannot_read_or_modify_links(self):
        app = FastAPI()
        app.include_router(router, prefix="/api")
        from app.core.auth import get_current_active_user
        app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(id="x", role="doctor")
        app.dependency_overrides[get_database] = lambda: self.db
        app.dependency_overrides[get_catalog_client] = lambda: self.source
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            for method, url, body in (("GET", "/api/integrations/forms/patient-links", None),
                                      ("POST", "/api/integrations/forms/patient-links", self.payload().model_dump())):
                result = await c.request(method, url, json=body)
                self.assertEqual(result.status_code, 403)
        self.assertEqual(await self.db.external_patient_links.count_documents({}), 0)

    async def test_same_patient_can_add_reviewed_project_context_without_replacing_history(self):
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[require_catalog_admin] = lambda: self.actor
        app.dependency_overrides[get_database] = lambda: self.db
        app.dependency_overrides[get_catalog_client] = lambda: self.source
        link = await bind_reviewed_patient(self.db, self.source, self.actor, self.payload())
        async def other_subject_same_patient(project, center, subject):
            return {"source": {"system": "form-platform-11344", "environment": "production"},
                    "project_id": project, "center_id": center, "subject_id": subject,
                    "patient_id": 102, "patient_archive_id": 205}
        self.source.get_patient_reference = other_subject_same_patient
        payload = {"project_id": 5, "center_id": 2, "subject_id": 8,
                   "evidence_reference": "review-2", "identity_verified": True}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            url = f"/api/integrations/forms/patient-links/{link['id']}/contexts"
            self.assertEqual((await c.post(url, json=payload)).status_code, 200)
            self.assertEqual((await c.post(url, json=payload)).status_code, 409)
            # A later center assignment is a separately reviewed context, not
            # a reason to discard the original record.
            moved = {**payload, "center_id": 3, "evidence_reference": "review-3"}
            self.assertEqual((await c.post(url, json=moved)).status_code, 200)
            self.assertEqual((await c.post(url, json=moved)).status_code, 409)
        stored = await self.db.external_patient_links.find_one({"_id": ObjectId(link["id"])})
        self.assertEqual([x["subject_id"] for x in stored["references"]], [2, 8, 8])
        self.assertEqual([x["action"] for x in stored["audit"]], ["verify_link", "add_context", "add_context"])
