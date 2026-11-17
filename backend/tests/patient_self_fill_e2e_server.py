"""Loopback-only disposable Rehabman endpoint for the two-service self-fill test.

Run with the isolated replica set and a test callback secret. This module must
never be mounted by the production application.
"""
import os
from datetime import datetime, timedelta

from bson import ObjectId
from cryptography.fernet import Fernet
from fastapi import FastAPI, Header, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import SecretStr

from app.core.config import settings
from app.db.mongodb import get_database
from app.integrations.forms import models, patient_self
from app.integrations.forms.client import FormPlatformClient
from app.integrations.forms.router import router as forms_router
from app.core.auth import get_current_active_user
from app.integrations.identity.config import oidc_settings
from app.integrations.identity.service import OidcClient, digest, ensure_identity_indexes
from app.models.health_record import FollowUpRecord
from app.schemas.followup import ReviewFollowUpRequest
from app.services.followup_service import FollowupService


MONGO_URI = os.environ.get("REHAB_TEST_SELF_FILL_MONGO_URI", "")
DB_NAME = os.environ.get("REHAB_SELF_FILL_E2E_DB", "rehab_patient_self_http_e2e")
E2E_SECRET = os.environ.get("REHAB_SELF_FILL_E2E_SECRET", "")
CALLBACK_SECRET = os.environ.get("REHAB_SELF_FILL_CALLBACK_SECRET", "")
ISSUER = os.environ.get("OIDC_ISSUER", "https://identity.test")
PATIENT_ID = "66b1f2a942a95a5210d4c101"
DOCTOR_ID = "66b1f2a942a95a5210d4c102"
SUBJECT = "opaque-oneid-subject-001"
BROWSER_COOKIE = os.environ.get("REHAB_SELF_FILL_E2E_BROWSER_COOKIE", "e2e-browser-cookie")
MINI_TOKEN = os.environ.get("REHAB_SELF_FILL_E2E_MINI_TOKEN", "e2e-mini-token")
BINDING_REVISION = "e2e-reviewed-binding-revision"

if (not MONGO_URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:"))
        or not E2E_SECRET or not CALLBACK_SECRET):
    raise RuntimeError("loopback Mongo and explicit E2E/callback secrets are required")

mongo = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=4000)
db = mongo[DB_NAME]
app = FastAPI(title="Rehabman self-fill E2E fixture")
app.include_router(forms_router, prefix="/api")
app.dependency_overrides[get_database] = lambda: db
settings.REHAB_SELF_FILL_CALLBACK_SECRET = SecretStr(CALLBACK_SECRET)
oidc_settings.public_base_url = os.environ.get("REHAB_SELF_FILL_E2E_PUBLIC_BASE_URL", "http://127.0.0.1:18777")
oidc_settings.session_encryption_key = SecretStr(Fernet.generate_key().decode("ascii"))


@app.on_event("startup")
async def startup():
    hello = await db.command("hello")
    if not hello.get("setName"):
        raise RuntimeError("self-fill E2E requires a disposable Mongo replica set")
    await db.drop_collection(models.COLLECTION_NAME)
    await db.drop_collection(patient_self.BRIDGE_COLLECTION)
    for name in ("users", "oidc_principal_bindings", "oidc_application_sessions",
                 "oidc_mini_sessions", "external_patient_links", "external_form_bindings",
                 "patient_domain_state", "clinical_patients", "patient_account_links"):
        await db.drop_collection(name)
    await ensure_identity_indexes(db)


async def _e2e_doctor():
    return type("DoctorActor", (), {"id": DOCTOR_ID, "role": "doctor"})()


app.dependency_overrides[get_current_active_user] = _e2e_doctor


async def _authorize_oidc_session(session_hash):
    source = await db.oidc_application_sessions.find_one({
        "_id": session_hash, "issuer": ISSUER, "expires_at": {"$gt": datetime.utcnow()}})
    if not source:
        return None, None
    binding = await db.oidc_principal_bindings.find_one({
        "issuer": ISSUER, "subject": source.get("subject"), "enabled": True,
        "approved_role": "patient", "authorization_revision": source.get("binding_revision")})
    if not binding:
        return None, None
    actor = await db.users.find_one({"_id": ObjectId(PATIENT_ID), "role": "patient", "is_active": True})
    return (source, actor) if actor else (None, None)


async def _fixture_actor_for_session_hash(self, session_hash):
    return await _authorize_oidc_session(session_hash)


async def _fixture_actor_for_session(self, sid):
    return await _authorize_oidc_session(digest(sid) if sid else None)


async def _fixture_actor_for_mini_session(self, token):
    mini = await db.oidc_mini_sessions.find_one({"_id": digest(token),
        "actor_id": PATIENT_ID, "expires_at": {"$gt": datetime.utcnow()}}) if token else None
    if not mini:
        return None, None
    actor = await db.users.find_one({"_id": ObjectId(PATIENT_ID), "role": "patient", "is_active": True})
    return (mini, actor) if actor else (None, None)


