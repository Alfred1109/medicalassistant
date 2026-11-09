"""Reviewed form selection against isolated Mongo; no fill session is created."""
import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from bson import ObjectId
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import ValidationError

from app.core.auth import get_current_active_user
from app.db.mongodb import get_database
from app.integrations.forms.form_bindings import FormBindingRequest, bind_form, router
from app.integrations.forms.catalog_router import get_catalog_client

URI = os.environ.get("REHAB_TEST_PATIENT_LINK_MONGO_URI")


def source_result():
    ref = {"form_id": 9, "family_id": 10, "version": 3, "version_state": "current",
           "definition_sha256": "a" * 64, "crf_code": None, "crf_version": None}
    return {"source": {"system": "form-platform-11344", "environment": "production"},
            "form": {"form_id": 9, "project_id": 4, "title": "测试问卷", "status": "active",
                     "current_version": ref}, "version": ref}


class FormBindingValidation(unittest.TestCase):
    def test_requires_explicit_purpose_and_confirmation(self):
        base = dict(project_id=4, form_id=9, version=3, evidence_reference="review-1")
        for extra in ({"purpose": "followup", "confirmed": False},
                      {"purpose": "followup", "confirmed": 1},
                      {"purpose": "unknown", "confirmed": True}):
            with self.assertRaises(ValidationError):
                FormBindingRequest(**base, **extra)


@unittest.skipUnless(URI, "set isolated local REHAB_TEST_PATIENT_LINK_MONGO_URI")
class FormBindingMongoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue(URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")))
        self.mongo = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.mongo["rehab_form_binding_test_" + uuid4().hex]
        self.actor = SimpleNamespace(id=str(ObjectId()), role="admin")
        self.client = SimpleNamespace(source_origin="https://forms.example.test")
        self.payload = FormBindingRequest(project_id=4, form_id=9, version=3, purpose="followup",
                                          evidence_reference="review-1", confirmed=True)

    async def asyncTearDown(self):
        await self.mongo.drop_database(self.db.name)
        self.mongo.close()

    async def test_saves_source_verified_version_and_audit_only(self):
        self.client.get_form_definition = AsyncMock(return_value=source_result())
        out = await bind_form(self.db, self.client, self.actor, self.payload)
        self.client.get_form_definition.assert_awaited_once_with(9, version=3)
        row = await self.db.external_form_bindings.find_one({"_id": ObjectId(out["id"])})
        self.assertEqual(row["version_ref"]["definition_sha256"], "a" * 64)
        self.assertEqual(row["audit"][0]["actor_id"], self.actor.id)
        self.assertEqual(await self.db.list_collection_names(), ["external_form_bindings"])

    async def test_concurrent_identical_binding_only_one_succeeds(self):
        with patch("app.integrations.forms.form_bindings.catalog_service.form_version", new=AsyncMock(return_value=source_result())):
            out = await asyncio.gather(bind_form(self.db, self.client, self.actor, self.payload),
                                       bind_form(self.db, self.client, self.actor, self.payload), return_exceptions=True)
        self.assertEqual(sum(isinstance(x, dict) for x in out), 1)
        self.assertEqual(await self.db.external_form_bindings.count_documents({"status": "active"}), 1)

    async def test_wrong_project_or_retired_version_does_not_write(self):
        for mutation in ("project", "state"):
            result = source_result()
            if mutation == "project": result["form"]["project_id"] = 999
            else: result["version"]["version_state"] = "retired"
            with patch("app.integrations.forms.form_bindings.catalog_service.form_version", new=AsyncMock(return_value=result)):
                with self.assertRaises(HTTPException):
                    await bind_form(self.db, self.client, self.actor, self.payload)
        self.assertEqual(await self.db.external_form_bindings.count_documents({}), 0)

    async def test_non_admin_cannot_list_or_create(self):
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(role="doctor", id="x")
        app.dependency_overrides[get_database] = lambda: self.db
        app.dependency_overrides[get_catalog_client] = lambda: self.client
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            self.assertEqual((await client.get("/api/integrations/forms/form-bindings")).status_code, 403)
            self.assertEqual((await client.post("/api/integrations/forms/form-bindings", json=self.payload.model_dump())).status_code, 403)
