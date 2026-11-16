"""Authorized, reviewed source candidates for starting a fill task."""

from typing import Any, Dict

from bson import ObjectId
from fastapi import HTTPException

from app.core.patient_access import (
    patient_domain_context, patient_assignment_field, PatientAccessError,
    is_domain_state_unavailable,
)


ALLOWED_ROLES = {"doctor", "health_manager", "admin"}
MAX_SKIP = 10_000
MAX_LIMIT = 100


def _patient_match(context, actor) -> Dict[str, Any]:
    if context.is_canonical:
        match: Dict[str, Any] = {"status": "active"}
    else:
        match = {"role": "patient", "is_active": True}

    if actor.role == "admin":
        return match

    field = patient_assignment_field(actor.role)
    operator_id = str(actor.id)
    identifiers: list[Any] = [operator_id]
    if ObjectId.is_valid(operator_id):
        identifiers.append(ObjectId(operator_id))
    match[field] = {"$in": identifiers}
    return match


def _pipeline(context, actor, source_origin: str, skip: int, limit: int) -> list[Dict[str, Any]]:
    patient_id_field = {"$toString": "$patient_id"} if context.is_canonical else {"$toString": "$_id"}
    return [
        {"$match": _patient_match(context, actor)},
        {"$addFields": {"_fill_patient_id": patient_id_field}},
        {"$lookup": {
            "from": "external_patient_links",
            "localField": "_fill_patient_id",
            "foreignField": "local_patient_id",
            "as": "_fill_links",
        }},
        {"$unwind": "$_fill_links"},
        {"$match": {
            "_fill_links.status": "verified",
            "_fill_links.source_origin": source_origin,
            "_fill_links.verified_by": {"$type": "string", "$ne": ""},
            "_fill_links.verified_at": {"$type": "date"},
            "_fill_links.evidence_reference": {"$type": "string", "$ne": ""},
        }},
        {"$addFields": {"_fill_references": {"$ifNull": [
            "$_fill_links.references", ["$_fill_links.reference"]]}}},
        {"$unwind": "$_fill_references"},
        {"$match": {
            "_fill_links.source_origin": {"$type": "string", "$ne": ""},
            "_fill_references.project_id": {"$type": "number", "$gt": 0},
            "_fill_references.center_id": {"$type": "number", "$gt": 0},
            "_fill_references.subject_id": {"$type": "number", "$gt": 0},
            "_fill_references.source.system": "form-platform-11344",
            "_fill_references.source.environment": {"$in": ["pilot", "production"]},
        }},
        {"$lookup": {
            "from": "external_form_bindings",
            "let": {
                "project_id": "$_fill_references.project_id",
                "source_origin": "$_fill_links.source_origin",
                "source_system": "$_fill_references.source.system",
                "source_environment": "$_fill_references.source.environment",
            },
            "pipeline": [
                {"$match": {"$expr": {"$and": [
                    {"$eq": ["$status", "active"]},
                    {"$eq": ["$project_id", "$$project_id"]},
                    {"$eq": ["$source_origin", "$$source_origin"]},
                    {"$eq": ["$source.system", "$$source_system"]},
                    {"$eq": ["$source.environment", "$$source_environment"]},
                    {"$in": ["$purpose", ["initial_assessment", "followup", "reassessment"]]},
                    {"$eq": ["$version_ref.version_state", "current"]},
                ]}}},
                {"$match": {
                    "verified_by": {"$type": "string", "$ne": ""},
                    "verified_at": {"$type": "date"},
                    "evidence_reference": {"$type": "string", "$ne": ""},
                    "version_ref.form_id": {"$type": "number"},
                    "version_ref.version": {"$type": "number"},
                }},
                {"$project": {
                    "form_id": 1, "version": 1, "purpose": 1, "title": 1,
                }},
            ],
            "as": "_fill_forms",
        }},
        {"$match": {"_fill_forms.0": {"$exists": True}}},
        {"$project": {
            "patient_id": "$_fill_patient_id",
            "name": 1,
            "reference": {
                "project_id": "$_fill_references.project_id",
                "center_id": "$_fill_references.center_id",
                "subject_id": "$_fill_references.subject_id",
            },
            "forms": {"$map": {
                "input": "$_fill_forms", "as": "form", "in": {
                    "binding_id": {"$toString": "$$form._id"},
                    "form_id": "$$form.form_id",
                    "version": "$$form.version",
                    "purpose": "$$form.purpose",
                    "title": "$$form.title",
                },
            }},
        }},
        {"$group": {
            "_id": "$patient_id",
            "name": {"$first": "$name"},
            "references": {"$push": {
                "project_id": "$reference.project_id",
                "center_id": "$reference.center_id",
                "subject_id": "$reference.subject_id",
                "forms": "$forms",
            }},
        }},
        {"$sort": {"_id": 1}},
        {"$facet": {
            "patients": [
                {"$skip": skip}, {"$limit": limit},
                {"$project": {"_id": 0, "patient_id": "$_id", "name": 1, "references": 1}},
            ],
            "total": [{"$count": "count"}],
        }},
    ]


async def list_fill_candidates(db, actor, source_origin: str, *, skip: int = 0,
                               limit: int = 50) -> Dict[str, Any]:
    if actor.role not in ALLOWED_ROLES:
        raise HTTPException(403, detail={"error": "FILL_CANDIDATES_FORBIDDEN",
                                         "message": "当前角色不能发起表单填报"})
    if skip < 0 or skip > MAX_SKIP or limit < 1 or limit > MAX_LIMIT:
        raise HTTPException(422, detail={"error": "INVALID_FILL_CANDIDATE_PAGINATION",
                                         "message": "候选列表分页参数无效"})

    context = await patient_domain_context(db)
    collection = db.clinical_patients if context.is_canonical else db.users
    cursor = collection.aggregate(_pipeline(context, actor, source_origin, skip, limit))
    pages = await cursor.to_list(length=1)
    page = pages[0] if pages else {"patients": [], "total": []}
    total = page.get("total") or []
    patients = page.get("patients", [])
    if actor.role != "admin":
        for patient in patients:
            try:
                await context.ensure_patient_access(
                    patient["patient_id"], str(actor.id), actor.role)
            except PatientAccessError as exc:
                if is_domain_state_unavailable(exc) or exc.error_code == "PATIENT_IDENTITY_AMBIGUOUS":
                    raise HTTPException(exc.status_code, detail={
                        "error": exc.error_code, "message": exc.message,
                    }) from exc
                # Scope can change between the aggregation and this final shared
                # authorization check. Fail closed for that row.
                patient["references"] = []
        patients = [patient for patient in patients if patient["references"]]
    return {
        "patients": patients,
        "skip": skip,
        "limit": limit,
        "total": total[0]["count"] if total else 0,
    }