# The external OneID issuer is deliberately stubbed only inside this disposable
# test app. The real source platform and Rehabman callback still use loopback HTTP.
OidcClient.actor_for_session_hash = _fixture_actor_for_session_hash
OidcClient.actor_for_session = _fixture_actor_for_session
OidcClient.actor_for_mini_session = _fixture_actor_for_mini_session


def _guard(secret):
    if secret != E2E_SECRET:
        raise HTTPException(status_code=404)


@app.post("/__test/seed")
async def seed_task(payload: dict, x_e2e_secret: str = Header(default="")):
    _guard(x_e2e_secret)
    expected = {"rehabman_task_ref", "patient_actor_subject", "source_origin", "allowed_origin",
                "remote_refs", "questionnaire_version_ref", "reference"}
    if set(payload) != expected:
        raise HTTPException(422, "invalid seed payload")
    refs, version, reference = payload["remote_refs"], payload["questionnaire_version_ref"], payload["reference"]
    if (not isinstance(refs, dict) or not isinstance(version, dict) or not isinstance(reference, dict)
            or any(type(refs.get(k)) is not int or refs[k] <= 0 for k in
                   ("project_id", "center_id", "subject_id", "questionnaire_id"))
            or any(type(version.get(k)) is not int or version[k] <= 0 for k in ("form_id", "family_id", "version"))
            or not isinstance(version.get("definition_sha256"), str)
            or not isinstance(payload["source_origin"], str) or not payload["source_origin"].startswith("https://")):
        raise HTTPException(422, "invalid reviewed reference")
    now = datetime.utcnow()
    await db.users.update_one({"_id": ObjectId(PATIENT_ID)}, {"$set": {
        "role": "patient", "is_active": True, "practitioners": [DOCTOR_ID]}}, upsert=True)
    await db.users.update_one({"_id": ObjectId(DOCTOR_ID)}, {"$set": {
        "role": "doctor", "is_active": True}}, upsert=True)
    await db.oidc_principal_bindings.update_one({"_id": digest(ISSUER + "\0" + SUBJECT)}, {"$set": {
        "issuer": ISSUER, "subject": SUBJECT,
        "actor_id": PATIENT_ID, "enabled": True, "approved_role": "patient",
        "authorization_revision": BINDING_REVISION, "verified_by": "e2e-fixture",
        "verified_at": now, "evidence_reference": "test-only/e2e"}}, upsert=True)
    session_hash = digest(BROWSER_COOKIE)
    await db.oidc_application_sessions.update_one({"_id": session_hash}, {"$set": {"issuer": ISSUER,
        "subject": SUBJECT, "binding_revision": BINDING_REVISION,
        "expires_at": now + timedelta(hours=1)}}, upsert=True)
    mini_id = digest(MINI_TOKEN)
    await db.oidc_mini_sessions.update_one({"_id": mini_id}, {"$set": {"source_session_id": session_hash,
        "actor_id": PATIENT_ID, "expires_at": now + timedelta(hours=1)}}, upsert=True)
    link_id, binding_id, task_id = ObjectId(), ObjectId(), ObjectId()
    followup = FollowUpRecord(patient_id=PATIENT_ID, created_by=DOCTOR_ID,
        scheduled_date=now + timedelta(days=1), follow_up_type="phone", status="awaiting_fill")
    followup.visit_code = "visit-self-fill-e2e"
    followup.mutation_version = 0
    followup_id = ObjectId(followup._id)
    await db.followup_records.insert_one(followup.to_mongo())
    await db.external_patient_links.insert_one({"_id": link_id, "local_patient_id": PATIENT_ID,
        "status": "verified", "source_origin": payload["source_origin"], "reference": reference,
        "references": [reference], "verified_by": "e2e-fixture", "verified_at": now,
        "evidence_reference": "test-only/e2e"})
    await db.external_form_bindings.insert_one({"_id": binding_id, "status": "active",
        "source_origin": payload["source_origin"], "source": reference.get("source"),
        "project_id": refs["project_id"], "form_id": refs["questionnaire_id"],
        "version": version["version"], "purpose": "followup", "version_ref": version,
        "verified_by": "e2e-fixture", "verified_at": now, "evidence_reference": "test-only/e2e"})
    task = {
        "_id": task_id, "task_type": patient_self.TASK_TYPE, "patient_id": PATIENT_ID,
        "operator": {"user_id": DOCTOR_ID, "role": "doctor"}, "remote_refs": refs,
        "allowed_origin": payload["allowed_origin"], "status": "session_created", "mutation_version": 0,
        "created_at": now, "session": {"session_uuid": None},
        "followup_visit_id": str(followup_id), "visit_code": followup.visit_code,
        "reviewed_context": {"patient_link_id": str(link_id), "form_binding_id": str(binding_id),
            "reference": reference, "version_ref": version, "purpose": "followup"},
        "patient_self": {"status": "assigned", "rehabman_task_ref": payload["rehabman_task_ref"],
            "patient_actor_subject": payload["patient_actor_subject"], "patient_actor_id": PATIENT_ID,
            "patient_issuer": ISSUER, "patient_binding_revision": BINDING_REVISION,
            "mini_session_id": mini_id, "source_session_hash": session_hash,
            "pinned_version_sha256": version["definition_sha256"], "ttl_seconds": 1800},
    }
    await db[models.COLLECTION_NAME].insert_one(task)
    await db.followup_records.update_one({"_id": followup_id},
        {"$set": {"fill_task_ids": [task_id]}})
    return {"task_id": str(task_id), "patient_id": PATIENT_ID, "browser_cookie": BROWSER_COOKIE,
            "mini_token": MINI_TOKEN, "source_session_hash": session_hash,
            "followup_visit_id": str(followup_id)}


