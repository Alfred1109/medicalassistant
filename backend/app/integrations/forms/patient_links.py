"""Explicitly reviewed links between local patients and authorized source patients.

An account identity and a clinical patient are different things. This module
never creates a user or infers a match from names or email addresses.
"""
import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import urlsplit

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

from app.db.mongodb import get_database
from .client import FormPlatformError
from .catalog_router import get_catalog_client, require_catalog_admin

def _private_response(response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


router = APIRouter(prefix="/integrations/forms/patient-links", tags=["form-patient-links"],
                   dependencies=[Depends(_private_response)])


class PatientLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    local_patient_id: str = Field(min_length=24, max_length=24)
    project_id: StrictInt = Field(gt=0, le=9223372036854775807)
    center_id: StrictInt = Field(gt=0, le=9223372036854775807)
    subject_id: StrictInt = Field(gt=0, le=9223372036854775807)
    evidence_reference: str = Field(min_length=1, max_length=256)
    identity_verified: StrictBool

    @field_validator("identity_verified")
    @classmethod
    def require_identity_review(cls, value):
        if value is not True:
            raise ValueError("identity must be explicitly verified")
        return value


class RevokePatientLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=1, max_length=256)


class AddPatientContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_id: StrictInt = Field(gt=0, le=9223372036854775807)
    center_id: StrictInt = Field(gt=0, le=9223372036854775807)
    subject_id: StrictInt = Field(gt=0, le=9223372036854775807)
    evidence_reference: str = Field(min_length=1, max_length=256)
    identity_verified: StrictBool

    @field_validator("identity_verified")
    @classmethod
    def require_identity_review(cls, value):
        if value is not True:
            raise ValueError("identity must be explicitly verified")
        return value


def _reference(value, project_id, center_id, subject_id):
    if not isinstance(value, dict) or not isinstance(value.get("source"), dict):
        raise HTTPException(502, detail={"code": "INVALID_SOURCE_REFERENCE"})
    source = value["source"]
    system, environment = source.get("system"), source.get("environment")
    if system != "form-platform-11344" or environment not in {"pilot", "production"}:
        raise HTTPException(502, detail={"code": "INVALID_SOURCE_REFERENCE"})
    for key, expected in (("project_id", project_id), ("center_id", center_id), ("subject_id", subject_id)):
        if type(value.get(key)) is not int or value[key] != expected:
            raise HTTPException(502, detail={"code": "INVALID_SOURCE_REFERENCE"})
    for key in ("patient_id", "patient_archive_id"):
        if type(value.get(key)) is not int or value[key] <= 0:
            raise HTTPException(502, detail={"code": "INVALID_SOURCE_REFERENCE"})
    return {"source": {"system": system, "environment": environment},
            **{key: value[key] for key in ("project_id", "center_id", "subject_id", "patient_id", "patient_archive_id")}}


