"""Patient-owned form task authorization, source status sync and bridge boundaries."""
import asyncio
import os
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from bson import ObjectId
from cryptography.fernet import Fernet
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import SecretStr

from app.core.config import settings
from app.db.mongodb import get_database
from app.integrations.forms import models, patient_self, service
from app.integrations.forms.client import FormPlatformClient, FormPlatformError
from app.integrations.forms.router import _require_patient_session, router as forms_router
from app.integrations.identity.config import OidcSettings
from app.integrations.identity.service import digest, ensure_identity_indexes
from app.models.health_record import FollowUpRecord
from app.schemas.followup import ReviewFollowUpRequest
from app.services.followup_service import FollowupService


class PatientSelfCallbackHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_callback_requires_independent_secret_at_http_boundary(self):
        app = FastAPI()
        app.include_router(forms_router, prefix="/api")
        app.dependency_overrides[get_database] = lambda: object()
        transport = httpx.ASGITransport(app=app)
        payload = {"rehabman_task_ref": "task-ref", "patient_actor_subject": "subject",
                   "source_session_id": "session_1", "action": "read", "pinned_version_sha256": "a" * 64}
        with patch.object(patient_self.settings, "REHAB_SELF_FILL_CALLBACK_SECRET", None):
            async with httpx.AsyncClient(transport=transport, base_url="https://rehab.test") as client:
                no_auth = await client.post("/api/integrations/forms/patient-self/authorize", json=payload)
                wrong = await client.post("/api/integrations/forms/patient-self/authorize", json=payload,
                                          headers={"Authorization": "Bearer wrong"})
        self.assertEqual(no_auth.status_code, 401)
        self.assertEqual(wrong.status_code, 401)
        app.dependency_overrides.clear()

    async def test_callback_secret_is_constant_time_checked_and_payload_is_exact(self):
        with patch.object(patient_self.settings, "REHAB_SELF_FILL_CALLBACK_SECRET", SecretStr("independent-test-secret")):
            with self.assertRaises(patient_self.FormIntegrationError) as raised:
                await patient_self.callback_authorize(object(), {}, "wrong")
        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(raised.exception.error_code, "SELF_FILL_CALLBACK_UNAUTHORIZED")


class PatientSelfBrowserSessionTests(unittest.TestCase):
    def test_patient_reads_and_launch_require_oneid_browser_cookie_or_mini_session(self):
        patient = SimpleNamespace(role="patient")
        browser = SimpleNamespace(state=SimpleNamespace(identity_transport=None),
                                  cookies={"__Host-rehab_session": "opaque-session"})
        mini = SimpleNamespace(state=SimpleNamespace(identity_transport="mini_bearer"), cookies={})
        no_session = SimpleNamespace(state=SimpleNamespace(identity_transport=None), cookies={})
        with patch("app.integrations.identity.access.unified_authentication", return_value=True):
            _require_patient_session(browser, patient)
            _require_patient_session(mini, patient)
            with self.assertRaises(patient_self.FormIntegrationError) as raised:
                _require_patient_session(no_session, patient)
        self.assertEqual(raised.exception.error_code, "SOURCE_IDENTITY_REQUIRED")

    def test_staff_cannot_use_patient_self_session_gate(self):
        request = SimpleNamespace(state=SimpleNamespace(identity_transport=None), cookies={})
        with self.assertRaises(patient_self.FormIntegrationError) as raised:
            _require_patient_session(request, SimpleNamespace(role="doctor"))
        self.assertEqual(raised.exception.error_code, "SELF_FILL_ROLE_REQUIRED")

class PatientSelfClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_source_client_uses_dedicated_session_routes_and_no_patient_bearer(self):
        seen = []
        def handler(request):
            seen.append(request)
            if request.method == "POST" and request.url.path == "/integration/v1/patient-self-fill-sessions":
                return httpx.Response(201, json={"session_id": "psf_123", "status": "created",
                    "launch_url": "https://form.example/self-fill/psf_123", "launch_token": "synthetic-one-use",
                    "expires_at": (datetime.utcnow() + timedelta(minutes=5)).isoformat() + "Z",
                    "questionnaire_version_ref": {"form_id": 4, "family_id": 4, "version": 1, "definition_sha256": "a" * 64}})
            if request.url.path.endswith("/resume"):
                return httpx.Response(200, json={"session_id": "psf_123", "status": "embedded",
                    "launch_url": "https://form.example/self-fill/psf_123", "launch_token": "rotated-token",
                    "expires_at": (datetime.utcnow() + timedelta(minutes=5)).isoformat() + "Z",
                    "questionnaire_version_ref": {"form_id": 4, "family_id": 4, "version": 1, "definition_sha256": "a" * 64}})
            if request.url.path.endswith("/psf_123/response"):
                return httpx.Response(200, json={"session": {"session_uuid": "psf_123"}, "response": {"response_id": 42}})
            return httpx.Response(200, json={"session_id": "psf_123", "status": "submitted"})
        client = FormPlatformClient("https://form.example", "client", "server-secret", 2,
                                    transport=httpx.MockTransport(handler))
        payload = {"rehabman_task_ref": "task-ref", "patient_actor_subject": "patient-subject"}
        await client.create_patient_self_fill_session(payload, idempotency_key="b" * 64)
        await client.resume_patient_self_fill_session("psf_123", payload, idempotency_key="c" * 64)
        await client.get_patient_self_fill_session("psf_123")
        await client.get_patient_self_fill_response("psf_123")
        await client.revoke_patient_self_fill_session("psf_123", {"reason": "requested", "rehabman_task_ref": "task-ref"})
        self.assertEqual([request.url.path for request in seen], [
            "/integration/v1/patient-self-fill-sessions",
            "/integration/v1/patient-self-fill-sessions/psf_123/resume",
            "/integration/v1/patient-self-fill-sessions/psf_123",
            "/integration/v1/patient-self-fill-sessions/psf_123/response",
            "/integration/v1/patient-self-fill-sessions/psf_123/revoke",
        ])
        self.assertEqual(seen[0].headers["idempotency-key"], "b" * 64)
        self.assertEqual(seen[1].headers["idempotency-key"], "c" * 64)
        self.assertEqual(seen[0].headers["authorization"], "Bearer client.server-secret")
        self.assertNotIn("X-Source-Access-Token", seen[0].headers)
        with self.assertRaises(FormPlatformError):
            await client.get_patient_self_fill_response("bad/session")


