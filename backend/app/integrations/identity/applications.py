"""Access requests from a verified questionnaire login before any clinical role exists."""
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException
from pymongo import ASCENDING

from .bindings import manage_binding

REQUESTED_ROLES = {"patient", "doctor", "health_manager"}


def _public(row):
    return {"id": str(row["_id"]), "requested_role": row["requested_role"], "note": row.get("note") or "",
            "status": row["status"], "created_at": row["created_at"],
            "local_user_id": row.get("local_user_id"), "reason": row.get("reason")}


async def _indexes(db):
    await db.access_applications.create_index(
        [("issuer", ASCENDING), ("subject", ASCENDING)], unique=True, name="one_open_access_application",
        partialFilterExpression={"status": "pending"})


async def submit_application(db, session, requested_role, note):
    if not session or not session.get("authenticated") or session.get("identity_state") != "pending_binding":
        raise HTTPException(403, detail={"code": "ACCESS_APPLICATION_NOT_ALLOWED"})
    if requested_role not in REQUESTED_ROLES:
        raise HTTPException(422, detail={"code": "INVALID_ROLE"})
    note = (note or "").strip()
    if len(note) > 500:
        raise HTTPException(422, detail={"code": "NOTE_TOO_LONG"})
    await _indexes(db)
    existing = await db.access_applications.find_one(
        {"issuer": session["issuer"], "subject": session["subject"], "status": "pending"})
    if existing:
        return _public(existing)
    now = datetime.now(timezone.utc)
    document = {"_id": ObjectId(), "issuer": session["issuer"], "subject": session["subject"],
                "requested_role": requested_role, "note": note, "status": "pending", "created_at": now}
    try:
        await db.access_applications.insert_one(document)
    except Exception as exc:
        if exc.__class__.__name__ != "DuplicateKeyError":
            raise
        existing = await db.access_applications.find_one(
            {"issuer": session["issuer"], "subject": session["subject"], "status": "pending"})
        return _public(existing)
    return _public(document)


async def own_application(db, session):
    if not session or not session.get("authenticated"):
        raise HTTPException(401, detail={"code": "UNAUTHENTICATED"})
    row = await db.access_applications.find_one(
        {"issuer": session["issuer"], "subject": session["subject"]}, sort=[("created_at", -1)])
    return _public(row) if row else None


async def list_applications(db, status="pending"):
    if status not in {"pending", "approved", "rejected"}:
        raise HTTPException(422, detail={"code": "INVALID_STATUS"})
    cursor = db.access_applications.find({"status": status}).sort("created_at", 1)
    return [_public(row) async for row in cursor]


async def decide_application(db, actor, application_id, *, approved, local_user_id, evidence_reference, reason):
    if not ObjectId.is_valid(application_id):
        raise HTTPException(422, detail={"code": "INVALID_APPLICATION_ID"})
    row = await db.access_applications.find_one({"_id": ObjectId(application_id), "status": "pending"})
    if not row:
        raise HTTPException(404, detail={"code": "APPLICATION_NOT_PENDING"})
    now = datetime.now(timezone.utc)
    if not approved:
        reason = (reason or "").strip()
        if not reason:
            raise HTTPException(422, detail={"code": "REJECTION_REASON_REQUIRED"})
        await db.access_applications.update_one(
            {"_id": row["_id"], "status": "pending"},
            {"$set": {"status": "rejected", "reason": reason, "decided_at": now, "decided_by": str(actor.id)}})
        row.update(status="rejected", reason=reason)
        return _public(row)
    evidence_reference = (evidence_reference or "").strip()
    if not evidence_reference:
        raise HTTPException(422, detail={"code": "EVIDENCE_REQUIRED"})
    try:
        await manage_binding(db, issuer=row["issuer"], subject=row["subject"], actor_id=local_user_id,
                             reviewer=str(actor.id), evidence_reference=evidence_reference, action="bind", apply=True,
                             approved_role=row["requested_role"])
    except ValueError as exc:
        raise HTTPException(409, detail={"code": "BINDING_REJECTED", "message": str(exc)}) from None
    await db.access_applications.update_one(
        {"_id": row["_id"], "status": "pending"},
        {"$set": {"status": "approved", "local_user_id": local_user_id, "evidence_reference": evidence_reference,
                  "decided_at": now, "decided_by": str(actor.id)}})
    row.update(status="approved", local_user_id=local_user_id)
    return _public(row)
