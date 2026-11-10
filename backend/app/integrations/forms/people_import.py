"""Import a granted project roster, then let an administrator choose local roles.

Subjects arrive as patients. Other members arrive without a role. The same source
record is not imported twice. A later role change clears patient assignments;
an existing login binding stops matching until it is reviewed again.
"""
import hashlib
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

from .catalog_service import people as load_people

LOCAL_ROLES = {"unassigned", "patient", "doctor", "health_manager"}
ROLE_FOR_KIND = {"subject": "patient", "member": "unassigned"}


def _storage_key(origin, person_key):
    return hashlib.sha256(f"{origin}\n{person_key}".encode()).hexdigest()


async def _ensure_index(users):
    await users.create_index([("source_person_key", ASCENDING)], unique=True,
                             name="unique_source_person",
                             partialFilterExpression={"source_person_key": {"$type": "string"}})


def _public(doc):
    return {"id": str(doc["_id"]), "name": doc.get("name") or "", "role": doc.get("role"),
            "source_kind": doc.get("source_kind"), "source_person_ref": doc.get("source_person_ref"),
            "source_project_id": doc.get("source_project_id"),
            "subject_code": doc.get("source_subject_code"),
            "practitioners": list(doc.get("practitioners") or []),
            "health_managers": list(doc.get("health_managers") or [])}


async def list_imported_people(db, origin, project_id):
    cursor = db.users.find({"source_origin": origin, "source_project_id": project_id}).sort("name", 1)
    return [_public(row) async for row in cursor]


async def import_project_people(db, client, actor, project_id):
    origin = client.source_origin
    await _ensure_index(db.users)
    created = existing = 0
    cursor = None
    for _ in range(100):
        page = await load_people(client, project_id, limit=100, cursor=cursor)
        for person in page["data"]:
            key = _storage_key(origin, person["person_key"])
            if await db.users.find_one({"source_person_key": key}, {"_id": 1}):
                existing += 1
                continue
            now = datetime.now(timezone.utc)
            role = ROLE_FOR_KIND[person["kind"]]
            document = {
                "_id": ObjectId(),
                "email": f"import-{key[:32]}@source-import.invalid",
                "name": person["display_name"] or person["person_key"],
                "password_hash": "!",
                "role": role,
                "permissions": [],
                "is_active": True,
                "created_at": now,
                "updated_at": now,
                "source_person_key": key,
                "source_origin": origin,
                "source_project_id": project_id,
                "source_kind": person["kind"],
                "source_person_ref": person["person_key"],
                "source_subject_id": person.get("subject_id"),
                "source_subject_code": person.get("subject_code"),
                "source_patient_id": person.get("source_patient_id"),
                "source_user_id": person.get("source_user_id"),
                "oidc_subject": person.get("oidc_subject"),
                "imported_by": str(actor.id),
                "practitioners": [],
                "health_managers": [],
                "patients": [],
                "role_reviews": [],
            }
            try:
                await db.users.insert_one(document)
            except DuplicateKeyError:
                existing += 1
            else:
                created += 1
        if not page["page"]["has_more"]:
            break
        cursor = page["page"]["next_cursor"]
    else:
        raise HTTPException(502, detail={"code": "SOURCE_ROSTER_TOO_LARGE"})
    return {"created": created, "existing": existing,
            "people": await list_imported_people(db, origin, project_id)}


async def assign_imported_role(db, actor, user_id, role, evidence_reference):
    if role not in LOCAL_ROLES:
        raise HTTPException(422, detail={"code": "INVALID_ROLE"})
    if not ObjectId.is_valid(user_id):
        raise HTTPException(422, detail={"code": "INVALID_USER_ID"})
    user = await db.users.find_one({"_id": ObjectId(user_id), "source_person_key": {"$type": "string"}})
    if not user:
        raise HTTPException(404, detail={"code": "IMPORTED_PERSON_NOT_FOUND"})
    if user.get("role") == role:
        return _public(user)
    uid = str(user["_id"])
    now = datetime.now(timezone.utc)
    review = {"role": role, "previous_role": user.get("role"), "actor_id": str(actor.id),
              "evidence_reference": evidence_reference, "at": now}
    await db.users.update_many(
        {"$or": [{"practitioners": uid}, {"health_managers": uid}]},
        {"$pull": {"practitioners": uid, "health_managers": uid}, "$set": {"updated_at": now}})
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"role": role, "patients": [], "practitioners": [], "health_managers": [], "updated_at": now},
         "$push": {"role_reviews": review}})
    user.update(role=role, patients=[], practitioners=[], health_managers=[])
    return _public(user)


async def _imported_person(db, user_id):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(422, detail={"code": "INVALID_USER_ID"})
    user = await db.users.find_one({"_id": ObjectId(user_id), "source_person_key": {"$type": "string"}})
    if not user:
        raise HTTPException(404, detail={"code": "IMPORTED_PERSON_NOT_FOUND"})
    return user


async def set_imported_care(db, actor, patient_id, practitioner_id, *, assigned, evidence_reference):
    """Connect a doctor or health manager to a patient imported from the same project."""
    if patient_id == practitioner_id:
        raise HTTPException(422, detail={"code": "CARE_SELF_ASSIGNMENT"})
    patient = await _imported_person(db, patient_id)
    practitioner = await _imported_person(db, practitioner_id)
    if (patient.get("source_origin") != practitioner.get("source_origin")
            or patient.get("source_project_id") != practitioner.get("source_project_id")):
        raise HTTPException(409, detail={"code": "DIFFERENT_PROJECT"})
    if patient.get("role") != "patient" or practitioner.get("role") not in {"doctor", "health_manager"}:
        raise HTTPException(409, detail={"code": "CARE_ROLE_MISMATCH"})
    field = "practitioners" if practitioner["role"] == "doctor" else "health_managers"
    patient_links = list(patient.get(field) or [])
    clinician_links = list(practitioner.get("patients") or [])
    practitioner_ref, patient_ref = str(practitioner["_id"]), str(patient["_id"])
    if assigned:
        if practitioner_ref not in patient_links:
            patient_links.append(practitioner_ref)
        if patient_ref not in clinician_links:
            clinician_links.append(patient_ref)
    else:
        patient_links = [item for item in patient_links if item != practitioner_ref]
        clinician_links = [item for item in clinician_links if item != patient_ref]
    now = datetime.now(timezone.utc)
    review = {"action": "assign" if assigned else "remove", "field": field,
              "practitioner_id": practitioner_ref, "actor_id": str(actor.id),
              "evidence_reference": evidence_reference, "at": now}
    await db.users.update_one({"_id": patient["_id"]},
                              {"$set": {field: patient_links, "updated_at": now}, "$push": {"care_reviews": review}})
    await db.users.update_one({"_id": practitioner["_id"]},
                              {"$set": {"patients": clinician_links, "updated_at": now}})
    patient[field] = patient_links
    return _public(patient)
