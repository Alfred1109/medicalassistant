"""Launch credentials remain transient and bind to reviewed task authority."""
import json
import os
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit
from uuid import uuid4

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from app.integrations.forms import models, service
from app.integrations.forms.client import FormPlatformError
from app.integrations.identity.service import FillDelegation, digest
from test_integration_forms_contract import make_operator, reviewed_documents


class LaunchResponseTests(unittest.TestCase):
    def setUp(self):
        self.task = {"_id": ObjectId(), "session": {"session_uuid": "synthetic-session"},
                     "allowed_origin": "https://rehab.example"}
        self.body = {"mode": "launch", "action": "https://form.example/integration/embed/synthetic-session",
                     "token": "transient-launch-credential", "session_uuid": "synthetic-session",
                     "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()}

    def test_launch_and_resume_reduce_to_known_fields(self):
        result = service._validated_launch_response(self.body, self.task, "https://form.example")
        self.assertEqual(result["token"], self.body["token"])
        resumed = dict(self.body, mode="resume", url="https://form.example/integration/resume/synthetic-session")
        result = service._validated_launch_response(resumed, self.task, "https://form.example")
        self.assertEqual(result["mode"], "resume")
        self.assertNotIn("token", result)
        self.assertNotIn("action", result)

    def test_other_origin_path_session_or_expired_response_rejected_without_secret(self):
        mutations = [
            {"action": "https://foreign.example/integration/embed/synthetic-session"},
            {"action": "https://form.example/integration/embed/another-session"},
            {"action": "https://form.example/integration/embed/synthetic-session?token=secret"},
            {"action": "https://user:password@form.example/integration/embed/synthetic-session"},
            {"session_uuid": "another-session"},
            {"expires_at": "2000-01-01T00:00:00Z"},
            {"expires_at": "2099-01-01T00:00:00"},
            {"token": "bad token"},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaises(service.FormIntegrationError) as raised:
                    service._validated_launch_response(dict(self.body, **mutation), self.task, "https://form.example")
                self.assertNotIn(self.body["token"], str(raised.exception))

    def test_creation_record_ignores_all_launch_material(self):
        task = models.FollowUpFillTask.new_task(patient_id="patient", operator_id="actor", operator_role="doctor",
            remote_refs={}, allowed_origin="https://rehab.example", ma_task_ref=None, visit_code=None,
            visit_name=None, ttl_seconds=None)
        task.record_remote_session({"session_uuid": "synthetic-session", "embed_token": "secret-one",
            "embed_url": "https://form.example/integration/embed/secret-one", "token": "secret-two"})
        stored = json.dumps(task.doc, default=str)
        self.assertNotIn("secret-one", stored)
        self.assertNotIn("secret-two", stored)
        self.assertNotIn("embed_url", stored)


@unittest.skipUnless(os.environ.get("REHAB_TEST_LAUNCH_MONGO_URI"), "isolated replica-set URI required")
class LaunchMongoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        uri = os.environ["REHAB_TEST_LAUNCH_MONGO_URI"]
        if urlsplit(uri).hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError("explicit loopback instance required")
        self.mongo = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=4000)
        self.db = self.mongo["rehab_launch_test_" + uuid4().hex]
        hello = await self.db.command("hello")
        self.assertTrue(hello.get("setName"))
        self.env = patch.dict(os.environ, {"FORM_PLATFORM_FILL_ENABLED": "true"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.actor = make_operator()
        patient_id = str(ObjectId())
        await self.db.users.insert_many([
            {"_id": ObjectId(self.actor.id), "role": self.actor.role, "is_active": True},
            {"_id": ObjectId(patient_id), "role": "patient", "practitioners": [self.actor.id]},
        ])
        link, binding = reviewed_documents(patient_id)
        await self.db.external_patient_links.insert_one(link)
        await self.db.external_form_bindings.insert_one(binding)
        self.link = link
        self.record = {"_id": digest("synthetic-cookie"), "issuer": "https://form.example", "subject": "source-subject",
            "binding_revision": "a" * 64, "expires_at": datetime.utcnow() + timedelta(minutes=5)}
        await self.db.oidc_application_sessions.insert_one(deepcopy(self.record))
        await self.db.oidc_principal_bindings.insert_one({"_id": digest("https://form.example\0source-subject"),
            "enabled": True, "actor_id": self.actor.id, "approved_role": self.actor.role,
            "authorization_revision": "a" * 64})
        oidc = SimpleNamespace(settings=SimpleNamespace(issuer="https://form.example"),
            actor_for_session=AsyncMock(return_value=(self.record, {"_id": ObjectId(self.actor.id), "role": self.actor.role})))
        self.delegation = FillDelegation(oidc, "synthetic-cookie", "source-access-credential", self.record, self.actor.id, self.actor.role)
        task = models.FollowUpFillTask.new_task(patient_id=patient_id, operator_id=self.actor.id, operator_role=self.actor.role,
            remote_refs={"project_id": 1, "center_id": 2, "subject_id": 3, "questionnaire_id": 4, "remote_operator_user_id": 7},
            allowed_origin="https://rehab.example", ma_task_ref=None, visit_code=None, visit_name=None, ttl_seconds=None)
        task.doc["_id"] = ObjectId()
        task.doc["mutation_version"] = 0
        task.record_remote_session({"session_uuid": "synthetic-session"})
        task.doc["identity_context"] = {key: self.record[key] for key in ("issuer", "subject", "binding_revision")}
        task.doc["reviewed_context"] = {"patient_link_id": link["_id"], "form_binding_id": binding["_id"],
            "reference": link["reference"], "version_ref": binding["version_ref"], "purpose": binding["purpose"]}
        await self.db[models.COLLECTION_NAME].insert_one(task.doc)
        self.task = task.doc
        self.body = {"mode": "launch", "action": "https://form.example/integration/embed/synthetic-session",
            "token": "transient-launch-credential", "session_uuid": "synthetic-session",
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()}
        self.client = SimpleNamespace(source_origin="https://form.example", launch_fill_session=AsyncMock(return_value=self.body))

    async def asyncTearDown(self):
        if hasattr(self, "db"):
            await self.mongo.drop_database(self.db.name)
        if hasattr(self, "mongo"):
            self.mongo.close()

    async def launch(self):
        return await service.launch_fill_task(self.db, self.client, str(self.task["_id"]), self.actor, delegation=self.delegation)

    async def test_launch_credentials_never_enter_database(self):
        result = await self.launch()
        self.assertEqual(result["token"], self.body["token"])
        self.client.launch_fill_session.assert_awaited_once_with("synthetic-session", source_access_token=self.delegation.token)
        for collection in await self.db.list_collection_names():
            rows = await self.db[collection].find({}).to_list(None)
            stored = json.dumps(rows, default=str)
            self.assertNotIn(self.body["token"], stored)
            self.assertNotIn(self.delegation.token, stored)

    async def test_revocation_while_source_launches_blocks_response(self):
        async def revoked(*args, **kwargs):
            await self.db.external_patient_links.update_one({"_id": self.link["_id"]}, {"$set": {"status": "revoked"}})
            return self.body
        self.client.launch_fill_session.side_effect = revoked
        with self.assertRaises(service.FormIntegrationError) as raised:
            await self.launch()
        self.assertEqual(raised.exception.error_code, "TASK_REVIEW_REVOKED")

    async def test_logout_while_source_launches_blocks_response(self):
        async def logout(*args, **kwargs):
            await self.db.oidc_application_sessions.delete_one({"_id": self.record["_id"]})
            return self.body
        self.client.launch_fill_session.side_effect = logout
        with self.assertRaises(service.FormIntegrationError) as raised:
            await self.launch()
        self.assertEqual(raised.exception.error_code, "SOURCE_IDENTITY_CHANGED")

    async def test_source_error_cannot_reflect_credential(self):
        self.client.launch_fill_session.side_effect = FormPlatformError(self.body["token"], status_code=409)
        with self.assertRaises(service.FormIntegrationError) as raised:
            await self.launch()
        self.assertNotIn(self.body["token"], str(raised.exception))
        self.assertEqual(raised.exception.status_code, 409)