@app.post("/__test/launch/{task_id}")
async def launch_task(task_id: str, x_e2e_secret: str = Header(default="")):
    _guard(x_e2e_secret)
    client = FormPlatformClient.from_settings()
    actor = type("PatientActor", (), {"id": PATIENT_ID, "role": "patient"})()
    try:
        return await patient_self.launch_task(db, client, task_id, actor,
            mini_token=MINI_TOKEN, oidc_client=OidcClient(db, oidc_settings), settings_obj=oidc_settings)
    except patient_self.FormIntegrationError as exc:
        raise HTTPException(exc.status_code, detail={"error": exc.error_code, "message": exc.message}) from exc


@app.post("/__test/verify/{task_id}")
async def verify_task(task_id: str, x_e2e_secret: str = Header(default="")):
    _guard(x_e2e_secret)
    client = FormPlatformClient.from_settings()
    task = await patient_self._task_for_id(db, task_id)
    updated = await patient_self.refresh_remote_status(db, client, task)
    return patient_self.serialize_patient_task(updated, include_staff=True)


@app.post("/__test/confirm/{task_id}")
async def confirm_task(task_id: str, x_e2e_secret: str = Header(default="")):
    _guard(x_e2e_secret)
    client = FormPlatformClient.from_settings()
    try:
        task = await patient_self.confirm_task(db, client, task_id,
            type("DoctorActor", (), {"id": DOCTOR_ID, "role": "doctor"})())
        return patient_self.serialize_patient_task(task, include_staff=True, include_evidence=True)
    except patient_self.FormIntegrationError as exc:
        raise HTTPException(exc.status_code, detail={"error": exc.error_code, "message": exc.message,
            "details": exc.details}) from exc


@app.get("/__test/followup/{followup_id}")
async def get_followup(followup_id: str, x_e2e_secret: str = Header(default="")):
    _guard(x_e2e_secret)
    from bson import ObjectId
    record = await db.followup_records.find_one({"_id": ObjectId(followup_id)})
    if not record:
        raise HTTPException(404, "followup not found")
    return {"id": str(record["_id"]), "status": record.get("status"),
        "mutation_version": record.get("mutation_version", 0),
        "effective_response": record.get("effective_response"),
        "submission_history": record.get("submission_history", [])}


@app.post("/__test/followup/{followup_id}/review")
async def review_followup(followup_id: str, payload: dict,
                          x_e2e_secret: str = Header(default="")):
    _guard(x_e2e_secret)
    try:
        result = await FollowupService(db).review_followup(followup_id,
            ReviewFollowUpRequest(**payload), reviewer_id=DOCTOR_ID, reviewer_role="doctor")
        return {"id": str(result.id), "status": result.status, "mutation_version": result.mutation_version,
            "review": result.review}
    except Exception as exc:
        from app.core.exceptions import AppBaseException
        if isinstance(exc, AppBaseException):
            raise HTTPException(exc.status_code, detail={"error": exc.error_code,
                "message": str(exc)}) from exc
        raise


@app.post("/__test/revoke/{task_id}")
async def revoke_task(task_id: str, x_e2e_secret: str = Header(default="")):
    _guard(x_e2e_secret)
    client = FormPlatformClient.from_settings()
    actor = type("DoctorActor", (), {"id": DOCTOR_ID, "role": "doctor"})()
    try:
        return await patient_self.revoke_task(db, client, task_id, actor, reason="test-only E2E revoke")
    except patient_self.FormIntegrationError as exc:
        raise HTTPException(exc.status_code, detail={"error": exc.error_code, "message": exc.message}) from exc
