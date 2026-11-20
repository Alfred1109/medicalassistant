"""Assigned, patient-owned questionnaire filling over the source platform."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
import secrets
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

from bson import ObjectId
from cryptography.fernet import Fernet
from fastapi import HTTPException

from app.core.patient_access import (
    PatientAccessError,
    ensure_self_patient_access,
    patient_domain_context,
)
from app.core.config import settings
from app.db.transactions import run_followup_transaction
from app.integrations.identity.service import digest

from . import models, service
from .client import FormPlatformError
from .service import FormIntegrationError

TASK_TYPE = "patient_self"
BRIDGE_COLLECTION = "integration_patient_self_bridges"
PATIENT_ROLES = {"doctor", "health_manager"}
ACTIVE_TASK_STATES = {"assigned", "active"}
VISIBLE_TASK_STATES = {"assigned", "active", "submitted", "revoking", "revoke_failed", "revoked", "expired"}
CALLBACK_ACTIONS = {"consume", "read", "save", "submit"}
PAGE_LIMIT = 100


def _encrypt(value: str, settings_obj=None) -> str:
    if settings_obj is None:
        from app.integrations.identity.config import oidc_settings as settings_obj
    key = settings_obj.session_encryption_key.get_secret_value().encode("ascii")
    return Fernet(key).encrypt(value.encode("utf-8")).decode("ascii")


def _decrypt(value: str, settings_obj=None) -> str:
    if settings_obj is None:
        from app.integrations.identity.config import oidc_settings as settings_obj
    key = settings_obj.session_encryption_key.get_secret_value().encode("ascii")
    return Fernet(key).decrypt(value.encode("ascii")).decode("utf-8")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _task_id(value: str) -> ObjectId:
    if not isinstance(value, str) or not ObjectId.is_valid(value):
        raise FormIntegrationError("患者填报任务不存在", error_code="SELF_FILL_TASK_NOT_FOUND", status_code=404)
    return ObjectId(value)


def _actor_id(actor: Any) -> str:
    return str(getattr(actor, "id", ""))


async def _lock_patient_assignment(db, session, patient_id: str, operator_id: str, role: str):
    """Write-fence the actual patient record against concurrent assignment revocation."""
    context = await patient_domain_context(db, session=session)
    patient = await context.ensure_patient_access(patient_id, operator_id, role)
    field = context.assignment_field(role)
    values = [operator_id]
    if ObjectId.is_valid(operator_id):
        values.append(ObjectId(operator_id))
    query = {"_id": patient["_id"], field: {"$in": values}}
    if context.is_canonical:
        query.update(patient_id=patient_id, status="active")
        collection = db.clinical_patients
    else:
        query.update(role="patient", is_active=True)
        collection = db.users
    result = await collection.update_one(query, {"$inc": {"patient_self_fill_use_revision": 1}}, session=session)
    if result.matched_count != 1:
        raise FormIntegrationError("患者归属已变化，未保存本人填报任务", error_code="PATIENT_ASSIGNMENT_CHANGED", status_code=409)
    return patient


async def _patient_subject_binding(db, patient_actor, issuer: str):
    """Return the sole enabled, reviewed OneID patient binding for this actor."""
    rows = await db.oidc_principal_bindings.find({
        "issuer": issuer, "actor_id": str(patient_actor.id), "enabled": True,
        "approved_role": "patient",
    }).limit(2).to_list(length=2)
    if len(rows) != 1:
        raise FormIntegrationError("患者账号尚未绑定唯一有效的 OneID 患者身份", error_code="PATIENT_ONEID_BINDING_REQUIRED", status_code=403)
    binding = rows[0]
    if (not isinstance(binding.get("subject"), str) or not binding["subject"]
            or not isinstance(binding.get("authorization_revision"), str)
            or not binding["authorization_revision"]):
        raise FormIntegrationError("OneID 患者绑定记录无效", error_code="PATIENT_ONEID_BINDING_INVALID", status_code=403)
    return binding


async def _lock_patient_binding(db, session, binding):
    result = await db.oidc_principal_bindings.update_one({
        "_id": binding["_id"], "issuer": binding["issuer"], "subject": binding["subject"],
        "actor_id": binding["actor_id"], "enabled": True, "approved_role": "patient",
        "authorization_revision": binding["authorization_revision"],
    }, {"$inc": {"patient_self_fill_use_revision": 1}}, session=session)
    if result.matched_count != 1:
        raise FormIntegrationError("患者 OneID 身份绑定已变化", error_code="PATIENT_ONEID_BINDING_CHANGED", status_code=409)


async def _lock_patient_self_mapping(db, session, patient_actor, patient_id):
    """Fence the actual legacy self document or canonical verified account link."""
    context = await patient_domain_context(db, session=session)
    try:
        resolved = await context.ensure_self_patient_access(patient_actor, patient_id)
    except PatientAccessError as exc:
        raise FormIntegrationError("患者账号未关联有效患者档案", error_code="SELF_PATIENT_UNAVAILABLE",
                                   status_code=403) from exc
    if resolved != str(patient_id):
        raise FormIntegrationError("患者账号与任务档案不匹配", error_code="SELF_FILL_TASK_FORBIDDEN", status_code=403)
    if context.is_canonical:
        link = await db.patient_account_links.find_one({"account_id": _actor_id(patient_actor),
            "patient_id": resolved, "status": "verified"}, session=session)
        if not link:
            raise FormIntegrationError("患者档案账号绑定已撤销", error_code="SELF_PATIENT_UNAVAILABLE", status_code=403)
        result = await db.patient_account_links.update_one({
            "_id": link["_id"], "account_id": _actor_id(patient_actor), "patient_id": resolved,
            "status": "verified", "source": link.get("source"), "account_document_id": link.get("account_document_id"),
            "schema_version": link.get("schema_version"), "audit": link.get("audit"),
        }, {"$inc": {"patient_self_fill_use_revision": 1}}, session=session)
    else:
        patient = await context.load_patient_doc(resolved)
        result = await db.users.update_one({"_id": patient["_id"], "role": "patient", "is_active": True},
            {"$inc": {"patient_self_fill_use_revision": 1}}, session=session)
    if result.matched_count != 1:
        raise FormIntegrationError("患者账号与档案关联已变化", error_code="SELF_PATIENT_UNAVAILABLE", status_code=409)


def serialize_patient_task(doc: Dict[str, Any], *, include_staff=False, include_evidence=False) -> Dict[str, Any]:
    self_fill = doc.get("patient_self") or {}
    refs = doc.get("remote_refs") or {}
    result = {
        "id": str(doc.get("_id")),
        "status": self_fill.get("status", "assigned"),
        "remoteRefs": {key: refs.get(key) for key in ("project_id", "center_id", "subject_id", "questionnaire_id")},
        "visitName": doc.get("visit_name"),
        "followupVisitId": str(doc["followup_visit_id"]) if doc.get("followup_visit_id") else None,
        "session": {
            "sessionId": self_fill.get("source_session_id"),
            "status": self_fill.get("source_status"),
            "expiresAt": self_fill.get("expires_at").isoformat() + "Z" if isinstance(self_fill.get("expires_at"), datetime) else None,
        },
        "submittedAt": self_fill.get("submitted_at").isoformat() + "Z" if isinstance(self_fill.get("submitted_at"), datetime) else None,
        "createdAt": doc.get("created_at").isoformat() + "Z" if doc.get("created_at") else None,
    }
    if include_staff:
        result["patientId"] = doc.get("patient_id")
        result["operator"] = {"userId": (doc.get("operator") or {}).get("user_id"),
                              "role": (doc.get("operator") or {}).get("role")}
    if doc.get("status") == models.TASK_STATUS_CONFIRMED:
        result["status"] = models.TASK_STATUS_CONFIRMED
    if include_staff and include_evidence and doc.get("status") == models.TASK_STATUS_CONFIRMED:
        confirmation = doc.get("confirmation")
        if isinstance(confirmation, dict) and confirmation.get("fill_mode") == TASK_TYPE:
            result["verifiedEvidence"] = deepcopy(confirmation)
    return result


def _version_reference(value):
    if not isinstance(value, dict):
        return None
    keys = ("form_id", "family_id", "version", "definition_sha256")
    return {key: value.get(key) for key in keys}


def _same_remote_refs(actual, expected):
    if not isinstance(actual, dict) or not isinstance(expected, dict):
        return False
    keys = ("project_id", "center_id", "subject_id", "questionnaire_id")
    return all(type(actual.get(key)) is type(expected.get(key)) and actual.get(key) == expected.get(key)
               for key in keys)


def _parse_source_datetime(value, label):
    if not isinstance(value, str) or not value:
        raise FormIntegrationError(f"源端{label}缺失", error_code="SELF_FILL_RESPONSE_INVALID", status_code=502)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise FormIntegrationError(f"源端{label}格式无效", error_code="SELF_FILL_RESPONSE_INVALID", status_code=502) from None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _response_snapshot_digest(confirmation):
    stable = {key: confirmation.get(key) for key in (
        "fill_mode", "session_uuid", "response_id", "remote_status", "submitted_at",
        "updated_at", "questionnaire_version_ref", "visit_code", "answers")}
    serialized = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256(serialized)


def _verified_source_snapshot(task, remote):
    """Validate source-owned self-fill evidence against the reviewed local task."""
    session = remote.get("session") if isinstance(remote, dict) else None
    response = remote.get("response") if isinstance(remote, dict) else None
    if not isinstance(session, dict) or not isinstance(response, dict):
        raise FormIntegrationError("源端未返回患者本人答卷证据", error_code="SELF_FILL_RESPONSE_INVALID", status_code=502)
    self_fill = task.get("patient_self") or {}
    refs = task.get("remote_refs") or {}
    context = task.get("reviewed_context") or {}
    expected_version = _version_reference(context.get("version_ref"))
    expected_session_id = self_fill.get("source_session_id")
    response_id = response.get("response_id")
    if (session.get("session_uuid") != expected_session_id
            or not expected_session_id
            or session.get("rehabman_task_ref") != self_fill.get("rehabman_task_ref")
            or session.get("status") != "submitted"
            or session.get("response_id") != response_id
            or type(response_id) is not int or response_id <= 0):
        raise FormIntegrationError("源端会话、任务和答卷引用不匹配", error_code="SELF_FILL_RESPONSE_MISMATCH", status_code=409)
    if (not _same_remote_refs(session, refs) or not _same_remote_refs(response, refs)
            or session.get("questionnaire_version_ref") != expected_version
            or _version_reference(response.get("form")) != expected_version
            or self_fill.get("pinned_version_sha256") != expected_version.get("definition_sha256")):
        raise FormIntegrationError("源端患者、问卷或版本与已审核任务不匹配", error_code="SELF_FILL_VERSION_MISMATCH", status_code=409)
    if (response.get("status") != "submitted" or response.get("is_voided") is not False
            or response.get("user_id", object()) is not None
            or response.get("patient_id") != session.get("patient_id")):
        raise FormIntegrationError("源端答卷未提交、已作废或不属于患者本人会话", error_code="SELF_FILL_RESPONSE_MISMATCH", status_code=409)
    answers = response.get("answers")
    if (not isinstance(answers, list)
            or any(not isinstance(answer, dict) or "question_id" not in answer
                   or (answer.get("answer_text") is not None
                       and not isinstance(answer.get("answer_text"), str)) for answer in answers)):
        raise FormIntegrationError("源端答卷回答格式无效", error_code="SELF_FILL_RESPONSE_INVALID", status_code=502)
    submitted_at = _parse_source_datetime(response.get("submitted_at"), "提交时间")
    updated_at = _parse_source_datetime(response.get("updated_at"), "答卷更新时间")
    source_visit_code = response.get("visit_code")
    if source_visit_code is not None and not isinstance(source_visit_code, str):
        raise FormIntegrationError("源端访视标识格式无效", error_code="SELF_FILL_RESPONSE_INVALID", status_code=502)
    if isinstance(source_visit_code, str):
        source_visit_code = source_visit_code.strip() or None
    confirmation = {
        "fill_mode": TASK_TYPE,
        "session_uuid": expected_session_id,
        "response_id": response_id,
        "remote_status": "submitted",
        "is_voided": False,
        "user_id": None,
        "submitted_at": submitted_at.isoformat() + "Z",
        "updated_at": updated_at.isoformat() + "Z",
        "questionnaire_version_ref": expected_version,
        "visit_code": source_visit_code,
        "answers": deepcopy(answers),
        "verified_at": datetime.utcnow().isoformat() + "Z",
    }
    confirmation["snapshot_sha256"] = _response_snapshot_digest(confirmation)
    return confirmation


async def confirm_task(db, client, task_id: str, operator):
    """Verify a submitted patient-owned answer and atomically attach it to its visit."""
    if operator.role not in PATIENT_ROLES:
        raise FormIntegrationError("仅医生或健康管理师可核验患者本人填报", error_code="SELF_FILL_ASSIGNMENT_ROLE_REQUIRED", status_code=403)
    task = await _task_for_id(db, task_id)
    if (task.get("operator") or {}).get("user_id") != _actor_id(operator):
        raise FormIntegrationError("只能核验自己分配的患者任务", error_code="SELF_FILL_TASK_FORBIDDEN", status_code=403)
    await service._verify_patient_assignment(db, task.get("patient_id"), _actor_id(operator), operator.role)
    await service.require_task_reviewed_context(db, task)
    self_fill = task.get("patient_self") or {}
    if self_fill.get("status") not in {"active", "submitted"} or not self_fill.get("source_session_id"):
        raise FormIntegrationError("患者本人问卷尚未提交或已关闭", error_code="SELF_FILL_NOT_SUBMITTED", status_code=409)
    try:
        remote = await client.get_patient_self_fill_response(self_fill["source_session_id"])
    except FormPlatformError as exc:
        raise service._map_remote_error(exc, "核验患者本人答卷失败") from exc
    evidence = _verified_source_snapshot(task, remote)
    evidence["verified_by"] = _actor_id(operator)
    evidence["verified_by_role"] = operator.role
    followup_visit_id = task.get("followup_visit_id")
    node_visit_code = None
    if followup_visit_id and task.get("status") != models.TASK_STATUS_CONFIRMED:
        visit = await service._load_followup_visit(db, str(followup_visit_id))
        if str(visit.get("patient_id")) != str(task.get("patient_id")):
            raise FormIntegrationError("随访节点与患者填报任务不匹配", error_code="FOLLOWUP_VISIT_PATIENT_MISMATCH", status_code=409)
        service._visit_is_writable(visit)
        node_visit_code = visit.get("visit_code")
        if task.get("visit_code") and task.get("visit_code") != node_visit_code:
            raise FormIntegrationError("任务访视与随访节点不一致", error_code="RESPONSE_MISMATCH", status_code=409)
        if node_visit_code and evidence.get("visit_code") and evidence["visit_code"] != node_visit_code:
            raise FormIntegrationError("源端答卷访视与随访节点不一致", error_code="RESPONSE_MISMATCH", status_code=409)

    await service._require_transaction_topology(db)
    from app.core.followup_semantics import followup_version_filter, followup_submission_fields
    from app.models.health_record import FollowUpRecord

    async def persist(session):
        current = await db[models.COLLECTION_NAME].find_one({"_id": task["_id"], "task_type": TASK_TYPE}, session=session)
        if not current:
            raise FormIntegrationError("患者填报任务不存在", error_code="SELF_FILL_TASK_NOT_FOUND", status_code=404)
        await _lock_patient_assignment(db, session, current.get("patient_id"), _actor_id(operator), operator.role)
        await service.require_task_reviewed_context(db, current, session=session)
        current_confirmation = current.get("confirmation") or {}
        current_status = (current.get("patient_self") or {}).get("status")
        if current.get("status") == models.TASK_STATUS_CONFIRMED:
            if (current_confirmation.get("fill_mode") == TASK_TYPE
                    and current_confirmation.get("snapshot_sha256") == evidence["snapshot_sha256"]):
                return current
            raise FormIntegrationError("已核验答卷快照发生变化，需人工核查", error_code="SELF_FILL_EVIDENCE_CHANGED", status_code=409)
        if current_status not in {"active", "submitted"} or (current.get("patient_self") or {}).get("source_session_id") != evidence["session_uuid"]:
            raise FormIntegrationError("患者任务在核验期间已变化", error_code="SELF_FILL_TASK_CHANGED", status_code=409)

        if followup_visit_id:
            visit = await db[FollowUpRecord.collection_name].find_one(
                {"_id": ObjectId(str(followup_visit_id))}, session=session)
            if (not visit or visit.get("deleted") or str(visit.get("patient_id")) != str(current.get("patient_id"))
                    or visit.get("visit_code") != node_visit_code):
                raise FormIntegrationError("关联随访节点已改变，请重新核验", error_code="FOLLOWUP_VISIT_CHANGED", status_code=409)
            service._visit_is_writable(visit)
            effective_response = visit.get("effective_response")
            if effective_response and (str(effective_response.get("task_id")) != str(current["_id"])
                                      or effective_response.get("response_id") != evidence["response_id"]):
                raise FormIntegrationError("随访节点已有其他当前答卷，请先审阅现有证据", error_code="FOLLOWUP_EVIDENCE_CONFLICT", status_code=409)
            values = {"status": "in_review", "effective_response": {
                "task_id": str(current["_id"]), "response_id": evidence["response_id"],
                "visit_code": node_visit_code or evidence.get("visit_code"),
                "submitted_at": evidence["submitted_at"], "confirmed_at": evidence["verified_at"]},
                "updated_at": models.utcnow(), "completion_data": None, "answers": [],
                "follow_up_result": None, "actual_date": None}
            followup_confirmation = {key: evidence[key] for key in (
                "fill_mode", "session_uuid", "response_id", "remote_status", "snapshot_sha256",
                "verified_at", "verified_by", "verified_by_role")}
            values.update(followup_submission_fields(visit, values, source="external_form",
                submitted_by=(current.get("patient_self") or {}).get("patient_actor_id"),
                submitted_at=_parse_source_datetime(evidence["submitted_at"], "提交时间"),
                confirmation=followup_confirmation))
            visit_result = await db[FollowUpRecord.collection_name].update_one(
                followup_version_filter(visit),
                {"$set": values, "$addToSet": {"fill_task_ids": current["_id"]},
                 "$inc": {"mutation_version": 1}}, session=session)
            if visit_result.matched_count != 1:
                raise FormIntegrationError("随访节点已被其他请求修改", error_code="FOLLOWUP_CONFLICT", status_code=409)

        now = models.utcnow()
        task_result = await db[models.COLLECTION_NAME].update_one({
            "_id": current["_id"], "task_type": TASK_TYPE,
            "status": current.get("status"), "mutation_version": current.get("mutation_version", 0),
            "patient_self.status": current_status,
            "patient_self.source_session_id": evidence["session_uuid"],
        }, {"$set": {"status": models.TASK_STATUS_CONFIRMED, "confirmation": evidence,
                     "confirmed_at": now, "session.response_id": evidence["response_id"],
                     "patient_self.source_status": "submitted", "patient_self.status": "submitted",
                     "patient_self.source_response_id": evidence["response_id"],
                     "patient_self.submitted_at": _parse_source_datetime(evidence["submitted_at"], "提交时间"),
                     "patient_self.confirmed_at": now, "last_error": None, "updated_at": now,
                     "patient_self.updated_at": now}, "$inc": {"mutation_version": 1}}, session=session)
        if task_result.matched_count != 1:
            raise FormIntegrationError("患者填报任务已被其他请求修改", error_code="SELF_FILL_TASK_CHANGED", status_code=409)
        return await db[models.COLLECTION_NAME].find_one({"_id": current["_id"]}, session=session)

    return await run_followup_transaction(db, persist)


async def create_patient_task(db, client, operator, payload, delegation=None):
    service.require_fill_enabled()
    if operator.role not in PATIENT_ROLES:
        raise FormIntegrationError("仅医生或健康管理师可分配患者本人填报任务", error_code="SELF_FILL_ASSIGNMENT_ROLE_REQUIRED", status_code=403)
    from app.integrations.identity.service import FillDelegation, OidcFailure, OidcUnavailable
    if (not isinstance(delegation, FillDelegation) or delegation.actor_id != _actor_id(operator)
            or delegation.role != operator.role or delegation.client.settings.issuer != client.source_origin):
        raise FormIntegrationError("分配任务需要有效的 OneID 身份委托", error_code="SOURCE_IDENTITY_REQUIRED", status_code=403)
    try:
        await delegation.revalidate()
    except OidcUnavailable:
        raise FormIntegrationError("身份源暂不可用", error_code="SOURCE_IDENTITY_UNAVAILABLE", status_code=503) from None
    except OidcFailure:
        raise FormIntegrationError("OneID 登录已失效", error_code="SOURCE_IDENTITY_REQUIRED", status_code=403) from None

    forbidden = {"patient_actor_subject", "patient_actor_id", "source_session_id", "rehabman_task_ref"}.intersection(payload)
    if forbidden:
        raise FormIntegrationError("患者身份与任务引用由服务端确定", error_code="SELF_FILL_IDENTITY_OVERRIDE_FORBIDDEN", status_code=422)
    patient_id = payload.get("patient_id")
    if not isinstance(patient_id, str) or not patient_id:
        raise FormIntegrationError("patient_id 必填", error_code="INVALID_PATIENT", status_code=422)
    await service._verify_patient_assignment(db, patient_id, _actor_id(operator), operator.role)
    followup_visit_id = payload.get("followup_visit_id")
    followup_visit = None
    if followup_visit_id:
        followup_visit = await service._load_followup_visit(db, followup_visit_id)
        service._visit_is_writable(followup_visit)
        if str(followup_visit.get("patient_id")) != patient_id:
            raise FormIntegrationError("随访节点与任务患者不一致", error_code="FOLLOWUP_VISIT_PATIENT_MISMATCH", status_code=409)

    refs = service._extract_remote_refs(payload)
    refs, reviewed_link, reviewed_binding, reviewed_reference = await service._reviewed_fill_context(
        db, client, patient_id, refs, payload)
    from urllib.parse import urlsplit
    origin = str(payload.get("allowed_origin") or "").rstrip("/")
    if not origin:
        raise FormIntegrationError("allowed_origin 必填", error_code="INVALID_ORIGIN", status_code=422)
    parsed = urlsplit(origin)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment
            or (settings.ENVIRONMENT.lower() == "production" and parsed.scheme != "https")):
        raise FormIntegrationError("allowed_origin 格式无效", error_code="INVALID_ORIGIN", status_code=422)
    ttl_seconds = payload.get("ttl_seconds", 1800)
    if type(ttl_seconds) is not int or not 60 <= ttl_seconds <= 86_400:
        raise FormIntegrationError("ttl_seconds 必须为60到86400秒", error_code="INVALID_TTL", status_code=422)

    task_id = ObjectId()
    task = models.FollowUpFillTask.new_task(
        patient_id=patient_id, operator_id=_actor_id(operator), operator_role=operator.role,
        remote_refs=refs, allowed_origin=origin, ma_task_ref=f"rehabman-self-{task_id}",
        visit_code=(payload.get("visit_code") or (followup_visit or {}).get("visit_code")),
        visit_name=payload.get("visit_name"), ttl_seconds=payload.get("ttl_seconds"),
        followup_visit_id=str(followup_visit_id) if followup_visit_id else None)
    task.doc["_id"] = task_id
    task.doc["mutation_version"] = 0
    task.doc["ttl_seconds"] = ttl_seconds
    task.doc["task_type"] = TASK_TYPE
    task.doc["reviewed_context"] = {
        "patient_link_id": reviewed_link["_id"], "form_binding_id": reviewed_binding["_id"],
        "reference": deepcopy(reviewed_reference), "version_ref": deepcopy(reviewed_binding["version_ref"]),
        "purpose": reviewed_binding["purpose"],
    }
    task.doc["patient_self"] = {
        "status": "assigned", "rehabman_task_ref": f"rehabman-self-{task_id}",
        "source_session_id": None, "source_status": None, "source_token_encrypted": None,
        "patient_actor_id": None, "patient_actor_subject": None, "patient_issuer": None,
        "patient_binding_revision": None, "pinned_version_sha256": reviewed_binding["version_ref"]["definition_sha256"],
        "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
    }
    await service._require_transaction_topology(db)

    async def persist(session):
        from app.core.followup_semantics import followup_version_filter
        try:
            await delegation.lock(db, session)
        except OidcFailure:
            raise FormIntegrationError("OneID 登录在保存期间失效", error_code="SOURCE_IDENTITY_CHANGED", status_code=403) from None
        await _lock_patient_assignment(db, session, patient_id, _actor_id(operator), operator.role)
        await service._lock_reviewed_fill_context(db, session, reviewed_link, reviewed_binding)
        if followup_visit_id:
            from app.models.health_record import FollowUpRecord
            visit = await db[FollowUpRecord.collection_name].find_one({"_id": ObjectId(followup_visit_id)}, session=session)
            if (not visit or str(visit.get("patient_id")) != patient_id
                    or visit.get("visit_code") != (followup_visit or {}).get("visit_code")):
                raise FormIntegrationError("随访节点已变化，未保存患者填报任务", error_code="FOLLOWUP_VISIT_CHANGED", status_code=409)
            service._visit_is_writable(visit)
            result = await db[FollowUpRecord.collection_name].update_one(
                followup_version_filter(visit),
                {"$addToSet": {"fill_task_ids": task_id}, "$inc": {"mutation_version": 1},
                 "$set": {"updated_at": models.utcnow()}}, session=session)
            if result.matched_count != 1:
                raise FormIntegrationError("随访节点已被其他请求修改", error_code="FOLLOWUP_VISIT_CHANGED", status_code=409)
        await db[models.COLLECTION_NAME].insert_one(deepcopy(task.doc), session=session)

    await run_followup_transaction(db, persist)
    return serialize_patient_task(task.doc, include_staff=True)


async def _task_for_id(db, task_id: str, *, task_type=TASK_TYPE):
    doc = await db[models.COLLECTION_NAME].find_one({"_id": _task_id(task_id), "task_type": task_type})
    if not doc:
        raise FormIntegrationError("患者填报任务不存在", error_code="SELF_FILL_TASK_NOT_FOUND", status_code=404)
    return doc


async def refresh_remote_status(db, client, task):
    """Refresh only source-owned state; never infer completion from Mini UI."""
    self_fill = task.get("patient_self") or {}
    session_id = self_fill.get("source_session_id")
    if not session_id or self_fill.get("status") not in {"active", "submitted", "revoking", "revoke_failed"}:
        return task
    try:
        remote = await client.get_patient_self_fill_session(session_id)
    except FormPlatformError as exc:
        raise service._map_remote_error(exc, "读取患者填报状态失败") from exc
    if remote.get("session_id") not in {None, session_id}:
        raise FormIntegrationError("源端会话与患者任务不匹配", error_code="SELF_FILL_SESSION_MISMATCH", status_code=502)
    if remote.get("rehabman_task_ref") not in {None, self_fill.get("rehabman_task_ref")}:
        raise FormIntegrationError("源端任务引用与本地任务不匹配", error_code="SELF_FILL_SESSION_MISMATCH", status_code=502)
    if remote.get("questionnaire_version_ref") is not None:
        expected = {key: (task.get("reviewed_context") or {}).get("version_ref", {}).get(key)
                    for key in ("form_id", "family_id", "version", "definition_sha256")}
        if remote["questionnaire_version_ref"] != expected:
            raise FormIntegrationError("源端问卷版本与任务固定版本不匹配", error_code="SELF_FILL_VERSION_MISMATCH", status_code=409)
    state = remote.get("status")
    local_updates = {"source_status": state, "updated_at": datetime.utcnow()}
    update = {"$set": {f"patient_self.{key}": value for key, value in local_updates.items()}}
    if state == "submitted":
        local_updates.update(status="submitted", submitted_at=datetime.utcnow())
        update["$set"].update({"patient_self.status": "submitted", "patient_self.submitted_at": local_updates["submitted_at"]})
    elif state in {"revoked", "cancelled", "canceled"}:
        local_updates["status"] = "revoked"
        update["$set"]["patient_self.status"] = "revoked"
    elif state in {"expired", "timed_out"}:
        local_updates["status"] = "expired"
        update["$set"]["patient_self.status"] = "expired"
    if ("patient_self.status" in update["$set"]
            and update["$set"]["patient_self.status"] != self_fill.get("status")):
        update["$inc"] = {"mutation_version": 1}
    if "$set" in update:
        result = await db[models.COLLECTION_NAME].update_one({"_id": task["_id"], "task_type": TASK_TYPE,
            "patient_self.source_session_id": session_id,
            "patient_self.status": self_fill.get("status")}, update)
        if result.matched_count == 1:
            task["patient_self"].update(local_updates)
            if update.get("$inc"):
                task["mutation_version"] = task.get("mutation_version", 0) + 1
    return task


async def _resolve_self_task(db, actor, doc):
    try:
        patient_id = await ensure_self_patient_access(db, actor, doc.get("patient_id"))
    except PatientAccessError as exc:
        raise FormIntegrationError("该任务不属于当前患者账号", error_code="SELF_FILL_TASK_FORBIDDEN", status_code=403) from exc
    if patient_id != str(doc.get("patient_id")):
        raise FormIntegrationError("该任务不属于当前患者账号", error_code="SELF_FILL_TASK_FORBIDDEN", status_code=403)
    return patient_id


async def list_tasks(db, actor, *, skip=0, limit=20, actionable_only=False):
    if not 0 <= skip <= 10000 or not 1 <= limit <= PAGE_LIMIT:
        raise FormIntegrationError("分页参数无效", error_code="INVALID_PAGINATION", status_code=422)
    if actor.role == "patient":
        try:
            patient_id = await ensure_self_patient_access(db, actor)
        except PatientAccessError as exc:
            raise FormIntegrationError("当前患者账号未绑定有效患者档案", error_code="SELF_PATIENT_UNAVAILABLE", status_code=403) from exc
        visible = ACTIVE_TASK_STATES if actionable_only else VISIBLE_TASK_STATES
        query = {"task_type": TASK_TYPE, "patient_id": patient_id,
                 "patient_self.status": {"$in": sorted(visible)}}
        include_staff = False
    elif actor.role in PATIENT_ROLES:
        from app.core.patient_access import patient_domain_context
        context = await patient_domain_context(db)
        patient_ids = await context.assigned_scope_ids(_actor_id(actor), actor.role)
        query = {"task_type": TASK_TYPE, "patient_id": {"$in": patient_ids},
                 "operator.user_id": _actor_id(actor)}
        include_staff = True
    else:
        raise FormIntegrationError("当前角色不能查看患者填报任务", error_code="SELF_FILL_ROLE_REQUIRED", status_code=403)
    total = await db[models.COLLECTION_NAME].count_documents(query)
    cursor = db[models.COLLECTION_NAME].find(query).sort("created_at", -1).skip(skip).limit(limit)
    rows = await cursor.to_list(length=limit)
    return {"items": [serialize_patient_task(row, include_staff=include_staff) for row in rows],
            "total": total, "skip": skip, "limit": limit}


async def _verify_live_patient_identity(db, task, patient_actor, issuer):
    await _resolve_self_task(db, patient_actor, task)
    binding = await _patient_subject_binding(db, patient_actor, issuer)
    self_fill = task.get("patient_self") or {}
    if self_fill.get("patient_actor_id") and self_fill.get("patient_actor_id") != _actor_id(patient_actor):
        raise FormIntegrationError("任务已绑定其他患者身份", error_code="SELF_FILL_TASK_FORBIDDEN", status_code=403)
    if self_fill.get("patient_actor_subject") and self_fill.get("patient_actor_subject") != binding.get("subject"):
        raise FormIntegrationError("患者 OneID 身份与任务绑定不一致", error_code="PATIENT_ONEID_BINDING_CHANGED", status_code=403)
    if self_fill.get("patient_binding_revision") and self_fill.get("patient_binding_revision") != binding.get("authorization_revision"):
        raise FormIntegrationError("患者 OneID 授权已变化", error_code="PATIENT_ONEID_BINDING_CHANGED", status_code=403)
    await service.require_task_reviewed_context(db, task)
    if self_fill.get("pinned_version_sha256") != (task.get("reviewed_context") or {}).get("version_ref", {}).get("definition_sha256"):
        raise FormIntegrationError("问卷版本固定信息不一致", error_code="SELF_FILL_VERSION_MISMATCH", status_code=409)
    return binding


async def _lock_task(db, session, task):
    result = await db[models.COLLECTION_NAME].update_one({
        "_id": task["_id"], "task_type": TASK_TYPE,
        "mutation_version": task.get("mutation_version", 0),
        "patient_self.status": task.get("patient_self", {}).get("status"),
        "patient_self.source_session_id": task.get("patient_self", {}).get("source_session_id"),
    }, {"$inc": {"patient_self.authorization_revision": 1}}, session=session)
    if result.matched_count != 1:
        raise FormIntegrationError("患者填报任务已变化，请重新读取", error_code="SELF_FILL_TASK_CHANGED", status_code=409)


async def _bind_patient_session(db, task, patient_actor, binding, session_context, session_id):
    """Persist the live OneID identity before source resume invokes callback."""
    transport = session_context["transport"]
    source_record = session_context["source_record"]
    mini = session_context.get("mini")
    source_session_hash = source_record["_id"]

    latest = await _task_for_id(db, str(task["_id"]))
    await _verify_live_patient_identity(db, latest, patient_actor, binding["issuer"])
    current = latest.get("patient_self") or {}
    if current.get("status") not in ACTIVE_TASK_STATES:
        raise FormIntegrationError("患者填报任务已撤销或关闭", error_code="SELF_FILL_TASK_NOT_ACTIVE", status_code=409)
    if current.get("source_session_id") and current["source_session_id"] != session_id:
        raise FormIntegrationError("源端会话与本地任务绑定不一致", error_code="SELF_FILL_SESSION_MISMATCH", status_code=409)

    async def persist(session):
        await _lock_task(db, session, latest)
        await _lock_patient_self_mapping(db, session, patient_actor, latest["patient_id"])
        await _lock_patient_binding(db, session, binding)
        if mini:
            mini_result = await db.oidc_mini_sessions.update_one({"_id": mini["_id"],
                "source_session_id": source_session_hash, "actor_id": _actor_id(patient_actor),
                "expires_at": {"$gt": datetime.utcnow()}}, {"$inc": {"patient_self_fill_use_revision": 1}}, session=session)
            if mini_result.matched_count != 1:
                raise FormIntegrationError("患者小程序登录已失效", error_code="MINI_SESSION_REQUIRED", status_code=403)
        source_result = await db.oidc_application_sessions.update_one({
            "_id": source_session_hash, "issuer": source_record["issuer"],
            "subject": source_record["subject"], "binding_revision": source_record["binding_revision"],
            "expires_at": {"$gt": datetime.utcnow()}}, {"$inc": {"patient_self_fill_use_revision": 1}}, session=session)
        if source_result.matched_count != 1:
            raise FormIntegrationError("OneID 登录已失效", error_code="SOURCE_IDENTITY_REQUIRED", status_code=403)
        current_task = await db[models.COLLECTION_NAME].find_one({"_id": latest["_id"], "task_type": TASK_TYPE,
            "mutation_version": latest.get("mutation_version", 0), "patient_self.status": current.get("status"),
            "patient_self.source_session_id": current.get("source_session_id")}, session=session)
        if not current_task:
            raise FormIntegrationError("患者填报任务已被撤销或修改", error_code="SELF_FILL_TASK_CHANGED", status_code=409)
        reviewed = current_task.get("reviewed_context") or {}
        link = await db.external_patient_links.find_one({"_id": ObjectId(str(reviewed.get("patient_link_id")))}, session=session)
        form = await db.external_form_bindings.find_one({"_id": ObjectId(str(reviewed.get("form_binding_id")))}, session=session)
        await service._lock_reviewed_fill_context(db, session, link, form)
        result = await db[models.COLLECTION_NAME].update_one({"_id": current_task["_id"],
            "task_type": TASK_TYPE, "mutation_version": current_task.get("mutation_version", 0),
            "patient_self.status": current_task["patient_self"]["status"],
            "patient_self.source_session_id": current_task["patient_self"].get("source_session_id")},
            {"$set": {
                "patient_self.status": "active", "patient_self.source_session_id": session_id,
                "patient_self.patient_actor_id": _actor_id(patient_actor),
                "patient_self.patient_actor_subject": binding["subject"],
                "patient_self.patient_issuer": binding["issuer"],
                "patient_self.patient_binding_revision": binding["authorization_revision"],
                "patient_self.mini_session_id": mini["_id"] if mini else None,
                "patient_self.source_session_hash": source_session_hash,
                "patient_self.identity_transport": transport,
                "patient_self.updated_at": datetime.utcnow(),
            }, "$inc": {"mutation_version": 1}}, session=session)
        if result.matched_count != 1:
            raise FormIntegrationError("患者填报任务已被其他请求修改", error_code="SELF_FILL_TASK_CHANGED", status_code=409)
        await db[BRIDGE_COLLECTION].delete_many({"task_id": str(current_task["_id"])}, session=session)

    await run_followup_transaction(db, persist)


async def _finalize_launch_bridge(db, session, task, patient_actor, binding,
                                 session_context, bridge, expires_at, remote):
    mini = session_context.get("mini")
    source_record = session_context["source_record"]
    await _lock_task(db, session, task)
    await _lock_patient_self_mapping(db, session, patient_actor, task["patient_id"])
    await _lock_patient_binding(db, session, binding)
    if mini:
        mini_result = await db.oidc_mini_sessions.update_one({"_id": mini["_id"],
            "source_session_id": source_record["_id"], "actor_id": _actor_id(patient_actor),
            "expires_at": {"$gt": datetime.utcnow()}}, {"$inc": {"patient_self_fill_use_revision": 1}}, session=session)
    source_result = await db.oidc_application_sessions.update_one({
        "_id": source_record["_id"], "issuer": source_record["issuer"],
        "subject": source_record["subject"], "binding_revision": source_record["binding_revision"],
        "expires_at": {"$gt": datetime.utcnow()}}, {"$inc": {"patient_self_fill_use_revision": 1}}, session=session)
    if (mini and mini_result.matched_count != 1) or source_result.matched_count != 1:
        raise FormIntegrationError("患者 OneID 登录已失效", error_code="SOURCE_IDENTITY_REQUIRED", status_code=403)
    current = await db[models.COLLECTION_NAME].find_one({"_id": task["_id"], "task_type": TASK_TYPE,
        "mutation_version": task.get("mutation_version", 0), "patient_self.status": "active",
        "patient_self.source_session_id": bridge["source_session_id"],
        "patient_self.mini_session_id": mini["_id"] if mini else None,
        "patient_self.source_session_hash": source_record["_id"]}, session=session)
    if not current:
        raise FormIntegrationError("任务或患者身份在启动期间已变化", error_code="SELF_FILL_TASK_CHANGED", status_code=409)
    reviewed = current.get("reviewed_context") or {}
    link = await db.external_patient_links.find_one({"_id": ObjectId(str(reviewed.get("patient_link_id")))}, session=session)
    form = await db.external_form_bindings.find_one({"_id": ObjectId(str(reviewed.get("form_binding_id")))}, session=session)
    await service._lock_reviewed_fill_context(db, session, link, form)
    result = await db[models.COLLECTION_NAME].update_one({"_id": current["_id"],
        "mutation_version": current.get("mutation_version", 0), "patient_self.status": "active",
        "patient_self.source_session_id": bridge["source_session_id"],
        "patient_self.mini_session_id": mini["_id"] if mini else None}, {
            "$set": {"patient_self.source_status": remote.get("status"),
                     "patient_self.expires_at": expires_at.replace(tzinfo=None),
                     "patient_self.updated_at": datetime.utcnow()},
            "$inc": {"mutation_version": 1}}, session=session)
    if result.matched_count != 1:
        raise FormIntegrationError("患者填报任务已被其他请求修改", error_code="SELF_FILL_TASK_CHANGED", status_code=409)


async def launch_task(db, client, task_id, patient_actor, *, oidc_client, settings_obj,
                      mini_token=None, browser_sid=None):
    if patient_actor.role != "patient":
        raise FormIntegrationError("患者本人账号登录后才能启动此问卷", error_code="SELF_FILL_ROLE_REQUIRED", status_code=403)
    task = await _task_for_id(db, task_id)
    binding = await _verify_live_patient_identity(db, task, patient_actor, oidc_client.settings.issuer)
    if (task.get("patient_self") or {}).get("status") not in ACTIVE_TASK_STATES:
        raise FormIntegrationError("该患者填报任务当前不可启动", error_code="SELF_FILL_TASK_NOT_ACTIVE", status_code=409)
    if mini_token:
        mini, mini_actor = await oidc_client.actor_for_mini_session(mini_token)
        if (mini is None or mini_actor is None or str(mini_actor["_id"]) != _actor_id(patient_actor)
                or mini_actor.get("role") != "patient"):
            raise FormIntegrationError("小程序登录已失效，请重新登录", error_code="MINI_SESSION_REQUIRED", status_code=403)
        source_record, current_actor = await oidc_client.actor_for_session_hash(mini.get("source_session_id"))
        transport = "mini"
    elif browser_sid:
        mini = None
        source_record, current_actor = await oidc_client.actor_for_session(browser_sid)
        transport = "browser"
    else:
        raise FormIntegrationError("请重新登录后启动患者问卷", error_code="SOURCE_IDENTITY_REQUIRED", status_code=403)
    if (source_record is None or current_actor is None or str(current_actor.get("_id")) != _actor_id(patient_actor)
            or current_actor.get("role") != "patient"):
        raise FormIntegrationError("OneID 登录已失效，请重新登录", error_code="SOURCE_IDENTITY_REQUIRED", status_code=403)
    session_context = {"transport": transport, "mini": mini, "source_record": source_record}

    refs = task.get("remote_refs") or {}
    version = (task.get("reviewed_context") or {}).get("version_ref") or {}
    self_fill = task.get("patient_self") or {}
    remote_payload = {
        "rehabman_task_ref": self_fill["rehabman_task_ref"],
        "patient_actor_subject": binding["subject"],
        "project_id": refs["project_id"], "center_id": refs["center_id"],
        "subject_id": refs["subject_id"], "questionnaire_id": refs["questionnaire_id"],
        "questionnaire_version_ref": {key: version[key] for key in ("form_id", "family_id", "version", "definition_sha256")},
        "allowed_origin": task["allowed_origin"],
        "ttl_seconds": int(task.get("ttl_seconds") or 1800),
    }
    session_id = self_fill.get("source_session_id")
    if not session_id:
        try:
            created = await client.create_patient_self_fill_session(
                remote_payload, idempotency_key=_sha256(self_fill["rehabman_task_ref"]))
        except FormPlatformError as exc:
            raise service._map_remote_error(exc, "创建患者本人填报会话失败") from exc
        session_id = created.get("session_id")
        if (not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id)
                or created.get("questionnaire_version_ref") != remote_payload["questionnaire_version_ref"]
                or created.get("status") not in {"created", "embedded"}):
            raise FormIntegrationError("源端返回的本人填报会话无效", error_code="FORM_PLATFORM_INVALID_RESPONSE", status_code=502)
        # Create may be replayed after a lost response/local commit. Bind the
        # known session before resume's source callback validates the patient.
        try:
            await _bind_patient_session(db, task, patient_actor, binding, session_context, session_id)
        except Exception:
            latest = await _task_for_id(db, task_id)
            if latest.get("patient_self", {}).get("status") not in ACTIVE_TASK_STATES:
                try:
                    await client.revoke_patient_self_fill_session(session_id, {
                        "reason": "rehabman_local_authorization_changed", "rehabman_task_ref": self_fill["rehabman_task_ref"]})
                except FormPlatformError:
                    pass
            raise
    else:
        # A reopened draft requires a newly signed one-use proof. Rebind the live
        # mini/browser session first because the source calls back before signing.
        await _bind_patient_session(db, task, patient_actor, binding, session_context, session_id)

    resume_payload = {
        "rehabman_task_ref": self_fill["rehabman_task_ref"],
        "patient_actor_subject": binding["subject"],
        "questionnaire_version_ref": remote_payload["questionnaire_version_ref"],
        "allowed_origin": task["allowed_origin"],
    }
    resume_key = _sha256(f"resume|{self_fill['rehabman_task_ref']}|{session_id}|{secrets.token_urlsafe(24)}")
    try:
        remote = await client.resume_patient_self_fill_session(session_id, resume_payload,
                                                               idempotency_key=resume_key)
    except FormPlatformError as exc:
        raise service._map_remote_error(exc, "恢复患者本人问卷草稿失败") from exc
    launch_url = remote.get("launch_url")
    launch_token = remote.get("launch_token")
    expires = remote.get("expires_at")
    if (remote.get("session_id") != session_id
            or remote.get("status") not in {"created", "embedded"}
            or not isinstance(launch_url, str) or not isinstance(launch_token, str) or not launch_token
            or remote.get("questionnaire_version_ref") != remote_payload["questionnaire_version_ref"]):
        raise FormIntegrationError("源端返回的恢复信息无效", error_code="FORM_PLATFORM_INVALID_RESPONSE", status_code=502)
    parsed_url, parsed_origin = urlsplit(launch_url), urlsplit(client.source_origin)
    if (parsed_url.scheme != "https" or parsed_url.netloc.lower() != parsed_origin.netloc.lower()
            or not parsed_url.path.startswith("/") or parsed_url.query or parsed_url.fragment
            or parsed_url.username or parsed_url.password):
        raise FormIntegrationError("源端患者填报地址不符合已配置来源", error_code="FORM_PLATFORM_INVALID_RESPONSE", status_code=502)
    try:
        expires_at = datetime.fromisoformat(expires.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError):
        raise FormIntegrationError("源端会话有效期无效", error_code="FORM_PLATFORM_INVALID_RESPONSE", status_code=502) from None
    now = datetime.now(timezone.utc)
    if expires_at <= now or expires_at > now + timedelta(hours=24):
        raise FormIntegrationError("源端会话有效期超出允许范围", error_code="FORM_PLATFORM_INVALID_RESPONSE", status_code=502)

    # Source resume has already checked live patient authority. Recheck locally
    # before publishing a bridge; a concurrent logout/revoke invalidates it.
    latest = await _task_for_id(db, task_id)
    latest_binding = await _verify_live_patient_identity(db, latest, patient_actor, oidc_client.settings.issuer)
    if mini_token:
        fresh_mini, fresh_actor = await oidc_client.actor_for_mini_session(mini_token)
        session_still_live = (fresh_mini is not None and fresh_actor is not None
                              and str(fresh_actor.get("_id")) == _actor_id(patient_actor))
    else:
        fresh_record, fresh_actor = await oidc_client.actor_for_session(browser_sid)
        session_still_live = (fresh_record is not None and fresh_actor is not None
                              and str(fresh_actor.get("_id")) == _actor_id(patient_actor))
    if (latest.get("patient_self", {}).get("status") != "active"
            or latest.get("patient_self", {}).get("source_session_id") != session_id
            or latest.get("patient_self", {}).get("mini_session_id") != (mini["_id"] if mini else None)
            or latest.get("patient_self", {}).get("source_session_hash") != source_record["_id"]
            or latest_binding.get("authorization_revision") != binding.get("authorization_revision")
            or not session_still_live):
        try:
            await client.revoke_patient_self_fill_session(session_id, {
                "reason": "rehabman_local_authorization_changed", "rehabman_task_ref": self_fill["rehabman_task_ref"]})
        except FormPlatformError:
            pass
        raise FormIntegrationError("患者身份或任务在启动期间变化", error_code="SELF_FILL_TASK_CHANGED", status_code=409)
    from app.integrations.identity.service import digest as identity_digest
    ticket = secrets.token_urlsafe(32)
    bridge = {
        "_id": identity_digest(ticket), "task_id": str(task["_id"]),
        "patient_id": task["patient_id"], "patient_actor_id": _actor_id(patient_actor),
        "patient_actor_subject": binding["subject"], "patient_issuer": binding["issuer"],
        "patient_binding_revision": binding["authorization_revision"],
        "mini_session_id": mini["_id"] if mini else None, "source_session_hash": source_record["_id"],
        "identity_transport": transport,
        "source_session_id": session_id, "target": launch_url,
        "launch_token_encrypted": _encrypt(launch_token, settings_obj), "allowed_origin": task["allowed_origin"],
        "expires_at": min(datetime.utcnow() + timedelta(seconds=90), expires_at.replace(tzinfo=None)),
    }
    await db[BRIDGE_COLLECTION].create_index("expires_at", expireAfterSeconds=0, name="patient_self_bridge_expiry")
    await db[BRIDGE_COLLECTION].insert_one(bridge)

    try:
        await run_followup_transaction(db, lambda session: _finalize_launch_bridge(
            db, session, latest, patient_actor, latest_binding, session_context, bridge, expires_at, remote))
    except Exception:
        await db[BRIDGE_COLLECTION].delete_one({"_id": bridge["_id"]})
        raise
    from app.integrations.identity.config import oidc_settings
    base = oidc_settings.public_base_url.rstrip("/")
    return {"taskId": str(task["_id"]), "sessionId": session_id, "status": remote.get("status"),
            "expiresAt": expires_at.isoformat(), "allowedOrigin": task["allowed_origin"],
            "webviewUrl": f"{base}/api/integrations/forms/patient-self/launch-bridge/{ticket}"}


async def revoke_task(db, client, task_id, operator, *, reason: str):
    if operator.role not in PATIENT_ROLES:
        raise FormIntegrationError("仅医生或健康管理师可撤销任务", error_code="SELF_FILL_ASSIGNMENT_ROLE_REQUIRED", status_code=403)
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 500:
        raise FormIntegrationError("撤销原因必填且不超过500字", error_code="INVALID_REVOCATION_REASON", status_code=422)
    task = await _task_for_id(db, task_id)
    if (task.get("operator") or {}).get("user_id") != _actor_id(operator):
        raise FormIntegrationError("只能撤销自己分配的任务", error_code="SELF_FILL_TASK_FORBIDDEN", status_code=403)
    await service._verify_patient_assignment(db, task.get("patient_id"), _actor_id(operator), operator.role)
    current = task.get("patient_self") or {}
    status = current.get("status")
    if status in {"submitted", "confirmed"}:
        raise FormIntegrationError("患者已提交问卷，不能按未提交任务撤销", error_code="SELF_FILL_ALREADY_SUBMITTED", status_code=409)
    if status == "revoked":
        return serialize_patient_task(task, include_staff=True)
    if status not in {"assigned", "active", "revoking", "revoke_failed"}:
        raise FormIntegrationError("任务当前不可撤销", error_code="SELF_FILL_TASK_NOT_ACTIVE", status_code=409)

    # Local denial comes first so the source callback fails closed during any
    # cross-system delay. Failed remote revocation remains retryable.
    if status in {"assigned", "active", "revoke_failed"}:
        result = await db[models.COLLECTION_NAME].update_one({
            "_id": task["_id"], "task_type": TASK_TYPE,
            "mutation_version": task.get("mutation_version", 0),
            "patient_self.status": status,
        }, {"$set": {"patient_self.status": "revoking", "patient_self.revocation_reason": reason.strip(),
                     "patient_self.updated_at": datetime.utcnow()}, "$inc": {"mutation_version": 1}})
        if result.matched_count != 1:
            raise FormIntegrationError("任务已被其他操作修改，请刷新后重试", error_code="SELF_FILL_TASK_CHANGED", status_code=409)
        task["patient_self"]["status"] = "revoking"
        task["patient_self"]["revocation_reason"] = reason.strip()
        task["mutation_version"] = task.get("mutation_version", 0) + 1

    session_id = current.get("source_session_id")
    if session_id:
        try:
            remote = await client.revoke_patient_self_fill_session(session_id, {
                "reason": reason.strip(), "rehabman_task_ref": current["rehabman_task_ref"]})
        except FormPlatformError as exc:
            try:
                latest = await client.get_patient_self_fill_session(session_id)
            except FormPlatformError:
                await db[models.COLLECTION_NAME].update_one({"_id": task["_id"], "task_type": TASK_TYPE,
                    "patient_self.status": "revoking"}, {"$set": {"patient_self.status": "revoke_failed",
                    "patient_self.last_revoke_error": exc.remote_code or type(exc).__name__,
                    "patient_self.updated_at": datetime.utcnow()}, "$inc": {"mutation_version": 1}})
                raise service._map_remote_error(exc, "撤销患者本人填报会话失败，可重试") from exc
            if latest.get("status") == "submitted":
                await db[models.COLLECTION_NAME].update_one({"_id": task["_id"], "task_type": TASK_TYPE,
                    "patient_self.status": "revoking"}, {"$set": {"patient_self.status": "submitted",
                    "patient_self.source_status": "submitted", "patient_self.submitted_at": datetime.utcnow()},
                    "$inc": {"mutation_version": 1}})
                raise FormIntegrationError("患者已提交问卷，不能撤销", error_code="SELF_FILL_ALREADY_SUBMITTED", status_code=409)
            raise service._map_remote_error(exc, "撤销患者本人填报会话失败，可重试") from exc
        if remote.get("status") == "submitted":
            await db[models.COLLECTION_NAME].update_one({"_id": task["_id"], "task_type": TASK_TYPE,
                "patient_self.status": "revoking"}, {"$set": {"patient_self.status": "submitted",
                "patient_self.source_status": "submitted", "patient_self.submitted_at": datetime.utcnow()},
                "$inc": {"mutation_version": 1}})
            raise FormIntegrationError("患者已提交问卷，不能撤销", error_code="SELF_FILL_ALREADY_SUBMITTED", status_code=409)

    await db[models.COLLECTION_NAME].update_one({"_id": task["_id"], "task_type": TASK_TYPE,
        "patient_self.status": "revoking"}, {"$set": {"patient_self.status": "revoked",
        "patient_self.source_token_encrypted": None, "patient_self.updated_at": datetime.utcnow()},
        "$inc": {"mutation_version": 1}})
    task["patient_self"].update(status="revoked", source_token_encrypted=None)
    return serialize_patient_task(task, include_staff=True)


async def consume_launch_bridge(db, ticket, browser_sid, oidc_client, settings_obj):
    from starlette.responses import Response
    from fastapi.responses import RedirectResponse
    from app.integrations.identity.service import OidcFailure
    from app.integrations.identity.service import digest as identity_digest

    def response(text, status):
        return Response(text, status_code=status, media_type="text/html", headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, private", "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff"})

    invalid = response("<!doctype html><meta charset=utf-8><h1>填报入口已失效，请返回患者问卷页面重新打开。</h1>", 410)
    if not isinstance(ticket, str) or len(ticket) > 128:
        return invalid
    now = datetime.utcnow()
    query = {"_id": identity_digest(ticket), "expires_at": {"$gt": now}}
    bridge = await db[BRIDGE_COLLECTION].find_one(query)
    if not bridge:
        return invalid
    if not browser_sid or identity_digest(browser_sid) != bridge.get("source_session_hash"):
        return response("<!doctype html><meta charset=utf-8><h1>请在已登录的患者页面中重新打开问卷。</h1>", 403)
    try:
        source_record, source_actor = await oidc_client.actor_for_session(browser_sid)
        if bridge.get("identity_transport", "mini") == "mini":
            mini = await db.oidc_mini_sessions.find_one({
                "_id": bridge.get("mini_session_id"), "source_session_id": bridge.get("source_session_hash"),
                "actor_id": bridge.get("patient_actor_id"), "expires_at": {"$gt": now}})
        else:
            mini = None
    except Exception:
        return response("<!doctype html><meta charset=utf-8><h1>身份服务暂不可用，请稍后重试。</h1>", 503)
    if (source_record is None or source_actor is None
            or (bridge.get("identity_transport", "mini") == "mini" and mini is None)
            or str(source_actor.get("_id")) != bridge.get("patient_actor_id")
            or source_actor.get("role") != "patient"
            or source_record.get("issuer") != bridge.get("patient_issuer")
            or source_record.get("subject") != bridge.get("patient_actor_subject")):
        return invalid
    task = await db[models.COLLECTION_NAME].find_one({"_id": ObjectId(bridge["task_id"]), "task_type": TASK_TYPE})
    if not task:
        return invalid
    actor = type("PatientActor", (), {"id": bridge["patient_actor_id"], "role": "patient"})()
    try:
        binding = await _verify_live_patient_identity(db, task, actor, bridge["patient_issuer"])
    except FormIntegrationError as exc:
        return response("<!doctype html><meta charset=utf-8><h1>患者授权或问卷关联已变化，请返回患者问卷页面核实。</h1>", 403 if exc.status_code < 500 else 503)
    if (binding.get("subject") != bridge.get("patient_actor_subject")
            or binding.get("authorization_revision") != bridge.get("patient_binding_revision")
            or task.get("patient_self", {}).get("source_session_id") != bridge.get("source_session_id")
            or task.get("patient_self", {}).get("mini_session_id") != bridge.get("mini_session_id")
            or task.get("patient_self", {}).get("source_session_hash") != bridge.get("source_session_hash")
            or task.get("patient_self", {}).get("identity_transport", "mini") != bridge.get("identity_transport", "mini")
            or task.get("patient_self", {}).get("patient_actor_id") != bridge.get("patient_actor_id")
            or task.get("patient_self", {}).get("status") != "active"):
        return invalid
    target = bridge.get("target", "")
    parsed = urlsplit(target)
    try:
        reviewed_form = await db.external_form_bindings.find_one({
            "_id": ObjectId(str((task.get("reviewed_context") or {}).get("form_binding_id")))})
    except Exception:
        reviewed_form = None
    origin = urlsplit((reviewed_form or {}).get("source_origin") or "")
    if (parsed.scheme != "https" or parsed.netloc.lower() != origin.netloc.lower()
            or origin.scheme != "https" or not parsed.path.startswith("/") or parsed.query or parsed.fragment
            or parsed.username or parsed.password):
        return invalid
    try:
        token = _decrypt(bridge["launch_token_encrypted"], settings_obj)
    except Exception:
        return response("<!doctype html><meta charset=utf-8><h1>无法恢复一次性启动凭证，请返回患者问卷页面重新打开。</h1>", 503)

    async def consume(session):
        live_bridge = await db[BRIDGE_COLLECTION].find_one({**query,
            "source_session_hash": identity_digest(browser_sid),
            "mini_session_id": mini["_id"] if mini else None, "patient_actor_id": str(source_actor["_id"]),
            "patient_binding_revision": bridge["patient_binding_revision"]}, session=session)
        if not live_bridge:
            raise FormIntegrationError("患者填报入口已使用或过期", error_code="SELF_FILL_BRIDGE_EXPIRED", status_code=410)
        await _lock_task(db, session, task)
        await _lock_patient_self_mapping(db, session, actor, task.get("patient_id"))
        patient_binding = await db.oidc_principal_bindings.find_one({
            "issuer": bridge["patient_issuer"], "subject": bridge["patient_actor_subject"],
            "actor_id": bridge["patient_actor_id"], "enabled": True, "approved_role": "patient",
            "authorization_revision": bridge["patient_binding_revision"]}, session=session)
        if not patient_binding:
            raise FormIntegrationError("患者 OneID 授权已撤销", error_code="SELF_FILL_TASK_FORBIDDEN", status_code=403)
        await _lock_patient_binding(db, session, patient_binding)
        if mini:
            mini_fence = await db.oidc_mini_sessions.update_one({
                "_id": mini["_id"], "source_session_id": bridge["source_session_hash"],
                "actor_id": bridge["patient_actor_id"], "expires_at": {"$gt": datetime.utcnow()}},
                {"$inc": {"patient_self_fill_use_revision": 1}}, session=session)
        source_fence = await db.oidc_application_sessions.update_one({
            "_id": identity_digest(browser_sid), "issuer": source_record["issuer"],
            "subject": source_record["subject"], "binding_revision": source_record["binding_revision"],
            "expires_at": {"$gt": datetime.utcnow()}},
            {"$inc": {"patient_self_fill_use_revision": 1}}, session=session)
        if (mini and mini_fence.matched_count != 1) or source_fence.matched_count != 1:
            raise FormIntegrationError("患者 OneID 会话已失效", error_code="SELF_FILL_TASK_FORBIDDEN", status_code=403)
        current = await db[models.COLLECTION_NAME].find_one({"_id": task["_id"], "task_type": TASK_TYPE,
            "mutation_version": task.get("mutation_version", 0), "patient_self.status": "active",
            "patient_self.source_session_id": bridge["source_session_id"],
            "patient_self.mini_session_id": mini["_id"] if mini else None,
            "patient_self.source_session_hash": bridge["source_session_hash"]}, session=session)
        if not current:
            raise FormIntegrationError("患者授权或任务已变化", error_code="SELF_FILL_TASK_CHANGED", status_code=409)
        reviewed = current.get("reviewed_context") or {}
        link = await db.external_patient_links.find_one({"_id": ObjectId(str(reviewed.get("patient_link_id")))}, session=session)
        form = await db.external_form_bindings.find_one({"_id": ObjectId(str(reviewed.get("form_binding_id")))}, session=session)
        await service._lock_reviewed_fill_context(db, session, link, form)
        deleted = await db[BRIDGE_COLLECTION].delete_one({"_id": live_bridge["_id"],
            "expires_at": {"$gt": datetime.utcnow()}}, session=session)
        if deleted.deleted_count != 1:
            raise FormIntegrationError("患者填报入口已使用或过期", error_code="SELF_FILL_BRIDGE_EXPIRED", status_code=410)

    try:
        await run_followup_transaction(db, consume)
    except FormIntegrationError as exc:
        status = exc.status_code if exc.status_code in {403, 410} else 409
        return response("<!doctype html><meta charset=utf-8><h1>患者授权或问卷关联已变化，请返回患者问卷页面核实。</h1>", status)
    nonce = secrets.token_urlsafe(18)
    import html
    body = ("<!doctype html><html lang='zh'><head><meta charset='utf-8'><meta name='referrer' content='no-referrer'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'><title>正在打开问卷</title></head>"
            "<body><p>正在打开本人问卷，请稍候。</p>"
            f"<form id=\"launch\" method=\"post\" action=\"{html.escape(target, quote=True)}\">"
            f"<input type=\"hidden\" name=\"token\" value=\"{html.escape(token, quote=True)}\"></form>"
            f"<script nonce='{nonce}'>document.getElementById('launch').submit()</script>"
            "<noscript><button form='launch'>打开问卷</button></noscript></body></html>")
    result = response(body, 200)
    result.headers["Content-Security-Policy"] = f"default-src 'none'; form-action {origin.scheme}://{origin.netloc}; script-src 'nonce-{nonce}'; base-uri 'none'"
    return result


async def callback_authorize(db, payload: Dict[str, Any], supplied_secret: Optional[str]):
    configured = settings.REHAB_SELF_FILL_CALLBACK_SECRET
    expected = configured.get_secret_value() if configured else ""
    if not expected or not supplied_secret or not hmac.compare_digest(expected, supplied_secret):
        raise FormIntegrationError("回调凭据无效", error_code="SELF_FILL_CALLBACK_UNAUTHORIZED", status_code=401)
    if (not isinstance(payload, dict) or set(payload) != {
            "rehabman_task_ref", "patient_actor_subject", "source_session_id", "action", "pinned_version_sha256"}):
        raise FormIntegrationError("回调参数无效", error_code="SELF_FILL_CALLBACK_INVALID", status_code=422)
    task_ref, subject, session_id, action, version_hash = (payload.get("rehabman_task_ref"), payload.get("patient_actor_subject"),
        payload.get("source_session_id"), payload.get("action"), payload.get("pinned_version_sha256"))
    if (not isinstance(task_ref, str) or not task_ref or len(task_ref) > 200
            or not isinstance(subject, str) or not subject or len(subject) > 255
            or not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id)
            or action not in CALLBACK_ACTIONS or not isinstance(version_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", version_hash)):
        raise FormIntegrationError("回调参数无效", error_code="SELF_FILL_CALLBACK_INVALID", status_code=422)
    task = await db[models.COLLECTION_NAME].find_one({
        "task_type": TASK_TYPE, "patient_self.rehabman_task_ref": task_ref,
        "patient_self.source_session_id": session_id,
        "patient_self.status": "active",
        "patient_self.patient_actor_subject": subject,
        "patient_self.pinned_version_sha256": version_hash,
    })
    if not task:
        raise FormIntegrationError("任务或患者授权无效", error_code="SELF_FILL_CALLBACK_FORBIDDEN", status_code=403)
    self_fill = task["patient_self"]
    actor = type("PatientActor", (), {"id": self_fill.get("patient_actor_id"), "role": "patient"})()
    await _verify_live_patient_identity(db, task, actor, self_fill.get("patient_issuer"))
    from app.integrations.identity.service import OidcClient, OidcFailure, OidcUnavailable
    from app.integrations.identity.config import oidc_settings
    # Revalidate the exact bound OneID session on every source-side action.
    transport = self_fill.get("identity_transport", "mini")
    mini = None
    if transport == "mini":
        mini = await db.oidc_mini_sessions.find_one({
            "_id": self_fill.get("mini_session_id"), "source_session_id": self_fill.get("source_session_hash"),
            "actor_id": self_fill.get("patient_actor_id"), "expires_at": {"$gt": datetime.utcnow()}})
        if not mini:
            raise FormIntegrationError("患者小程序会话已失效", error_code="SELF_FILL_CALLBACK_FORBIDDEN", status_code=403)
    elif transport != "browser":
        raise FormIntegrationError("患者 OneID 会话类型无效", error_code="SELF_FILL_CALLBACK_FORBIDDEN", status_code=403)
    source_hash = self_fill.get("source_session_hash")
    try:
        source, source_actor = await OidcClient(db, oidc_settings).actor_for_session_hash(source_hash)
    except OidcUnavailable:
        raise FormIntegrationError("身份服务暂不可用", error_code="SELF_FILL_CALLBACK_UNAVAILABLE", status_code=503) from None
    except OidcFailure:
        raise FormIntegrationError("患者 OneID 会话已失效", error_code="SELF_FILL_CALLBACK_FORBIDDEN", status_code=403) from None
    if (not source or not source_actor or str(source_actor.get("_id")) != self_fill.get("patient_actor_id")
            or source_actor.get("role") != "patient" or source.get("subject") != subject
            or source.get("issuer") != self_fill.get("patient_issuer")):
        raise FormIntegrationError("患者 OneID 会话已失效", error_code="SELF_FILL_CALLBACK_FORBIDDEN", status_code=403)
    await service.require_task_reviewed_context(db, task)
    if version_hash != (task.get("reviewed_context") or {}).get("version_ref", {}).get("definition_sha256"):
        raise FormIntegrationError("问卷版本不再匹配已审核绑定", error_code="SELF_FILL_VERSION_MISMATCH", status_code=409)

    async def fence(session):
        current = await db[models.COLLECTION_NAME].find_one({"_id": task["_id"], "task_type": TASK_TYPE,
            "patient_self.status": "active", "patient_self.source_session_id": session_id,
            "mutation_version": task.get("mutation_version", 0)}, session=session)
        if not current:
            raise FormIntegrationError("任务授权已撤销或变化", error_code="SELF_FILL_CALLBACK_FORBIDDEN", status_code=403)
        await _lock_patient_self_mapping(db, session, actor, task.get("patient_id"))
        patient_binding = await db.oidc_principal_bindings.find_one({
            "issuer": self_fill["patient_issuer"], "subject": subject, "actor_id": self_fill["patient_actor_id"],
            "enabled": True, "approved_role": "patient", "authorization_revision": self_fill["patient_binding_revision"]}, session=session)
        if not patient_binding:
            raise FormIntegrationError("患者 OneID 授权已撤销", error_code="SELF_FILL_CALLBACK_FORBIDDEN", status_code=403)
        await _lock_patient_binding(db, session, patient_binding)
        # Fence the exact Mini (when used) and source-browser session documents
        # in the same transaction so logout/revocation conflicts with authorization.
        if mini:
            mini_fence = await db.oidc_mini_sessions.update_one({
                "_id": mini["_id"], "source_session_id": source_hash,
                "actor_id": self_fill["patient_actor_id"],
                "expires_at": {"$gt": datetime.utcnow()},
            }, {"$inc": {"patient_self_fill_use_revision": 1}}, session=session)
        source_fence = await db.oidc_application_sessions.update_one({
            "_id": source_hash, "issuer": source["issuer"], "subject": subject,
            "binding_revision": source["binding_revision"],
            "expires_at": {"$gt": datetime.utcnow()},
        }, {"$inc": {"patient_self_fill_use_revision": 1}}, session=session)
        if (mini and mini_fence.matched_count != 1) or source_fence.matched_count != 1:
            raise FormIntegrationError("患者 OneID 会话已失效", error_code="SELF_FILL_CALLBACK_FORBIDDEN", status_code=403)
        link = await db.external_patient_links.find_one({"_id": ObjectId(str(current["reviewed_context"]["patient_link_id"]))}, session=session)
        form = await db.external_form_bindings.find_one({"_id": ObjectId(str(current["reviewed_context"]["form_binding_id"]))}, session=session)
        await service._lock_reviewed_fill_context(db, session, link, form)
        update = {"$inc": {"patient_self.authorization_revision": 1}}
        update["$set"] = {"patient_self.last_authorized_action": action,
                           "patient_self.last_authorized_at": datetime.utcnow(),
                           "patient_self.updated_at": datetime.utcnow()}
        result = await db[models.COLLECTION_NAME].update_one({"_id": current["_id"],
            "mutation_version": current.get("mutation_version", 0), "patient_self.status": "active"}, update, session=session)
        if result.matched_count != 1:
            raise FormIntegrationError("任务授权已变化", error_code="SELF_FILL_CALLBACK_FORBIDDEN", status_code=403)

    await run_followup_transaction(db, fence)
    return None