MONGO_URI = os.environ.get("REHAB_TEST_SELF_FILL_MONGO_URI")


@unittest.skipUnless(MONGO_URI, "set isolated local replica-set REHAB_TEST_SELF_FILL_MONGO_URI")
class PatientSelfMongoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if not MONGO_URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")):
            raise RuntimeError("explicit loopback test Mongo URI required")
        self.mongo = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=4000)
        self.db = self.mongo["rehab_patient_self_test_" + uuid4().hex]
        hello = await self.db.command("hello")
        self.assertTrue(hello.get("setName"), "patient self-fill tests require isolated replica set transactions")
        await ensure_identity_indexes(self.db)
        self.issuer = "https://identity.test"
        self.subject = "patient-opaque-subject"
        self.patient_id = str(ObjectId())
        self.actor_id = ObjectId(self.patient_id)
        self.doctor_id = str(ObjectId())
        self.session_cookie = "patient-browser-cookie"
        self.session_hash = digest(self.session_cookie)
        self.binding_revision = "r" * 64
        await self.db.users.insert_many([
            {"_id": self.actor_id, "role": "patient", "is_active": True, "practitioners": [self.doctor_id]},
            {"_id": ObjectId(self.doctor_id), "role": "doctor", "is_active": True},
        ])
        await self.db.external_patient_links.insert_one({
            "_id": ObjectId(), "local_patient_id": self.patient_id, "status": "verified",
            "source_origin": "https://form.example", "reference": self.reference(), "references": [self.reference()],
            "verified_by": "reviewer", "verified_at": datetime.utcnow(), "evidence_reference": "review/self-fill"})
        self.link = await self.db.external_patient_links.find_one({"local_patient_id": self.patient_id})
        await self.db.external_form_bindings.insert_one({
            "_id": ObjectId(), "status": "active", "source_origin": "https://form.example",
            "source": {"system": "form-platform-11344", "environment": "pilot"},
            "project_id": 1, "form_id": 4, "version": 1, "purpose": "followup",
            "version_ref": self.version_ref(), "verified_by": "reviewer", "verified_at": datetime.utcnow(),
            "evidence_reference": "review/form"})
        self.form = await self.db.external_form_bindings.find_one({"project_id": 1})
        await self.db.oidc_principal_bindings.insert_one({
            "_id": digest(self.issuer + "\0" + self.subject), "issuer": self.issuer,
            "subject": self.subject, "actor_id": self.patient_id, "enabled": True,
            "approved_role": "patient", "authorization_revision": self.binding_revision,
            "verified_by": "reviewer", "verified_at": datetime.utcnow(), "evidence_reference": "review/oidc"})
        self.source_record = {"_id": self.session_hash, "issuer": self.issuer, "subject": self.subject,
            "binding_revision": self.binding_revision, "expires_at": datetime.utcnow() + timedelta(hours=1)}
        await self.db.oidc_application_sessions.insert_one(self.source_record.copy())
        self.mini_id = digest("patient-mini-token")
        await self.db.oidc_mini_sessions.insert_one({"_id": self.mini_id, "source_session_id": self.session_hash,
            "actor_id": self.patient_id, "expires_at": datetime.utcnow() + timedelta(hours=1)})
        self.task_id = ObjectId()
        self.task = {
            "_id": self.task_id, "task_type": patient_self.TASK_TYPE, "patient_id": self.patient_id,
            "operator": {"user_id": self.doctor_id, "role": "doctor"}, "remote_refs": {
                "project_id": 1, "center_id": 2, "subject_id": 3, "questionnaire_id": 4},
            "allowed_origin": "https://rehab.example", "status": "session_created", "mutation_version": 0,
            "created_at": datetime.utcnow(), "session": {"session_uuid": None},
            "reviewed_context": {"patient_link_id": str(self.link["_id"]), "form_binding_id": str(self.form["_id"]),
                "reference": self.reference(), "version_ref": self.version_ref(), "purpose": "followup"},
            "patient_self": {"status": "active", "rehabman_task_ref": "rehabman-self-test",
                "source_session_id": "psf_test", "source_status": "created",
                "patient_actor_id": self.patient_id, "patient_actor_subject": self.subject,
                "patient_issuer": self.issuer, "patient_binding_revision": self.binding_revision,
                "mini_session_id": self.mini_id, "source_session_hash": self.session_hash,
                "pinned_version_sha256": "a" * 64},
        }
        await self.db[models.COLLECTION_NAME].insert_one(self.task.copy())
        self.config = OidcSettings(_env_file=None, enabled=True, authentication_mode="oidc", issuer=self.issuer,
            public_base_url="https://rehab.example", client_id="rehab", client_secret="secret",
            session_encryption_key=Fernet.generate_key().decode())

    def reference(self):
        return {"project_id": 1, "center_id": 2, "subject_id": 3, "patient_id": 8, "patient_archive_id": 9,
                "source": {"system": "form-platform-11344", "environment": "pilot"}}

    def version_ref(self):
        return {"form_id": 4, "family_id": 4, "version": 1, "version_state": "current", "definition_sha256": "a" * 64}

    async def asyncTearDown(self):
        await self.mongo.drop_database(self.db.name)
        self.mongo.close()

    async def test_callback_fences_live_patient_mini_identity_and_reviewed_source(self):
        actor = {"_id": self.actor_id, "role": "patient", "is_active": True}
        oidc = SimpleNamespace(actor_for_session_hash=AsyncMock(return_value=(self.source_record, actor)))
        with patch.object(patient_self.settings, "REHAB_SELF_FILL_CALLBACK_SECRET", SecretStr("independent-secret")), \
             patch("app.integrations.identity.service.OidcClient", return_value=oidc):
            await patient_self.callback_authorize(self.db, {
                "rehabman_task_ref": "rehabman-self-test", "patient_actor_subject": self.subject,
                "source_session_id": "psf_test", "action": "submit", "pinned_version_sha256": "a" * 64},
                "independent-secret")
        stored = await self.db[models.COLLECTION_NAME].find_one({"_id": self.task_id})
        # The callback authorizes the operation; GET source status is the evidence of submission.
        self.assertEqual(stored["patient_self"]["status"], "active")
        self.assertEqual(stored["patient_self"]["last_authorized_action"], "submit")
        with patch.object(patient_self.settings, "REHAB_SELF_FILL_CALLBACK_SECRET", SecretStr("independent-secret")):
            await self.db.external_form_bindings.update_one({"_id": self.form["_id"]}, {"$set": {"status": "revoked"}})
            with self.assertRaises(patient_self.FormIntegrationError) as raised:
                await patient_self.callback_authorize(self.db, {
                    "rehabman_task_ref": "rehabman-self-test", "patient_actor_subject": self.subject,
                    "source_session_id": "psf_test", "action": "read", "pinned_version_sha256": "a" * 64},
                    "independent-secret")
        self.assertEqual(raised.exception.status_code, 409)

    async def test_callback_rechecks_canonical_account_link_after_outer_identity_check(self):
        canonical_id = await self._switch_to_canonical_patient()
        actor = {"_id": self.actor_id, "role": "patient", "is_active": True}
        oidc = SimpleNamespace(actor_for_session_hash=AsyncMock(return_value=(self.source_record, actor)))
        original = patient_self._verify_live_patient_identity
        async def verify_then_unlink(*args, **kwargs):
            result = await original(*args, **kwargs)
            await self.db.patient_account_links.update_one({"account_id": self.patient_id},
                {"$set": {"status": "disabled"}})
            return result
        with patch.object(patient_self.settings, "REHAB_SELF_FILL_CALLBACK_SECRET", SecretStr("independent-secret")), \
             patch("app.integrations.identity.service.OidcClient", return_value=oidc), \
             patch.object(patient_self, "_verify_live_patient_identity", side_effect=verify_then_unlink):
            with self.assertRaises(patient_self.FormIntegrationError) as raised:
                await patient_self.callback_authorize(self.db, {
                    "rehabman_task_ref": "rehabman-self-test", "patient_actor_subject": self.subject,
                    "source_session_id": "psf_test", "action": "read", "pinned_version_sha256": "a" * 64},
                    "independent-secret")
        self.assertEqual(raised.exception.error_code, "SELF_PATIENT_UNAVAILABLE")
        stored = await self.db[models.COLLECTION_NAME].find_one({"_id": self.task_id})
        self.assertNotIn("last_authorized_action", stored["patient_self"])
        self.assertEqual(stored["patient_id"], canonical_id)

    async def test_callback_rechecks_legacy_patient_document_inside_transaction(self):
        actor = {"_id": self.actor_id, "role": "patient", "is_active": True}
        oidc = SimpleNamespace(actor_for_session_hash=AsyncMock(return_value=(self.source_record, actor)))
        original = patient_self._verify_live_patient_identity
        async def verify_then_disable(*args, **kwargs):
            result = await original(*args, **kwargs)
            await self.db.users.update_one({"_id": self.actor_id}, {"$set": {"is_active": False}})
            return result
        with patch.object(patient_self.settings, "REHAB_SELF_FILL_CALLBACK_SECRET", SecretStr("independent-secret")), \
             patch("app.integrations.identity.service.OidcClient", return_value=oidc), \
             patch.object(patient_self, "_verify_live_patient_identity", side_effect=verify_then_disable):
            with self.assertRaises(patient_self.FormIntegrationError) as raised:
                await patient_self.callback_authorize(self.db, {
                    "rehabman_task_ref": "rehabman-self-test", "patient_actor_subject": self.subject,
                    "source_session_id": "psf_test", "action": "read", "pinned_version_sha256": "a" * 64},
                    "independent-secret")
        self.assertEqual(raised.exception.error_code, "SELF_PATIENT_UNAVAILABLE")
        stored = await self.db[models.COLLECTION_NAME].find_one({"_id": self.task_id})
        self.assertNotIn("last_authorized_action", stored["patient_self"])

    async def test_callback_retries_conflicting_canonical_unlink_then_denies(self):
        await self._switch_to_canonical_patient()
        actor = {"_id": self.actor_id, "role": "patient", "is_active": True}
        oidc = SimpleNamespace(actor_for_session_hash=AsyncMock(return_value=(self.source_record, actor)))
        original = patient_self._lock_patient_self_mapping
        race_once = True
        async def unlink_during_transaction(db, session, patient_actor, patient_id):
            nonlocal race_once
            if race_once:
                race_once = False
                # Another request commits the unlink after this transaction
                # took its snapshot but before the account-link write fence.
                await db.patient_account_links.update_one({"account_id": self.patient_id},
                    {"$set": {"status": "disabled"}})
            return await original(db, session, patient_actor, patient_id)
        with patch.object(patient_self.settings, "REHAB_SELF_FILL_CALLBACK_SECRET", SecretStr("independent-secret")), \
             patch("app.integrations.identity.service.OidcClient", return_value=oidc), \
             patch.object(patient_self, "_lock_patient_self_mapping", side_effect=unlink_during_transaction):
            with self.assertRaises(patient_self.FormIntegrationError) as raised:
                await patient_self.callback_authorize(self.db, {
                    "rehabman_task_ref": "rehabman-self-test", "patient_actor_subject": self.subject,
                    "source_session_id": "psf_test", "action": "save", "pinned_version_sha256": "a" * 64},
                    "independent-secret")
        self.assertFalse(race_once)
        self.assertIn(raised.exception.error_code, {"SELF_PATIENT_UNAVAILABLE", "SELF_FILL_TASK_CHANGED"})
        stored = await self.db[models.COLLECTION_NAME].find_one({"_id": self.task_id})
        self.assertNotIn("last_authorized_action", stored["patient_self"])

    async def test_bridge_transaction_retries_after_canonical_unlink_and_preserves_ticket(self):
        await self._switch_to_canonical_patient()
        oidc = self._mini_oidc()
        source, _created, _resumed, _revoked = self._launch_client()
        actor = SimpleNamespace(id=self.patient_id, role="patient")
        with patch("app.integrations.identity.config.oidc_settings.public_base_url", "https://rehab.example"):
            launched = await patient_self.launch_task(self.db, source, str(self.task_id), actor,
                mini_token="patient-mini-token", oidc_client=oidc, settings_obj=self.config)
        ticket = launched["webviewUrl"].rsplit("/", 1)[-1]
        source_for_cookie = SimpleNamespace(actor_for_session=AsyncMock(return_value=(
            self.source_record, {"_id": self.actor_id, "role": "patient", "is_active": True})))
        original = patient_self._lock_patient_self_mapping
        race_once = True
        async def unlink_during_transaction(db, session, patient_actor, patient_id):
            nonlocal race_once
            if race_once:
                race_once = False
                await db.patient_account_links.update_one({"account_id": self.patient_id},
                    {"$set": {"status": "disabled"}})
            return await original(db, session, patient_actor, patient_id)
        with patch.object(patient_self, "_lock_patient_self_mapping", side_effect=unlink_during_transaction):
            result = await patient_self.consume_launch_bridge(self.db, ticket, self.session_cookie,
                source_for_cookie, self.config)
        self.assertEqual(result.status_code, 403)
        self.assertFalse(race_once)
        self.assertEqual(await self.db[patient_self.BRIDGE_COLLECTION].count_documents({}), 1)

    async def test_remote_submit_status_is_authoritative_for_patient_and_staff_views(self):
        remote = SimpleNamespace(get_patient_self_fill_session=AsyncMock(return_value={
            "session_id": "psf_test", "rehabman_task_ref": "rehabman-self-test", "status": "submitted",
            "questionnaire_version_ref": {"form_id": 4, "family_id": 4, "version": 1, "definition_sha256": "a" * 64}}))
        task = await self.db[models.COLLECTION_NAME].find_one({"_id": self.task_id})
        updated = await patient_self.refresh_remote_status(self.db, remote, task)
        self.assertEqual(updated["patient_self"]["status"], "submitted")
        self.assertIsNotNone(updated["patient_self"]["submitted_at"])

    async def _seed_followup_for_confirmation(self):
        record = FollowUpRecord(patient_id=self.patient_id, created_by=self.doctor_id,
            scheduled_date=datetime.utcnow() + timedelta(days=1), follow_up_type="phone", status="awaiting_fill")
        record.visit_code = "visit-self-1"
        record.mutation_version = 4
        await self.db.followup_records.insert_one(record.to_mongo())
        followup_id = ObjectId(record._id)
        await self.db.followup_records.update_one({"_id": followup_id},
            {"$set": {"fill_task_ids": [self.task_id]}})
        await self.db[models.COLLECTION_NAME].update_one({"_id": self.task_id},
            {"$set": {"followup_visit_id": str(followup_id), "visit_code": record.visit_code}})
        return followup_id

    def _source_response_snapshot(self, *, response_id=42, voided=False, answer_text=None, visit_code=None):
        version = {key: self.version_ref()[key] for key in
                   ("form_id", "family_id", "version", "definition_sha256")}
        refs = {"project_id": 1, "center_id": 2, "subject_id": 3, "questionnaire_id": 4}
        return {
            "session": {"session_uuid": "psf_test", "rehabman_task_ref": "rehabman-self-test",
                "status": "submitted", "patient_id": 8, **refs,
                "questionnaire_version_ref": version, "response_id": response_id},
            "response": {"response_id": response_id, "status": "submitted", "is_voided": voided,
                "user_id": None, "patient_id": 8, **refs, "form": version,
                "submitted_at": "2026-11-17T10:00:00Z", "updated_at": "2026-11-17T10:02:00Z",
                "visit_code": visit_code, "answers": [{"question_id": 101, "answer_text": answer_text}]},
        }

    async def test_self_fill_confirmation_links_source_snapshot_without_patient_session(self):
        followup_id = await self._seed_followup_for_confirmation()
        # First clinician verification is independent of the original Mini or browser session.
        await self.db.oidc_mini_sessions.delete_many({})
        await self.db.oidc_application_sessions.delete_many({})
        source = SimpleNamespace(get_patient_self_fill_response=AsyncMock(
            return_value=self._source_response_snapshot()))
        operator = SimpleNamespace(id=self.doctor_id, role="doctor")

        confirmed = await patient_self.confirm_task(self.db, source, str(self.task_id), operator)

        self.assertEqual(confirmed["status"], "confirmed")
        self.assertEqual(confirmed["patient_self"]["status"], "submitted")
        self.assertEqual(confirmed["patient_self"]["source_status"], "submitted")
        self.assertEqual(confirmed["patient_self"]["source_response_id"], 42)
        self.assertEqual(confirmed["confirmation"]["fill_mode"], "patient_self")
        self.assertEqual(confirmed["confirmation"]["remote_status"], "submitted")
        self.assertNotIn("revision", confirmed["confirmation"])
        self.assertIsNone(confirmed["confirmation"]["user_id"])
        self.assertEqual(confirmed["confirmation"]["verified_by"], self.doctor_id)
        self.assertEqual(confirmed["confirmation"]["answers"], [{"question_id": 101, "answer_text": None}])

        node = await self.db.followup_records.find_one({"_id": followup_id})
        self.assertEqual(node["status"], "in_review")
        self.assertEqual(node["effective_response"]["task_id"], str(self.task_id))
        self.assertEqual(node["effective_response"]["response_id"], 42)
        self.assertEqual(node["current_evidence"]["source"], "external_form")
        history = node["submission_history"][-1]
        self.assertEqual(history["submitted_by"], self.patient_id)
        self.assertEqual(history["submitted_at"], datetime(2026, 11, 17, 10, 0))
        self.assertEqual(history["confirmation"]["verified_by"], self.doctor_id)
        self.assertNotIn("answers", history["confirmation"])
        self.assertEqual(history["snapshot"]["answers"], [])

        patient_view = patient_self.serialize_patient_task(confirmed)
        staff_summary = patient_self.serialize_patient_task(confirmed, include_staff=True)
        staff_detail = patient_self.serialize_patient_task(confirmed, include_staff=True, include_evidence=True)
        self.assertEqual(patient_view["status"], "confirmed")
        self.assertNotIn("verifiedEvidence", patient_view)
        self.assertNotIn("verifiedEvidence", staff_summary)
        self.assertEqual(staff_detail["verifiedEvidence"]["fill_mode"], "patient_self")
        self.assertEqual(staff_detail["verifiedEvidence"]["answers"][0]["answer_text"], None)
        patient_list = await patient_self.list_tasks(
            self.db, SimpleNamespace(id=self.patient_id, role="patient"))
        staff_list = await patient_self.list_tasks(
            self.db, SimpleNamespace(id=self.doctor_id, role="doctor"))
        self.assertNotIn("verifiedEvidence", patient_list["items"][0])
        self.assertNotIn("answers", patient_list["items"][0])
        self.assertNotIn("verifiedEvidence", staff_list["items"][0])
        self.assertNotIn("answers", staff_list["items"][0])
        self.assertEqual(source.get_patient_self_fill_response.await_args.args[0], "psf_test")

        followups = FollowupService(self.db)
        reviewed = await followups.review_followup(followup_id,
            ReviewFollowUpRequest(expected_version=node["mutation_version"], decision="approved"),
            reviewer_id=self.doctor_id)
        self.assertEqual(reviewed.status, "completed")
        self.assertEqual(reviewed.review["history"][-1]["verified_confirmation"]["fill_mode"], "patient_self")

        # Retrying the same confirmation is idempotent and does not append a second visit submission.
        retried = await patient_self.confirm_task(self.db, source, str(self.task_id), operator)
        self.assertEqual(retried["confirmation"]["snapshot_sha256"], confirmed["confirmation"]["snapshot_sha256"])
        node = await self.db.followup_records.find_one({"_id": followup_id})
        self.assertEqual(len(node["submission_history"]), 1)

    async def test_self_fill_followup_and_task_confirmation_roll_back_together(self):
        followup_id = await self._seed_followup_for_confirmation()
        operator = SimpleNamespace(id=self.doctor_id, role="doctor")
        source = SimpleNamespace(get_patient_self_fill_response=AsyncMock(
            return_value=self._source_response_snapshot()))
        task_collection = self.db[models.COLLECTION_NAME]
        original_update_one = AsyncIOMotorCollection.update_one

        async def fail_task_cas(collection, query, update, *args, **kwargs):
            if collection.name == models.COLLECTION_NAME and "patient_self.source_session_id" in query:
                return SimpleNamespace(matched_count=0)
            return await original_update_one(collection, query, update, *args, **kwargs)

        with patch.object(AsyncIOMotorCollection, "update_one", autospec=True, side_effect=fail_task_cas):
            with self.assertRaises(patient_self.FormIntegrationError) as raised:
                await patient_self.confirm_task(self.db, source, str(self.task_id), operator)
        self.assertEqual(raised.exception.error_code, "SELF_FILL_TASK_CHANGED")
        node = await self.db.followup_records.find_one({"_id": followup_id})
        task = await task_collection.find_one({"_id": self.task_id})
        self.assertEqual(node["status"], "awaiting_fill")
        self.assertNotIn("effective_response", node)
        self.assertEqual(node.get("submission_history", []), [])
        self.assertNotEqual(task["status"], "confirmed")

    async def test_self_fill_confirmation_rejects_mismatched_or_voided_source_evidence(self):
        followup_id = await self._seed_followup_for_confirmation()
        operator = SimpleNamespace(id=self.doctor_id, role="doctor")
        mismatched_response = self._source_response_snapshot()
        mismatched_response["session"]["response_id"] = 43
        wrong_version = self._source_response_snapshot()
        wrong_version["session"]["questionnaire_id"] = 99
        for snapshot in (mismatched_response,
                         self._source_response_snapshot(voided=True),
                         wrong_version):
            source = SimpleNamespace(get_patient_self_fill_response=AsyncMock(return_value=snapshot))
            with self.assertRaises(patient_self.FormIntegrationError):
                await patient_self.confirm_task(self.db, source, str(self.task_id), operator)
        node = await self.db.followup_records.find_one({"_id": followup_id})
        task = await self.db[models.COLLECTION_NAME].find_one({"_id": self.task_id})
        self.assertEqual(node["status"], "awaiting_fill")
        self.assertNotIn("effective_response", node)
        self.assertNotEqual(task["status"], "confirmed")

    async def test_patient_self_task_is_invisible_to_legacy_clinician_task_reads(self):
        operator = SimpleNamespace(id=self.task["operator"]["user_id"], role="doctor")
        page = await service.list_fill_tasks(self.db, operator)
        self.assertEqual(page["items"], [])
        with self.assertRaises(service.FormIntegrationError) as raised:
            await service.get_fill_task(self.db, str(self.task_id), operator)
        self.assertEqual(raised.exception.status_code, 404)

    async def _seed_assigned_task(self):
        task = await self.db[models.COLLECTION_NAME].find_one({"_id": self.task_id})
        task["patient_self"].update(status="assigned", source_session_id=None, source_status=None,
                                     patient_actor_id=None, patient_actor_subject=None, patient_issuer=None,
                                     patient_binding_revision=None, mini_session_id=None, source_session_hash=None)
        task["mutation_version"] = 0
        await self.db[models.COLLECTION_NAME].replace_one({"_id": self.task_id}, task)

    async def _switch_to_canonical_patient(self):
        canonical_id = str(ObjectId())
        now = datetime.utcnow()
        await self.db.patient_domain_state.insert_one({"_id": "clinical-patients-v1", "mode": "canonical",
                                                        "schema_version": 1})
        await self.db.clinical_patients.insert_one({"_id": ObjectId(), "patient_id": canonical_id,
            "status": "active", "schema_version": 1, "practitioners": [self.doctor_id]})
        await self.db.patient_account_links.insert_one({"_id": f"explicit:{canonical_id}",
            "account_id": self.patient_id, "account_document_id": self.actor_id,
            "patient_id": canonical_id, "source": "explicit_binding", "schema_version": 1,
            "status": "verified", "bound_at": now,
            "audit": [{"operation": "explicit_binding", "reviewer": "reviewer",
                       "evidence_reference": "review/patient-binding", "at": now}]})
        await self.db.external_patient_links.update_one({"_id": self.link["_id"]},
            {"$set": {"local_patient_id": canonical_id}})
        await self.db[models.COLLECTION_NAME].update_one({"_id": self.task_id},
            {"$set": {"patient_id": canonical_id}})
        self.task["patient_id"] = canonical_id
        return canonical_id

    def _mini_oidc(self):
        mini = {"_id": self.mini_id, "source_session_id": self.session_hash,
                "actor_id": self.patient_id, "expires_at": datetime.utcnow() + timedelta(hours=1)}
        actor = {"_id": self.actor_id, "role": "patient", "is_active": True}
        return SimpleNamespace(settings=SimpleNamespace(issuer=self.issuer),
            actor_for_mini_session=AsyncMock(return_value=(mini, actor)),
            actor_for_session_hash=AsyncMock(return_value=(self.source_record, actor)))

    def _launch_client(self):
        created = []
        resumed = []
        revoked = []
        version_ref = {key: self.version_ref()[key] for key in ("form_id", "family_id", "version", "definition_sha256")}
        response = {"session_id": "psf_retry", "status": "created", "launch_url": "https://form.example/self-fill/psf_retry",
            "launch_token": "create-token-ignored", "expires_at": (datetime.utcnow() + timedelta(minutes=5)).isoformat() + "Z",
            "questionnaire_version_ref": version_ref}
        class Source:
            source_origin = "https://form.example"
            async def create_patient_self_fill_session(inner, payload, *, idempotency_key):
                created.append((payload, idempotency_key))
                return response
            async def resume_patient_self_fill_session(inner, session_id, payload, *, idempotency_key):
                resumed.append((session_id, payload, idempotency_key))
                return {"session_id": session_id, "status": "created", "launch_url": "https://form.example/self-fill/psf_retry",
                    "launch_token": f"resume-token-{len(resumed)}", "expires_at": (datetime.utcnow() + timedelta(minutes=5)).isoformat() + "Z",
                    "questionnaire_version_ref": version_ref}
            async def revoke_patient_self_fill_session(inner, session_id, payload):
                revoked.append((session_id, payload))
                return {"session_id": session_id, "status": "revoked"}
        return Source(), created, resumed, revoked

    async def test_create_success_local_commit_failure_retries_with_same_remote_idempotency_key(self):
        await self._seed_assigned_task()
        oidc = self._mini_oidc()
        source, created, resumed, revoked = self._launch_client()
        actor = SimpleNamespace(id=self.patient_id, role="patient")
        with patch("app.integrations.identity.config.oidc_settings.public_base_url", "https://rehab.example"), \
             patch.object(patient_self, "run_followup_transaction", side_effect=RuntimeError("synthetic local commit failure")):
            with self.assertRaises(RuntimeError):
                await patient_self.launch_task(self.db, source, str(self.task_id), actor,
                    mini_token="patient-mini-token", oidc_client=oidc, settings_obj=self.config)
        self.assertEqual(len(revoked), 0)
        self.assertEqual(len(resumed), 0)
        self.assertEqual(await self.db[patient_self.BRIDGE_COLLECTION].count_documents({}), 0)
        stored = await self.db[models.COLLECTION_NAME].find_one({"_id": self.task_id})
        self.assertEqual(stored["patient_self"]["status"], "assigned")
        with patch("app.integrations.identity.config.oidc_settings.public_base_url", "https://rehab.example"):
            launched = await patient_self.launch_task(self.db, source, str(self.task_id), actor,
                mini_token="patient-mini-token", oidc_client=oidc, settings_obj=self.config)
        self.assertEqual(created[0][1], created[1][1])
        self.assertEqual(len(resumed), 1)
        self.assertEqual(resumed[0][1], {"rehabman_task_ref": "rehabman-self-test",
            "patient_actor_subject": self.subject,
            "questionnaire_version_ref": {"form_id": 4, "family_id": 4, "version": 1, "definition_sha256": "a" * 64},
            "allowed_origin": "https://rehab.example"})
        self.assertEqual(launched["sessionId"], "psf_retry")
        self.assertNotIn("resume-token", str(launched))
        self.assertNotIn("create-token-ignored", str(launched))
        stored = await self.db[models.COLLECTION_NAME].find_one({"_id": self.task_id})
        self.assertNotIn("resume-token", str(stored))
        self.assertNotIn("create-token-ignored", str(stored))
        self.assertEqual(stored["patient_self"]["status"], "active")

    async def test_reopen_draft_rotates_one_time_token_without_creating_new_remote_draft(self):
        await self._seed_assigned_task()
        oidc = self._mini_oidc()
        source, created, resumed, _revoked = self._launch_client()
        actor = SimpleNamespace(id=self.patient_id, role="patient")
        with patch("app.integrations.identity.config.oidc_settings.public_base_url", "https://rehab.example"):
            first = await patient_self.launch_task(self.db, source, str(self.task_id), actor,
                mini_token="patient-mini-token", oidc_client=oidc, settings_obj=self.config)
            first_bridge = first["webviewUrl"].rsplit("/", 1)[-1]
            second = await patient_self.launch_task(self.db, source, str(self.task_id), actor,
                mini_token="patient-mini-token", oidc_client=oidc, settings_obj=self.config)
        self.assertEqual(len(created), 1)
        self.assertEqual(len(resumed), 2)
        self.assertNotEqual(resumed[0][2], resumed[1][2])
        self.assertEqual(first["sessionId"], second["sessionId"])
        self.assertNotEqual(first["webviewUrl"], second["webviewUrl"])
        self.assertIsNone(await self.db[patient_self.BRIDGE_COLLECTION].find_one({"_id": digest(first_bridge)}))

    async def test_browser_session_opens_its_bridge_once_without_a_mini_session(self):
        await self._seed_assigned_task()
        await self.db.oidc_mini_sessions.delete_one({"_id": self.mini_id})
        actor = SimpleNamespace(id=self.patient_id, role="patient")
        oidc = SimpleNamespace(settings=SimpleNamespace(issuer=self.issuer),
            actor_for_session=AsyncMock(return_value=(self.source_record,
                {"_id": self.actor_id, "role": "patient", "is_active": True})))
        source, created, resumed, _revoked = self._launch_client()
        with patch("app.integrations.identity.config.oidc_settings.public_base_url", "https://rehab.example"):
            launched = await patient_self.launch_task(self.db, source, str(self.task_id), actor,
                browser_sid=self.session_cookie, oidc_client=oidc, settings_obj=self.config)
        self.assertEqual(len(created), 1)
        self.assertEqual(len(resumed), 1)
        self.assertNotIn("resume-token-1", str(launched))
        ticket = launched["webviewUrl"].rsplit("/", 1)[-1]
        bridge = await self.db[patient_self.BRIDGE_COLLECTION].find_one({"_id": digest(ticket)})
        self.assertEqual(bridge["identity_transport"], "browser")
        self.assertIsNone(bridge["mini_session_id"])
        wrong = await patient_self.consume_launch_bridge(self.db, ticket, "another-cookie", oidc, self.config)
        self.assertEqual(wrong.status_code, 403)
        accepted = await patient_self.consume_launch_bridge(self.db, ticket, self.session_cookie, oidc, self.config)
        self.assertEqual(accepted.status_code, 200)
        self.assertIn(b'method="post" action="https://form.example/self-fill/psf_retry"', accepted.body)
        self.assertIn(b'name="token" value="resume-token-1"', accepted.body)
        self.assertIn("no-store", accepted.headers["cache-control"])
        replayed = await patient_self.consume_launch_bridge(self.db, ticket, self.session_cookie, oidc, self.config)
        self.assertEqual(replayed.status_code, 410)

    async def test_revoke_wins_during_remote_launch_and_compensates_source_session(self):
        await self._seed_assigned_task()
        oidc = self._mini_oidc()
        source, created, resumed, revoked = self._launch_client()
        actor = SimpleNamespace(id=self.patient_id, role="patient")
        operator = SimpleNamespace(id=self.doctor_id, role="doctor")
        original = source.create_patient_self_fill_session
        async def create_then_revoke(payload, *, idempotency_key):
            result = await original(payload, idempotency_key=idempotency_key)
            await patient_self.revoke_task(self.db, source, str(self.task_id), operator, reason="患者已取消")
            return result
        source.create_patient_self_fill_session = create_then_revoke
        with patch("app.integrations.identity.config.oidc_settings.public_base_url", "https://rehab.example"):
            with self.assertRaises(patient_self.FormIntegrationError):
                await patient_self.launch_task(self.db, source, str(self.task_id), actor,
                    mini_token="patient-mini-token", oidc_client=oidc, settings_obj=self.config)
        self.assertEqual(len(created), 1)
        self.assertEqual(len(resumed), 0)
        self.assertEqual(len(revoked), 1)
        stored = await self.db[models.COLLECTION_NAME].find_one({"_id": self.task_id})
        self.assertEqual(stored["patient_self"]["status"], "revoked")
        self.assertEqual(await self.db[patient_self.BRIDGE_COLLECTION].count_documents({}), 0)

    async def test_revoke_and_source_callback_race_fails_closed_after_revocation(self):
        actor = {"_id": self.actor_id, "role": "patient", "is_active": True}
        oidc = SimpleNamespace(actor_for_session_hash=AsyncMock(return_value=(self.source_record, actor)))
        source = SimpleNamespace(revoke_patient_self_fill_session=AsyncMock(return_value={"status": "revoked"}))
        payload = {"rehabman_task_ref": "rehabman-self-test", "patient_actor_subject": self.subject,
                   "source_session_id": "psf_test", "action": "save", "pinned_version_sha256": "a" * 64}
        with patch.object(patient_self.settings, "REHAB_SELF_FILL_CALLBACK_SECRET", SecretStr("independent-secret")), \
             patch("app.integrations.identity.service.OidcClient", return_value=oidc):
            results = await asyncio.gather(
                patient_self.callback_authorize(self.db, payload, "independent-secret"),
                patient_self.revoke_task(self.db, source, str(self.task_id),
                    SimpleNamespace(id=self.doctor_id, role="doctor"), reason="撤销"),
                return_exceptions=True)
            self.assertTrue(any(not isinstance(item, Exception) for item in results))
            with self.assertRaises(patient_self.FormIntegrationError) as raised:
                await patient_self.callback_authorize(self.db, payload, "independent-secret")
        self.assertEqual(raised.exception.status_code, 403)
        stored = await self.db[models.COLLECTION_NAME].find_one({"_id": self.task_id})
        self.assertEqual(stored["patient_self"]["status"], "revoked")