def _link_key(reference, origin):
    source = reference["source"]
    raw = json.dumps([origin, source["system"], source["environment"], reference["patient_id"]],
                     ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


async def bind_reviewed_patient(db, client, actor, payload: PatientLinkRequest):
    if not ObjectId.is_valid(payload.local_patient_id):
        raise HTTPException(422, detail={"code": "INVALID_PATIENT_ID"})
    local_patient_id = str(ObjectId(payload.local_patient_id))
    patient = await db.users.find_one({"_id": ObjectId(local_patient_id),
                                       "role": "patient", "is_active": True}, {"_id": 1})
    if not patient:
        raise HTTPException(404, detail={"code": "ACTIVE_PATIENT_NOT_FOUND"})
    try:
        remote = await client.get_patient_reference(payload.project_id, payload.center_id, payload.subject_id)
    except FormPlatformError:
        raise HTTPException(502, detail={"code": "SOURCE_REFERENCE_UNAVAILABLE"}) from None
    reference = _reference(remote, payload.project_id, payload.center_id, payload.subject_id)
    try:
        origin = client.source_origin
        parsed = urlsplit(origin)
        if (not parsed.hostname or parsed.username or parsed.password or parsed.path
                or parsed.query or parsed.fragment or parsed.scheme not in {"http", "https"}
                or (reference["source"]["environment"] == "production" and parsed.scheme != "https")):
            raise ValueError("untrusted source")
    except (AttributeError, ValueError):
        raise HTTPException(503, detail={"code": "INVALID_SOURCE_CONFIGURATION"}) from None
    links = db.external_patient_links
    # Database-enforced uniqueness is required before any write; no fallback on failure.
    index_options = {"unique": True, "partialFilterExpression": {"status": "verified"}}
    await links.create_index([("local_patient_id", ASCENDING)], name="unique_verified_local_patient", **index_options)
    await links.create_index([("source_key", ASCENDING)], name="unique_verified_source_patient", **index_options)
    key = _link_key(reference, origin)
    existing = await links.find_one({"source_key": key, "status": "verified"})
    if existing or await links.find_one({"local_patient_id": local_patient_id, "status": "verified"}):
        raise HTTPException(409, detail={"code": "PATIENT_LINK_CONFLICT"})
    now = datetime.now(timezone.utc)
    link_id = ObjectId()
    entry = {"_id": link_id, "source_key": key, "source_origin": origin,
             "local_patient_id": local_patient_id,
             "reference": reference, "references": [reference], "status": "verified", "verified_by": str(actor.id),
             "verified_at": now, "evidence_reference": payload.evidence_reference,
             "audit": [{"action": "verify_link", "actor_id": str(actor.id), "at": now,
                        "evidence_reference": payload.evidence_reference}]}
    try:
        await links.insert_one(entry)
    except DuplicateKeyError:
        raise HTTPException(409, detail={"code": "PATIENT_LINK_CONFLICT"}) from None
    return {"id": str(link_id), "local_patient_id": local_patient_id, "reference": reference,
            "status": "verified", "verified_at": now}


@router.post("", status_code=201)
async def create_patient_link(payload: PatientLinkRequest, actor=Depends(require_catalog_admin),
                              db=Depends(get_database), client=Depends(get_catalog_client)):
    return await bind_reviewed_patient(db, client, actor, payload)


@router.get("")
async def list_patient_links(skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
                             actor=Depends(require_catalog_admin), db=Depends(get_database)):
    cursor = db.external_patient_links.find({}).sort([("verified_at", -1), ("_id", -1)]).skip(skip).limit(limit)
    result = []
    async for row in cursor:
        result.append({"id": str(row["_id"]), "local_patient_id": row["local_patient_id"],
                       "reference": row["reference"], "references": row.get("references", [row["reference"]]),
                       "status": row["status"],
                       "verified_at": row["verified_at"]})
    return {"items": result, "skip": skip, "limit": limit,
            "total": await db.external_patient_links.count_documents({})}


@router.post("/{link_id}/contexts")
async def add_patient_context(link_id: str, payload: AddPatientContextRequest,
                              actor=Depends(require_catalog_admin), db=Depends(get_database),
                              client=Depends(get_catalog_client)):
    if not ObjectId.is_valid(link_id):
        raise HTTPException(422, detail={"code": "INVALID_LINK_ID"})
    row = await db.external_patient_links.find_one({"_id": ObjectId(link_id), "status": "verified"})
    if not row:
        raise HTTPException(404, detail={"code": "PATIENT_LINK_NOT_ACTIVE"})
    try:
        remote = await client.get_patient_reference(payload.project_id, payload.center_id, payload.subject_id)
    except FormPlatformError:
        raise HTTPException(502, detail={"code": "SOURCE_REFERENCE_UNAVAILABLE"}) from None
    reference = _reference(remote, payload.project_id, payload.center_id, payload.subject_id)
    try:
        origin = client.source_origin
    except (AttributeError, ValueError):
        raise HTTPException(503, detail={"code": "INVALID_SOURCE_CONFIGURATION"}) from None
    if origin != row.get("source_origin") or _link_key(reference, origin) != row.get("source_key"):
        raise HTTPException(409, detail={"code": "SOURCE_PATIENT_MISMATCH"})
    now = datetime.now(timezone.utc)
    # Atomic same-document update prevents duplicate contexts and preserves the
    # previous context and audit when a patient participates in another project.
    result = await db.external_patient_links.update_one(
        {"_id": row["_id"], "status": "verified", "references": {"$not": {"$elemMatch": {
            "project_id": reference["project_id"], "center_id": reference["center_id"],
            "subject_id": reference["subject_id"]}}}},
        {"$push": {"references": reference,
                   "audit": {"action": "add_context", "actor_id": str(actor.id), "at": now,
                             "evidence_reference": payload.evidence_reference,
                             "project_id": reference["project_id"], "center_id": reference["center_id"],
                             "subject_id": reference["subject_id"]}}})
    if result.modified_count != 1:
        raise HTTPException(409, detail={"code": "PATIENT_CONTEXT_CONFLICT"})
    return {"id": link_id, "reference": reference, "status": "verified"}


@router.post("/{link_id}/revoke")
async def revoke_patient_link(link_id: str, payload: RevokePatientLinkRequest,
                              actor=Depends(require_catalog_admin), db=Depends(get_database)):
    if not ObjectId.is_valid(link_id):
        raise HTTPException(422, detail={"code": "INVALID_LINK_ID"})
    now = datetime.now(timezone.utc)
    result = await db.external_patient_links.update_one(
        {"_id": ObjectId(link_id), "status": "verified"},
        {"$set": {"status": "revoked", "revoked_at": now},
         "$push": {"audit": {"action": "revoke_link", "actor_id": str(actor.id),
                              "at": now, "reason": payload.reason}}})
    if result.modified_count != 1:
        raise HTTPException(409, detail={"code": "PATIENT_LINK_NOT_ACTIVE"})
    return {"id": link_id, "status": "revoked", "revoked_at": now}
