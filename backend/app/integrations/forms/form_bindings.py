"""Administrator-reviewed project questionnaire references, not fill sessions."""
import hashlib
import json
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

from app.db.mongodb import get_database
from .catalog_router import get_catalog_client, require_catalog_admin
from . import catalog_service

def _private_response(response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


router = APIRouter(prefix="/integrations/forms/form-bindings", tags=["form-bindings"],
                   dependencies=[Depends(_private_response)])


class FormBindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    project_id: StrictInt = Field(gt=0, le=9223372036854775807)
    form_id: StrictInt = Field(gt=0, le=9223372036854775807)
    version: StrictInt = Field(gt=0, le=9223372036854775807)
    purpose: Literal["initial_assessment", "followup", "reassessment"]
    evidence_reference: str = Field(min_length=1, max_length=256)
    confirmed: StrictBool

    @field_validator("confirmed")
    @classmethod
    def require_confirmation(cls, value):
        if value is not True:
            raise ValueError("form and purpose must be explicitly confirmed")
        return value


class RevokeFormBindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=1, max_length=256)


async def bind_form(db, client, actor, payload: FormBindingRequest):
    # The source returns only an authorized current, published definition here;
    # validate on every binding attempt, never trust a client-supplied hash.
    version = await catalog_service.form_version(client, payload.project_id, payload.form_id, version=payload.version)
    source = version["source"]
    try:
        origin = client.source_origin
        parsed = urlsplit(origin)
    except (AttributeError, ValueError):
        raise HTTPException(503, detail={"code": "INVALID_SOURCE_CONFIGURATION"}) from None
    if (not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment
            or parsed.scheme not in {"http", "https"} or
            (source["environment"] == "production" and parsed.scheme != "https")):
        raise HTTPException(503, detail={"code": "INVALID_SOURCE_CONFIGURATION"})
    ref = version["version"]
    if (version["form"]["project_id"] != payload.project_id or ref["form_id"] != payload.form_id
            or ref["version"] != payload.version or ref["version_state"] != "current"
            or not ref.get("definition_sha256")):
        raise HTTPException(409, detail={"code": "FORM_VERSION_NOT_CURRENT"})
    key_data = [origin, source["system"], source["environment"], payload.project_id,
                payload.form_id, payload.version, payload.purpose]
    key = hashlib.sha256(json.dumps(key_data, separators=(",", ":")).encode()).hexdigest()
    bindings = db.external_form_bindings
    await bindings.create_index([("binding_key", ASCENDING)], name="unique_active_form_binding", unique=True,
                                partialFilterExpression={"status": "active"})
    if await bindings.find_one({"binding_key": key, "status": "active"}):
        raise HTTPException(409, detail={"code": "FORM_BINDING_CONFLICT"})
    now = datetime.now(timezone.utc)
    doc = {"_id": ObjectId(), "binding_key": key, "source_origin": origin,
           "source": source, "project_id": payload.project_id, "form_id": payload.form_id,
           "version": payload.version, "version_ref": ref, "title": version["form"]["title"],
           "purpose": payload.purpose, "status": "active", "verified_by": str(actor.id),
           "verified_at": now, "evidence_reference": payload.evidence_reference,
           "audit": [{"action": "select_form", "actor_id": str(actor.id), "at": now,
                      "evidence_reference": payload.evidence_reference}]}
    try:
        await bindings.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, detail={"code": "FORM_BINDING_CONFLICT"}) from None
    return {"id": str(doc["_id"]), "project_id": doc["project_id"], "form_id": doc["form_id"],
            "version": doc["version"], "version_ref": doc["version_ref"], "title": doc["title"],
            "purpose": doc["purpose"], "status": doc["status"], "verified_at": now}


@router.post("", status_code=201)
async def create_form_binding(payload: FormBindingRequest, actor=Depends(require_catalog_admin),
                              db=Depends(get_database), client=Depends(get_catalog_client)):
    return await bind_form(db, client, actor, payload)


@router.get("")
async def list_form_bindings(skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
                             actor=Depends(require_catalog_admin), db=Depends(get_database)):
    cursor = db.external_form_bindings.find({}).sort([("verified_at", -1), ("_id", -1)]).skip(skip).limit(limit)
    result = []
    async for row in cursor:
        result.append({"id": str(row["_id"]), **{k: row[k] for k in
            ("project_id", "form_id", "version", "version_ref", "title", "purpose", "status", "verified_at")}})
    return {"items": result, "skip": skip, "limit": limit,
            "total": await db.external_form_bindings.count_documents({})}


@router.post("/{binding_id}/revoke")
async def revoke_form_binding(binding_id: str, payload: RevokeFormBindingRequest,
                               actor=Depends(require_catalog_admin), db=Depends(get_database)):
    if not ObjectId.is_valid(binding_id):
        raise HTTPException(422, detail={"code": "INVALID_FORM_BINDING_ID"})
    now = datetime.now(timezone.utc)
    result = await db.external_form_bindings.update_one(
        {"_id": ObjectId(binding_id), "status": "active"},
        {"$set": {"status": "revoked", "revoked_at": now},
         "$push": {"audit": {"action": "revoke_form", "actor_id": str(actor.id),
                              "at": now, "reason": payload.reason}}})
    if result.modified_count != 1:
        raise HTTPException(409, detail={"code": "FORM_BINDING_NOT_ACTIVE"})
    return {"id": binding_id, "status": "revoked", "revoked_at": now}
