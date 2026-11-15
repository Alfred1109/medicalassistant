"""集成填报任务服务：患者归属校验、远端会话创建、状态确认。

边界：
- 服务凭证只用于服务端对服务端调用，绝不当作操作者身份；
- 远端查询结果必须与本任务记录的远端引用一致才可确认（防止状态串号）；
- 远端失败如实记录 last_error / 任务 failed，不伪装完成；
- FU01 S4 节点联动：带 followup_visit_id 的任务在确认成功后回写随访节点
  （in_review + effective_response），visit_code 不一致拒绝确认（RESPONSE_MISMATCH）。
"""

from typing import Any, Dict, Optional
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from urllib.parse import urlsplit

from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from pymongo.errors import PyMongoError

from app.core.exceptions import AppBaseException
from app.core.patient_access import (
    PatientAccessError, assigned_patient_query, ensure_patient_access,
    is_domain_state_unavailable,
)
from app.patients.legacy import LegacyPatientRepository
from . import models
from .client import (
    AuthorizationRejected,
    FormPlatformClient,
    FormPlatformError,
    FormPlatformUnavailable,
)

# 本地允许发起填报任务的角色
OPERATOR_ROLES = {"doctor", "health_manager", "admin"}


class FormIntegrationError(AppBaseException):
    """集成填报业务错误（映射为 4xx/5xx 响应）。"""

    def __init__(self, message: str, error_code: str = "FORM_INTEGRATION_ERROR",
                 status_code: int = 400,
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=status_code,
                         error_code=error_code, details=details)


def require_fill_enabled() -> None:
    """Keep filling separate from read-only directory credentials.

    Explicit opt-in is required while the bilateral launch/recovery contract is
    being completed. Existing task inspection, confirmation and cancellation
    remain available so prior tasks can be reconciled or revoked.
    """
    value = os.environ.get("FORM_PLATFORM_FILL_ENABLED", "false").strip().lower()
    if value not in {"true", "false"}:
        raise FormIntegrationError(
            "表单填报开关配置无效", error_code="FORM_FILL_CONFIGURATION_INVALID",
            status_code=503)
    if value != "true":
        raise FormIntegrationError(
            "表单填报尚未启用", error_code="FORM_FILL_DISABLED", status_code=503)


def _map_remote_error(exc: FormPlatformError, prefix: str) -> FormIntegrationError:
    if isinstance(exc, AuthorizationRejected):
        return FormIntegrationError(f"{prefix}：远端拒绝了集成凭证或授权范围",
                                    error_code="FORM_PLATFORM_AUTH_REJECTED",
                                    status_code=502, details={"remote_code": exc.remote_code})
    if isinstance(exc, FormPlatformUnavailable):
        return FormIntegrationError(f"{prefix}：表单平台不可达",
                                    error_code="FORM_PLATFORM_UNAVAILABLE",
                                    status_code=502)
    status_code = exc.status_code if exc.status_code and exc.status_code < 500 else 502
    return FormIntegrationError(f"{prefix}：{exc}",
                                error_code="FORM_PLATFORM_REJECTED",
                                status_code=status_code, details={"remote_code": exc.remote_code})


# ---- T44：源端创建幂等与对账对齐（源端 0d28031 / T36 语义） ----
#
# 任务引用（ma_task_ref）是康复端任务侧的唯一引用：
# - 源端按 (client, ma_task_ref) 维护"进行中会话唯一"（部分唯一索引兜底），
#   重复创建 409 task_ref_conflict 并返回既有会话指针；
# - 康复端不加本地唯一索引：历史任务允许同引用多轮（会话终结后新一轮），
#   且"进行中唯一"由源端索引权威裁决并经 409 指针回传，本地据此把重复
#   创建收敛为既有任务/收养孤儿会话，效果上保证进行中引用不重复。

def _resolve_task_ref(payload: Dict[str, Any], *, operator_id: str, patient_id: str,
                      refs: Dict[str, Any], binding: Dict[str, Any],
                      followup_visit_id: Optional[str],
                      visit_code: Optional[str]) -> str:
    """任务引用解析：显式引用透传，缺省时由任务身份确定性派生。

    - 显式引用：去首尾空白后 1-160 字符（与源端 by-task-ref 对账端点上限
      一致，保证引用始终可对账）；非字符串/为空/超限 → 422；
    - 派生引用：绑定操作者、患者、远端资源、审核绑定与访视上下文（不含
      ttl_seconds / allowed_origin / visit_name 等会话参数）——同一请求体
      重试得到同一引用，重试改动会话参数不会更换引用，冲突在对账时显式
      可见（对齐清单 2 的 payload 确定性重建要求）。
    """
    raw = payload.get("ma_task_ref")
    if raw is not None:
        if not isinstance(raw, str):
            raise FormIntegrationError("ma_task_ref 必须为字符串",
                                       error_code="INVALID_TASK_REF", status_code=422)
        stripped = raw.strip()
        if not stripped or len(stripped) > 160:
            raise FormIntegrationError("ma_task_ref 必须为 1 到 160 个字符",
                                       error_code="INVALID_TASK_REF", status_code=422)
        return stripped
    canonical = json.dumps({
        "operator": operator_id, "patient": patient_id, "refs": refs,
        "binding": str(binding["_id"]), "purpose": binding.get("purpose"),
        "visit": followup_visit_id, "visit_code": visit_code,
    }, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return "auto-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def _session_idempotency_key(task: "models.FollowUpFillTask") -> str:
    """创建幂等键（对齐清单 1）：任务引用 + 本地任务 _id 复合哈希。

    同一次本地创建尝试内稳定（远端调用失败重试同键同体），跨尝试不复用：
    同一引用的旧会话终结后的新一轮创建（对齐清单 5）不会被旧幂等记录
    重放为已终结会话。键长 64 字符，处于源端 1-128 上限内。
    """
    material = f"fill-session|{task.doc.get('ma_task_ref')}|{task.doc['_id']}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _validated_adopted_session(body: Any, task: "models.FollowUpFillTask") -> Dict[str, Any]:
    """收养/找回的远端会话核验：引用一致、会话仍进行中、操作人有效。

    不假设 409 指针指向可复活会话（对齐清单 5）：已 submitted/cancelled/
    expired 的会话一律拒绝收养，不得绑定为新任务的活动会话。
    """
    mismatch = FormIntegrationError("找回的远端会话与当前任务引用不一致",
                                    error_code="TASK_REF_SESSION_MISMATCH", status_code=409)
    if not isinstance(body, dict):
        raise mismatch
    refs = task.doc.get("remote_refs") or {}
    if any(body.get(key) != refs.get(key)
           for key in ("project_id", "center_id", "subject_id", "questionnaire_id")):
        raise mismatch
    session_uuid = body.get("session_uuid")
    if not isinstance(session_uuid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", session_uuid):
        raise mismatch
    if body.get("status") not in ("created", "embedded"):
        raise FormIntegrationError("任务引用下的远端会话已结束，不能收养为当前任务的会话",
                                   error_code="TASK_REF_SESSION_NOT_LIVE", status_code=409)
    if type(body.get("operator_user_id")) is not int or body["operator_user_id"] <= 0:
        raise FormIntegrationError("表单平台未返回有效操作人",
                                   error_code="FORM_PLATFORM_INVALID_RESPONSE", status_code=502)
    return body


async def _resolve_task_ref_conflict(db: AsyncIOMotorDatabase, client: FormPlatformClient,
                                     task: "models.FollowUpFillTask", conflict: FormPlatformError,
                                     *, patient_id: str, operator_id: str):
    """对齐清单 3：409 task_ref_conflict 的指针找回，不报错失败。

    - 本地已有持有该会话的进行中任务且属于同一操作者/患者 → 直接返回该
      任务（引用重试收敛，不再创建本地任务）；
    - 本地无归属（创建 201 丢失的孤儿会话）→ 核验远端会话后收养为当前
      任务的会话，走正常持久化流程；
    - 指针指向失败任务保留的会话 → 如实上报需核查（禁止重新发起）；
    - 跨操作者/跨患者共享引用 → 拒绝，不泄露他人任务。
    """
    details = getattr(conflict, "details", None) or {}
    existing_uuid = details.get("existing_session_uuid")
    if not isinstance(existing_uuid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", existing_uuid):
        raise FormIntegrationError("任务引用冲突缺少可用的既有会话指针",
                                   error_code="TASK_REF_POINTER_INVALID", status_code=409)
    live_owner = None
    failed_owner = None
    query = {"$or": [{"session.session_uuid": existing_uuid},
                     {"fill_sessions.session_uuid": existing_uuid}]}
    async for doc in db[models.COLLECTION_NAME].find(query):
        if doc.get("status") in (models.TASK_STATUS_SESSION_CREATED, models.TASK_STATUS_WAITING_FILL):
            live_owner = live_owner or doc
        elif doc.get("status") == models.TASK_STATUS_FAILED:
            failed_owner = failed_owner or doc
    if failed_owner is not None:
        raise FormIntegrationError("该任务引用指向失败任务保留的远端会话，需按任务标识核查",
                                   error_code="FILL_TASK_RECOVERY_UNCERTAIN", status_code=503,
                                   details={"task_id": str(failed_owner["_id"]),
                                            "session_uuid": existing_uuid})
    if live_owner is not None:
        if ((live_owner.get("operator") or {}).get("user_id") == operator_id
                and live_owner.get("patient_id") == patient_id):
            return None, live_owner
        raise FormIntegrationError("该 ma_task_ref 已被其他填报任务占用",
                                   error_code="TASK_REF_CONFLICT", status_code=409,
                                   details={"ma_task_ref": task.doc.get("ma_task_ref")})
    session_body = await client.get_fill_session(existing_uuid)
    return _validated_adopted_session(session_body, task), None


async def _recover_session_by_task_ref(client: FormPlatformClient,
                                       task: "models.FollowUpFillTask") -> Optional[Dict[str, Any]]:
    """对账端点找回（对齐清单 4）：创建超时/201 丢失时按引用查询。

    404 session_not_found 表示超时发生在远端创建之前（无会话），返回 None
    让调用方如实抛 FORM_PLATFORM_UNAVAILABLE，不落本地任务；对账调用自身
    失败同样返回 None 保留原始不可达错误。
    """
    ref = task.doc.get("ma_task_ref")
    if not ref:
        return None
    try:
        body = await client.get_fill_session_by_task_ref(ref)
    except FormPlatformError:
        return None
    latest = body.get("latest") if isinstance(body, dict) else None
    return _validated_adopted_session(latest, task)


async def _create_remote_session(db: AsyncIOMotorDatabase, client: FormPlatformClient,
                                 task: "models.FollowUpFillTask", remote_payload: Dict[str, Any],
                                 *, source_access_token: str, patient_id: str, operator_id: str):
    """远端会话创建与失败恢复（对齐清单 1-4、6）。

    重试策略（源端失败响应不消费幂等键，同键重试安全）：
    - 表单平台不可达（超时/断连）→ 同键同体重试一次；两次仍不可达时按
      ma_task_ref 对账找回可能已创建的会话，对账也无果则如实抛
      FORM_PLATFORM_UNAVAILABLE，不落本地任务；
    - 409 task_ref_conflict → 指针找回（见 _resolve_task_ref_conflict）；
    - 409 idempotency_conflict / 其余 4xx → 不重试直接失败：幂等键与请求体
      指纹绑定，重试必须保持 payload 确定性重建（含 ttl_seconds、
      allowed_origin），改体重试只会得到键冲突。

    返回 (session_body, existing_task)：existing_task 非空表示命中本地既有
    任务（同操作者引用重试），调用方直接返回该任务、不再创建本地任务。
    """
    idempotency_key = _session_idempotency_key(task)
    unavailable: Optional[FormPlatformUnavailable] = None
    for _attempt in (1, 2):
        try:
            body = await client.create_fill_session(
                remote_payload, source_access_token=source_access_token,
                idempotency_key=idempotency_key)
            return body, None
        except FormPlatformUnavailable as exc:
            unavailable = unavailable or exc
        except FormPlatformError as exc:
            if exc.remote_code == "task_ref_conflict":
                return await _resolve_task_ref_conflict(
                    db, client, task, exc, patient_id=patient_id, operator_id=operator_id)
            raise
    recovered = await _recover_session_by_task_ref(client, task)
    if recovered is not None:
        return recovered, None
    assert unavailable is not None
    raise unavailable


async def _verify_patient_assignment(db: AsyncIOMotorDatabase, patient_id: str,
                                     operator_id: str, operator_role: str) -> None:
    """默认拒绝：操作者必须是患者档案中的主治医生（或管理员）。

    校验逻辑复用 app.core.patient_access.ensure_patient_access（AUTH01 共享实现）；
    此处仅把 PatientAccessError 翻译回集成侧错误类型，保持对外行为不变。

    域状态不可用（canonical 二次状态读取失败，503
    PATIENT_DOMAIN_STATE_UNAVAILABLE）必须透传，不得与归属失败 403
    混同（对抗审查缺陷 2 的集成侧第四处）。
    """
    try:
        await ensure_patient_access(db, patient_id, operator_id, operator_role)
    except PatientAccessError as exc:
        if is_domain_state_unavailable(exc):
            raise FormIntegrationError("患者域状态不可用，已拒绝访问",
                                       error_code=exc.error_code,
                                       status_code=exc.status_code) from exc
        if exc.error_code == "PATIENT_NOT_FOUND":
            raise FormIntegrationError("患者不存在",
                                       error_code="PATIENT_NOT_FOUND",
                                       status_code=404) from exc
        raise FormIntegrationError(
            "当前用户不是该患者的主治医生，不能为其发起表单填报任务",
            error_code="PATIENT_NOT_ASSIGNED", status_code=403) from exc


# 随访节点终态（confirm 回写前置校验：终态节点不接受答卷回写）
FOLLOWUP_VISIT_TERMINAL_STATUSES = {"completed", "canceled", "cancelled"}


# legacy-shape: 存量形态，不随域切换删除
def _task_version_filter(doc):
    return {"_id": doc["_id"], "mutation_version": doc.get("mutation_version", 0)
            if doc.get("mutation_version", 0) else {"$in": [0, None]}}


def _visit_is_writable(visit):
    if visit.get("deleted") or visit.get("status") in FOLLOWUP_VISIT_TERMINAL_STATUSES:
        raise FormIntegrationError("随访节点已关闭，不能关联或确认填报任务",
                                   error_code="FOLLOWUP_VISIT_TERMINAL", status_code=409)


async def _write_task(db, snapshot, fields, *, session=None):
    result = await db[models.COLLECTION_NAME].update_one(
        _task_version_filter(snapshot),
        {"$set": fields, "$inc": {"mutation_version": 1}}, **({"session": session} if session else {}))
    if result.matched_count != 1:
        raise FormIntegrationError("填报任务已被其他请求修改，请重新获取状态",
                                   error_code="TASK_CONFLICT", status_code=409)


async def _require_transaction_topology(db):
    """创建远端会话前拒绝不支持事务的部署，后续写入仍由事务保障。"""
    try:
        topology = await db.command("hello")
    except PyMongoError as exc:
        raise FormIntegrationError("无法确认数据库事务能力，未创建远端会话",
                                   error_code="FOLLOWUP_TRANSACTION_UNAVAILABLE", status_code=503) from exc
    if (not (topology.get("setName") or topology.get("msg") == "isdbgrid") or
            topology.get("logicalSessionTimeoutMinutes") is None):
        raise FormIntegrationError("填报任务创建需要支持事务的MongoDB副本集或分片集群",
                                   error_code="FOLLOWUP_TRANSACTION_UNAVAILABLE", status_code=503)


async def _recover_failed_creation(db, client, task, original_error):
    """跨系统创建失败：先核实本地提交，再撤销远端；审计不包含明文令牌。"""
    if getattr(original_error, "details", {}).get("commit_result_unknown"):
        recovery = {"_id": ObjectId(), "task_id": task.doc["_id"],
                    "session_uuid": models.active_session(task.doc).get("session_uuid"),
                    "followup_visit_id": task.doc.get("followup_visit_id"),
                    "operator": deepcopy(task.doc.get("operator")),
                    "status": "pending_commit_verification", "created_at": models.utcnow()}
        try:
            await db["integration_recovery_events"].insert_one(recovery)
        except Exception as exc:
            raise FormIntegrationError("事务提交未知且恢复审计未写入，需按任务和会话标识核查",
                                       error_code="FILL_TASK_RECOVERY_UNCERTAIN", status_code=503,
                                       details={"task_id": task.id,
                                                "session_uuid": recovery["session_uuid"]}) from exc
        raise FormIntegrationError("事务提交结果未知，远端会话已保留等待核查，禁止重新创建任务",
                                   error_code="FILL_TASK_COMMIT_UNCERTAIN", status_code=503,
                                   details={"task_id": task.id,
                                            "recovery_id": str(recovery["_id"])}) from original_error
    try:
        persisted = await db[models.COLLECTION_NAME].find_one({"_id": task.doc["_id"]})
    except Exception as exc:
        raise FormIntegrationError("本地事务提交状态无法核实，需按任务标识核查，禁止重新发起",
                                   error_code="FILL_TASK_COMMIT_UNCERTAIN", status_code=503,
                                   details={"task_id": task.id}) from exc
    if persisted and persisted.get("status") != models.TASK_STATUS_FAILED:
        if (models.active_session(persisted).get("session_uuid") ==
                models.active_session(task.doc).get("session_uuid") and
                persisted.get("followup_visit_id") == task.doc.get("followup_visit_id")):
            return persisted
        raise FormIntegrationError("本地任务标识与远端会话不一致，需核查",
                                   error_code="FILL_TASK_RECOVERY_UNCERTAIN", status_code=503,
                                   details={"task_id": task.id})
    session_uuid = models.active_session(task.doc).get("session_uuid")
    cleanup_required = False
    try:
        await client.cancel_fill_session(session_uuid)
    except FormPlatformError:
        cleanup_required = True
    audit = deepcopy(task.doc)
    audit["status"] = models.TASK_STATUS_FAILED
    audit["last_error"] = "本地随访绑定事务失败"
    audit["cleanup_required"] = cleanup_required
    audit["updated_at"] = models.utcnow()
    try:
        await db[models.COLLECTION_NAME].insert_one(audit)
    except Exception as exc:
        raise FormIntegrationError("本地创建失败且恢复审计未写入，需核查远端会话",
                                   error_code="FILL_TASK_RECOVERY_UNCERTAIN", status_code=503,
                                   details={"task_id": task.id, "session_uuid": session_uuid,
                                            "cleanup_required": cleanup_required}) from exc
    if cleanup_required:
        raise FormIntegrationError("本地创建失败，远端会话撤销待处理",
                                   error_code="FILL_TASK_CLEANUP_REQUIRED", status_code=503,
                                   details={"task_id": task.id}) from original_error
    raise original_error


async def _load_followup_visit(db: AsyncIOMotorDatabase,
                               followup_visit_id: str) -> Dict[str, Any]:
    """加载 followup_visit_id 指向的随访节点（FU01 S4 节点联动）。

    惰性导入业务模型，保持 forms 集成模块加载期零业务依赖（同上方
    _verify_patient_access 的处理方式）。
    """
    from bson import ObjectId, errors as bson_errors
    from app.models.health_record import FollowUpRecord

    try:
        query_id = ObjectId(followup_visit_id)
    except (bson_errors.InvalidId, TypeError):
        raise FormIntegrationError("followup_visit_id 格式无效",
                                   error_code="INVALID_FOLLOWUP_VISIT", status_code=422)
    visit = await db[FollowUpRecord.collection_name].find_one({"_id": query_id})
    if not visit:
        raise FormIntegrationError("关联的随访节点不存在",
                                   error_code="FOLLOWUP_VISIT_NOT_FOUND", status_code=404)
    return visit


def _extract_remote_refs(payload: Dict[str, Any]) -> Dict[str, Any]:
    refs = {
        "project_id": payload.get("remote_project_id"),
        "center_id": payload.get("remote_center_id"),
        "subject_id": payload.get("remote_subject_id"),
        "questionnaire_id": payload.get("remote_questionnaire_id"),
    }
    missing = [key for key, value in refs.items() if type(value) is not int or value <= 0]
    if missing:
        raise FormIntegrationError(
            "远端引用字段必须为整数：" + ", ".join(missing),
            error_code="INVALID_REMOTE_REFS", status_code=422)
    return refs


async def _reviewed_fill_context(db, client, patient_id, refs, payload):
    """Resolve selectors against reviewed records and current source facts."""
    from fastapi import HTTPException
    from . import catalog_service

    if (not isinstance(refs, dict) or any(type(refs.get(k)) is not int or refs[k] <= 0 for k in
            ("project_id", "center_id", "subject_id", "questionnaire_id"))):
        raise FormIntegrationError("远端选择器无效", error_code="INVALID_REMOTE_REFS", status_code=422)

    binding_id, purpose = payload.get("form_binding_id"), payload.get("form_purpose")
    if (not isinstance(binding_id, str) or not ObjectId.is_valid(binding_id) or not isinstance(purpose, str)
            or purpose not in {"initial_assessment", "followup", "reassessment"}):
        raise FormIntegrationError("请选择已确认的表单用途绑定", error_code="REVIEWED_FORM_REQUIRED", status_code=422)
    link = await db.external_patient_links.find_one({"local_patient_id": patient_id, "status": "verified"})
    binding = await db.external_form_bindings.find_one({"_id": ObjectId(binding_id), "status": "active"})
    if not link or not binding:
        raise FormIntegrationError("患者关联或表单绑定未核实或已撤销", error_code="REVIEWED_CONTEXT_REQUIRED", status_code=409)
    try:
        origin = client.source_origin
        parsed = urlsplit(origin)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username
                or parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise ValueError("invalid origin")
    except (AttributeError, ValueError, TypeError, FormPlatformError):
        raise FormIntegrationError("来源配置不可用", error_code="SOURCE_CONFIGURATION_INVALID", status_code=503) from None
    if (link.get("source_origin") != origin or binding.get("source_origin") != origin
            or binding.get("purpose") != purpose):
        raise FormIntegrationError("来源或表单用途与审核记录不一致", error_code="REVIEWED_CONTEXT_MISMATCH", status_code=409)
    for reviewed in (link, binding):
        if (not isinstance(reviewed.get("verified_by"), str) or not reviewed["verified_by"].strip()
                or not isinstance(reviewed.get("verified_at"), datetime)
                or not isinstance(reviewed.get("evidence_reference"), str) or not reviewed["evidence_reference"].strip()):
            raise FormIntegrationError("审核记录缺少核实证据", error_code="REVIEWED_CONTEXT_REQUIRED", status_code=409)
    contexts = link.get("references", [link.get("reference")])
    if (not isinstance(contexts, list) or not contexts or not isinstance(binding.get("version_ref"), dict)
            or any(type(binding.get(k)) is not int or binding[k] <= 0 for k in ("project_id", "form_id", "version"))):
        raise FormIntegrationError("审核记录结构无效", error_code="REVIEWED_CONTEXT_INVALID", status_code=409)
    selected = [r for r in contexts if isinstance(r, dict) and all(
        r.get(k) == refs[k] for k in ("project_id", "center_id", "subject_id"))]
    if len(selected) != 1 or binding.get("project_id") != refs["project_id"] or binding.get("form_id") != refs["questionnaire_id"]:
        raise FormIntegrationError("远端选择不属于已审核的患者和表单", error_code="REVIEWED_CONTEXT_MISMATCH", status_code=409)
    reference = selected[0]
    if (any(type(reference.get(k)) is not int or reference[k] <= 0 for k in
            ("project_id", "center_id", "subject_id", "patient_id", "patient_archive_id"))
            or reference.get("source") not in ({"system": "form-platform-11344", "environment": "pilot"},
                                               {"system": "form-platform-11344", "environment": "production"})
            or (reference["source"]["environment"] == "production" and parsed.scheme != "https")):
        raise FormIntegrationError("审核来源引用无效", error_code="REVIEWED_CONTEXT_INVALID", status_code=409)
    try:
        current_patient = await catalog_service.patient_reference(client, reference["project_id"], reference["center_id"], reference["subject_id"])
        current_form = await catalog_service.form_version(client, binding["project_id"], binding["form_id"], version=binding["version"])
    except HTTPException as exc:
        raise FormIntegrationError("来源患者或表单当前状态无法核实", error_code="SOURCE_CONTEXT_UNAVAILABLE", status_code=exc.status_code) from exc
    if (current_patient != reference or current_form["source"] != reference.get("source")
            or binding.get("source") != reference.get("source")
            or current_form["version"] != binding.get("version_ref")):
        raise FormIntegrationError("来源患者或表单版本已变化，请重新核实", error_code="SOURCE_CONTEXT_CHANGED", status_code=409)
    resolved = {k: reference[k] for k in ("project_id", "center_id", "subject_id")}
    resolved.update(questionnaire_id=binding["form_id"])
    return resolved, link, binding, reference


async def _lock_reviewed_fill_context(db, session, link, binding):
    # Snapshot reads alone do not conflict with concurrent authorization removal.
    for collection, snapshot, fields in (
        (db.external_patient_links, link, ("local_patient_id", "status", "source_origin", "reference", "references", "verified_at", "verified_by", "evidence_reference", "source_key")),
        (db.external_form_bindings, binding, ("status", "source_origin", "project_id", "form_id", "version", "version_ref", "purpose", "verified_at", "verified_by", "evidence_reference", "source", "binding_key")),
    ):
        query = {"_id": snapshot["_id"], **{k: snapshot.get(k) for k in fields}}
        result = await collection.update_one(query, {"$inc": {"fill_use_revision": 1}}, session=session)
        if result.matched_count != 1:
            raise FormIntegrationError("审核关联已变化，未创建填报任务", error_code="REVIEWED_CONTEXT_CHANGED", status_code=409)


async def create_fill_task(db: AsyncIOMotorDatabase, client: FormPlatformClient,
                           operator: Any, payload: Dict[str, Any], *, delegation=None) -> Dict[str, Any]:
    """校验患者和审核上下文，创建并保存远端会话引用。"""
    require_fill_enabled()
    from app.integrations.identity.service import FillDelegation, OidcFailure, OidcUnavailable
    if "remote_operator_user_id" in payload:
        raise FormIntegrationError("填报操作人由统一登录身份确定", error_code="OPERATOR_OVERRIDE_FORBIDDEN", status_code=422)
    try:
        source_origin = client.source_origin
    except FormPlatformError:
        raise FormIntegrationError("来源配置不可用", error_code="SOURCE_CONFIGURATION_INVALID", status_code=503) from None
    if (not isinstance(delegation, FillDelegation) or delegation.actor_id != str(operator.id)
            or delegation.role != operator.role or delegation.client.settings.issuer != source_origin):
        raise FormIntegrationError("缺少有效的来源身份委托", error_code="SOURCE_IDENTITY_REQUIRED", status_code=403)
    try:
        await delegation.revalidate()
    except OidcUnavailable:
        raise FormIntegrationError("身份源暂不可用", error_code="SOURCE_IDENTITY_UNAVAILABLE", status_code=503) from None
    except OidcFailure:
        raise FormIntegrationError("来源身份已失效", error_code="SOURCE_IDENTITY_REQUIRED", status_code=403) from None
    operator_id = str(operator.id)
    operator_role = operator.role
    if operator_role not in OPERATOR_ROLES:
        raise FormIntegrationError("当前角色不能发起表单填报任务",
                                   error_code="OPERATOR_ROLE_NOT_ALLOWED", status_code=403)

    patient_id = payload.get("patient_id")
    if not patient_id or not isinstance(patient_id, str):
        raise FormIntegrationError("patient_id 必填", error_code="INVALID_PATIENT",
                                   status_code=422)
    await _verify_patient_assignment(db, patient_id, operator_id, operator_role)

    # FU01 S4 创建联动（最小）：带 followup_visit_id 时校验节点存在且归属一致；
    # 操作者对该患者的归属权限已由上方 ensure_patient_access 覆盖（节点→patient_id 链路）
    followup_visit_id = payload.get("followup_visit_id")
    followup_visit: Optional[Dict[str, Any]] = None
    if followup_visit_id:
        followup_visit = await _load_followup_visit(db, followup_visit_id)
        _visit_is_writable(followup_visit)
        if str(followup_visit.get("patient_id")) != patient_id:
            raise FormIntegrationError(
                "随访节点与任务患者不一致", error_code="FOLLOWUP_VISIT_PATIENT_MISMATCH",
                status_code=409,
                details={"node_patient_id": str(followup_visit.get("patient_id")),
                         "task_patient_id": patient_id})

    refs = _extract_remote_refs(payload)
    refs, reviewed_link, reviewed_binding, reviewed_reference = await _reviewed_fill_context(
        db, client, patient_id, refs, payload)
    allowed_origin = (payload.get("allowed_origin") or "").strip().rstrip("/")
    if not allowed_origin:
        raise FormIntegrationError("allowed_origin 必填（发起嵌入页面的来源）",
                                   error_code="INVALID_ORIGIN", status_code=422)

    # visit_code 缺省时取节点 visit_code（设计稿 §3.3 第 1 步：visit_code=节点.visit_code）
    visit_code = payload.get("visit_code")
    if not visit_code and followup_visit:
        visit_code = followup_visit.get("visit_code")

    # T44 对齐清单 1/3/7：ma_task_ref 是康复端任务侧唯一引用；缺省时由任务
    # 身份确定性派生，使"同体重试找回"与"by-task-ref 对账"对不携带引用的
    # 调用方同样成立。
    ma_task_ref = _resolve_task_ref(
        payload, operator_id=operator_id, patient_id=patient_id, refs=refs,
        binding=reviewed_binding,
        followup_visit_id=str(followup_visit_id) if followup_visit_id else None,
        visit_code=visit_code)

    task = models.FollowUpFillTask.new_task(
        patient_id=patient_id,
        operator_id=operator_id,
        operator_role=operator_role,
        remote_refs=refs,
        allowed_origin=allowed_origin,
        ma_task_ref=ma_task_ref,
        visit_code=visit_code,
        visit_name=payload.get("visit_name"),
        ttl_seconds=payload.get("ttl_seconds"),
        followup_visit_id=str(followup_visit_id) if followup_visit_id else None,
    )
    task.doc["_id"] = ObjectId()
    task.doc["mutation_version"] = 0
    task.doc["reviewed_context"] = {"patient_link_id": reviewed_link["_id"],
        "form_binding_id": reviewed_binding["_id"], "reference": deepcopy(reviewed_reference),
        "version_ref": deepcopy(reviewed_binding["version_ref"]), "purpose": reviewed_binding["purpose"]}

    remote_payload = {
        "project_id": refs["project_id"],
        "center_id": refs["center_id"],
        "subject_id": refs["subject_id"],
        "questionnaire_id": refs["questionnaire_id"],
        "allowed_origin": allowed_origin,
        "questionnaire_version_ref": {
            key: reviewed_binding["version_ref"][key]
            for key in ("form_id", "family_id", "version", "definition_sha256")
        },
    }
    if visit_code:
        remote_payload["visit_code"] = visit_code
    if payload.get("visit_name"):
        remote_payload["visit_name"] = payload["visit_name"]
    remote_payload["ma_task_ref"] = ma_task_ref
    if payload.get("ttl_seconds") is not None:
        remote_payload["ttl_seconds"] = payload["ttl_seconds"]

    await _require_transaction_topology(db)
    try:
        session_body, existing_task = await _create_remote_session(
            db, client, task, remote_payload, source_access_token=delegation.token,
            patient_id=patient_id, operator_id=operator_id)
    except FormPlatformError as exc:
        mapped = _map_remote_error(exc, "创建填报会话失败")
        raise mapped from exc
    if existing_task is not None:
        # 对齐清单 3：同引用重试命中本地既有进行中任务 → 找回而非报错失败
        return models.serialize_task(existing_task)

    task.record_remote_session(session_body)
    if (not isinstance(task.doc["session"]["session_uuid"], str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", task.doc["session"]["session_uuid"])):
        # 远端响应缺关键材料：不落一条看似成功的任务
        invalid_response = FormIntegrationError("表单平台未返回有效会话引用",
                                                error_code="FORM_PLATFORM_INVALID_RESPONSE", status_code=502)
        if task.doc["session"]["session_uuid"]:
            await _recover_failed_creation(db, client, task, invalid_response)
        raise invalid_response

    actual_operator = session_body.get("operator_user_id")
    if type(actual_operator) is not int or actual_operator <= 0:
        await _recover_failed_creation(db, client, task, FormIntegrationError(
            "源端未返回有效操作人", error_code="FORM_PLATFORM_INVALID_RESPONSE", status_code=502))
    task.doc["operator"]["remote_user_id"] = actual_operator
    task.doc["remote_refs"]["remote_operator_user_id"] = actual_operator
    task.doc["identity_context"] = {"issuer": delegation.record["issuer"], "subject": delegation.record["subject"],
        "session_hash": delegation.record["_id"], "binding_revision": delegation.record["binding_revision"]}
    try:
        await delegation.revalidate()
    except (OidcFailure, OidcUnavailable):
        await _recover_failed_creation(db, client, task, FormIntegrationError(
            "来源身份在创建期间失效", error_code="SOURCE_IDENTITY_CHANGED", status_code=403))

    from app.db.transactions import run_followup_transaction
    from app.core.followup_semantics import followup_conflict, followup_version_filter

    async def persist_task(session):
        try:
            await delegation.lock(db, session)
        except OidcFailure:
            raise FormIntegrationError("来源身份在提交期间失效", error_code="SOURCE_IDENTITY_CHANGED", status_code=403) from None
        await _lock_reviewed_fill_context(db, session, reviewed_link, reviewed_binding)
        if followup_visit_id:
            from app.models.health_record import FollowUpRecord
            visit = await db[FollowUpRecord.collection_name].find_one(
                {"_id": ObjectId(followup_visit_id)}, session=session)
            if not visit or str(visit.get("patient_id")) != patient_id:
                raise followup_conflict("随访节点已改变，不能绑定填报任务")
            _visit_is_writable(visit)
            if visit.get("visit_code") != followup_visit.get("visit_code"):
                raise followup_conflict("随访访视标识已改变")
            result = await db[FollowUpRecord.collection_name].update_one(
                followup_version_filter(visit),
                {"$addToSet": {"fill_task_ids": task.doc["_id"]},
                 "$set": {"updated_at": models.utcnow()}, "$inc": {"mutation_version": 1}},
                session=session)
            if result.matched_count != 1:
                raise followup_conflict("随访节点已被其他请求修改")
        await db[models.COLLECTION_NAME].insert_one(deepcopy(task.doc), session=session)

    try:
        await run_followup_transaction(db, persist_task)
    except Exception as exc:
        recovered = await _recover_failed_creation(db, client, task, exc)
        task = models.FollowUpFillTask(recovered)
    return models.serialize_task(task.doc)


async def get_fill_task(db: AsyncIOMotorDatabase, task_id: str,
                        operator: Any) -> Dict[str, Any]:
    from bson import ObjectId, errors as bson_errors

    if operator.role not in OPERATOR_ROLES:
        raise FormIntegrationError("当前角色不能访问医护填报任务",
                                   error_code="OPERATOR_ROLE_NOT_ALLOWED", status_code=403)
    try:
        query_id = ObjectId(task_id)
    except (bson_errors.InvalidId, TypeError):
        raise FormIntegrationError("任务不存在", error_code="TASK_NOT_FOUND", status_code=404)

    doc = await db[models.COLLECTION_NAME].find_one({"_id": query_id})
    if not doc:
        raise FormIntegrationError("任务不存在", error_code="TASK_NOT_FOUND", status_code=404)
    operator_id = str(operator.id)
    # 只允许任务发起人或管理员查看
    if (doc.get("operator") or {}).get("user_id") != operator_id and operator.role != "admin":
        raise FormIntegrationError("无权查看该填报任务", error_code="TASK_FORBIDDEN",
                                   status_code=403)
    await _verify_patient_assignment(db, doc.get("patient_id"), operator_id, operator.role)
    return doc


async def require_task_reviewed_context(db, task, *, session=None):
    """Authorize a new action using the exact reviewed records used at creation."""
    context = task.get("reviewed_context")
    if not isinstance(context, dict):
        raise FormIntegrationError("旧任务缺少审核上下文，请重新核实并发起任务",
                                   error_code="TASK_REVIEW_REQUIRED", status_code=409)
    link_id, binding_id = context.get("patient_link_id"), context.get("form_binding_id")
    if not all(ObjectId.is_valid(str(value)) for value in (link_id, binding_id)):
        raise FormIntegrationError("任务审核上下文无效", error_code="TASK_REVIEW_REQUIRED", status_code=409)
    options = {"session": session} if session is not None else {}
    link = await db.external_patient_links.find_one({"_id": ObjectId(str(link_id)),
        "local_patient_id": task.get("patient_id"), "status": "verified"}, **options)
    binding = await db.external_form_bindings.find_one({"_id": ObjectId(str(binding_id)),
        "status": "active"}, **options)
    reference = context.get("reference")
    refs = task.get("remote_refs") or {}
    references = link.get("references", [link.get("reference")]) if link else None
    if (not link or not binding or not isinstance(reference, dict) or not isinstance(refs, dict)
            or not isinstance(references, list) or reference not in references
            or not isinstance(context.get("version_ref"), dict)
            or not isinstance(context.get("purpose"), str)
            or context["purpose"] not in {"initial_assessment", "followup", "reassessment"}
            or link.get("source_origin") != binding.get("source_origin")
            or not link.get("source_origin")
            or binding.get("source") != reference.get("source")
            or binding.get("version_ref") != context.get("version_ref")
            or binding.get("purpose") != context.get("purpose")
            or binding.get("form_id") != refs.get("questionnaire_id")
            or binding.get("project_id") != refs.get("project_id")
            or any(reference.get(key) != refs.get(key) for key in ("project_id", "center_id", "subject_id"))):
        raise FormIntegrationError("患者关联或问卷审核已变化，请重新核实并发起任务",
                                   error_code="TASK_REVIEW_REVOKED", status_code=409)
    for reviewed in (link, binding):
        if (not isinstance(reviewed.get("verified_by"), str) or not reviewed["verified_by"].strip()
                or not isinstance(reviewed.get("verified_at"), datetime)
                or not isinstance(reviewed.get("evidence_reference"), str)
                or not reviewed["evidence_reference"].strip()):
            raise FormIntegrationError("审核证据不完整，请重新核实",
                                       error_code="TASK_REVIEW_REQUIRED", status_code=409)
    if session is not None:
        await _lock_reviewed_fill_context(db, session, link, binding)
    return link, binding


def _validated_launch_response(body, task, source_origin):
    """Reduce launch data to the exact source action for this session."""
    invalid = FormIntegrationError(
        "表单平台启动响应无效，请重新获取任务状态",
        error_code="FORM_PLATFORM_INVALID_LAUNCH", status_code=502)
    sid = models.active_session(task).get("session_uuid")
    if (not isinstance(body, dict) or not isinstance(sid, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", sid)
            or body.get("session_uuid") != sid):
        raise invalid
    mode = body.get("mode")
    field = "action" if mode == "launch" else "url" if mode == "resume" else None
    address = body.get(field) if field else None
    if not isinstance(address, str) or any(ord(char) <= 32 for char in address):
        raise invalid
    try:
        parsed = urlsplit(address)
        origin = f"{parsed.scheme}://{parsed.netloc.lower()}"
        expected_path = f"/integration/{'embed' if mode == 'launch' else 'resume'}/{sid}"
        if (origin != source_origin or parsed.scheme != "https" or parsed.username
                or parsed.password or parsed.path != expected_path or parsed.query or parsed.fragment):
            raise invalid
        expiry = body.get("expires_at")
        if not isinstance(expiry, str):
            raise invalid
        expires_at = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        if expires_at.tzinfo is None or expires_at <= datetime.now(timezone.utc):
            raise invalid
    except (TypeError, ValueError):
        raise invalid from None
    result = {"taskId": str(task["_id"]), "mode": mode, field: address,
              "sessionUuid": sid, "expiresAt": expiry, "allowedOrigin": task.get("allowed_origin")}
    if mode == "launch":
        token = body.get("token")
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,512}", token):
            raise invalid
        result["token"] = token
    return result


async def launch_fill_task(db, client, task_id, operator, *, delegation):
    """Authorize a short-lived source launch without persisting its credentials."""
    from app.db.transactions import run_followup_transaction
    from app.integrations.identity.service import FillDelegation, OidcFailure, OidcUnavailable

    require_fill_enabled()
    doc = await get_fill_task(db, task_id, operator)
    try:
        source_origin = client.source_origin
    except FormPlatformError:
        raise FormIntegrationError("来源配置不可用", error_code="SOURCE_CONFIGURATION_INVALID", status_code=503) from None
    if (not isinstance(delegation, FillDelegation) or delegation.actor_id != str(operator.id)
            or delegation.role != operator.role or delegation.client.settings.issuer != source_origin):
        raise FormIntegrationError("请重新登录后继续填写", error_code="SOURCE_IDENTITY_REQUIRED", status_code=403)
    sid = models.active_session(doc).get("session_uuid")
    if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", sid):
        raise FormIntegrationError("任务会话引用无效，请重新核实", error_code="TASK_SESSION_INVALID", status_code=409)
    identity = doc.get("identity_context")
    if (not isinstance(identity, dict) or (doc.get("operator") or {}).get("user_id") != str(operator.id)
            or any(identity.get(key) != delegation.record.get(key)
                   for key in ("issuer", "subject", "binding_revision"))):
        raise FormIntegrationError("任务登录委托已变化，请重新核实并发起任务",
                                   error_code="TASK_IDENTITY_CHANGED", status_code=409)

    async def authorize(session):
        current = await db[models.COLLECTION_NAME].find_one({"_id": doc["_id"]}, session=session)
        if (not current or current.get("status") not in {models.TASK_STATUS_SESSION_CREATED, models.TASK_STATUS_WAITING_FILL}
                or current.get("identity_context") != identity
                or models.active_session(current).get("session_uuid") != models.active_session(doc).get("session_uuid")):
            raise FormIntegrationError("任务状态已变化，请重新获取任务",
                                       error_code="TASK_CONFLICT", status_code=409)
        try:
            await delegation.lock(db, session)
        except OidcFailure:
            raise FormIntegrationError("登录委托已失效", error_code="SOURCE_IDENTITY_CHANGED", status_code=403) from None
        await require_task_reviewed_context(db, current, session=session)
        patient_id = current.get("patient_id")
        # 并发栅栏：fill_use_revision 直写在 users 账号文档上（同事务内 $inc 计数），
        # 第一波段保持不动。待栅栏载体改造（canonical 波段拆分账号/患者对象后）
        # 再将计数迁移到患者域对象；归属条件已复用 assigned_patient_query 共享范围。
        query = {"_id": ObjectId(patient_id) if ObjectId.is_valid(str(patient_id)) else patient_id, "role": "patient"}
        if operator.role != "admin":
            query.update(assigned_patient_query(str(operator.id), operator.role))
        assigned = await db.users.update_one(query, {"$inc": {"fill_use_revision": 1}}, session=session)
        if assigned.matched_count != 1:
            raise FormIntegrationError("患者管理关系已变化", error_code="PATIENT_NOT_ASSIGNED", status_code=403)
        await _write_task(db, current, {"updated_at": models.utcnow()}, session=session)
        return current

    try:
        await delegation.revalidate()
        await run_followup_transaction(db, authorize)
        body = await client.launch_fill_session(models.active_session(doc)["session_uuid"], source_access_token=delegation.token)
        result = _validated_launch_response(body, doc, source_origin)
        await delegation.revalidate()
        await run_followup_transaction(db, authorize)
    except OidcUnavailable:
        raise FormIntegrationError("身份源暂不可用", error_code="SOURCE_IDENTITY_UNAVAILABLE", status_code=503) from None
    except OidcFailure:
        raise FormIntegrationError("登录委托已失效", error_code="SOURCE_IDENTITY_REQUIRED", status_code=403) from None
    except FormPlatformError as exc:
        status = exc.status_code if exc.status_code in {400, 403, 404, 409, 410, 422, 429} else 502
        raise FormIntegrationError("表单平台暂时无法启动该任务，请重新核实状态",
                                   error_code="FORM_PLATFORM_LAUNCH_REJECTED", status_code=status) from None
    return result


async def confirm_fill_task(db: AsyncIOMotorDatabase, client: FormPlatformClient,
                            task_id: str, operator: Any) -> Dict[str, Any]:
    """向远端核实会话与答卷真实状态；只有远端确认提交才转 confirmed。"""
    doc = await get_fill_task(db, task_id, operator)
    task = models.FollowUpFillTask(deepcopy(doc))
    session_uuid = models.active_session(doc).get("session_uuid")

    if task.status == models.TASK_STATUS_CONFIRMED:
        return doc
    await require_task_reviewed_context(db, doc)
    if task.status in (models.TASK_STATUS_CANCELLED, models.TASK_STATUS_FAILED):
        raise FormIntegrationError(f"任务已处于终态 {task.status}，不能确认",
                                   error_code="TASK_TERMINAL", status_code=409)

    try:
        session_body = await client.get_fill_session(session_uuid)
    except FormPlatformError as exc:
        task.record_error(str(exc))
        await _write_task(db, doc, {"last_error": task.doc["last_error"], "updated_at": models.utcnow()})
        raise _map_remote_error(exc, "查询填报会话失败") from exc

    remote_status = session_body.get("status")
    if remote_status == "cancelled":
        task.set_status(models.TASK_STATUS_CANCELLED)
        await _write_task(db, doc, {"status": task.status, "updated_at": task.doc["updated_at"]})
        return task.doc
    if remote_status != "submitted":
        # 未提交：如实保留 waiting_fill/session_created，记录远端状态
        new_status = (models.TASK_STATUS_WAITING_FILL
                      if remote_status == "embedded" else task.status)
        await _write_task(db, doc, {"status": new_status, "updated_at": models.utcnow()})
        doc["status"] = new_status
        doc["remote_status"] = remote_status
        return doc

    # 远端已提交：核实答卷归属与本任务的远端引用一致
    response_id = session_body.get("response_id")
    if not response_id:
        raise FormIntegrationError("远端会话已提交但缺少答卷标识",
                                   error_code="FORM_PLATFORM_INVALID_RESPONSE", status_code=502)
    try:
        response_body = await client.get_response(int(response_id))
    except FormPlatformError as exc:
        task.record_error(str(exc))
        await _write_task(db, doc, {"last_error": task.doc["last_error"], "updated_at": models.utcnow()})
        raise _map_remote_error(exc, "查询答卷状态失败") from exc

    refs = doc.get("remote_refs") or {}
    expected = {
        "project_id": refs.get("project_id"),
        "subject_id": refs.get("subject_id"),
        "questionnaire_id": refs.get("questionnaire_id"),
    }
    actual = {
        "project_id": response_body.get("project_id"),
        "subject_id": response_body.get("subject_id"),
        "questionnaire_id": response_body.get("questionnaire_id"),
    }
    if actual != expected or response_body.get("operator_user_id") != refs.get("remote_operator_user_id"):
        raise FormIntegrationError(
            "远端答卷与本任务引用不一致，拒绝确认", error_code="RESPONSE_MISMATCH",
            status_code=409, details={"expected": expected, "actual": actual})

    evidence = {
        "response_id": response_body.get("response_id"),
        "session_uuid": session_uuid,
        "remote_status": response_body.get("status"),
        "visit_code": response_body.get("visit_code"),
        "submitted_at": response_body.get("submitted_at"),
        "answers": response_body.get("answers") or [],
        "verified_at": models.utcnow().isoformat() + "Z",
    }

    # FU01 S4 节点联动前置核验：任务带 followup_visit_id 时，答卷/任务与节点的
    # visit_code 必须一致（防答卷串访视，与 project/subject/questionnaire 核验同级）；
    # 任一核验失败即拒绝确认，任务不落 confirmed、节点不被回写。
    followup_visit_id = doc.get("followup_visit_id")
    node_visit_code: Optional[str] = None
    if followup_visit_id:
        visit_doc = await _load_followup_visit(db, followup_visit_id)
        if str(visit_doc.get("patient_id")) != str(doc.get("patient_id")):
            raise FormIntegrationError(
                "随访节点与任务患者不一致，拒绝确认",
                error_code="FOLLOWUP_VISIT_PATIENT_MISMATCH", status_code=409,
                details={"node_patient_id": str(visit_doc.get("patient_id")),
                         "task_patient_id": str(doc.get("patient_id"))})
        node_visit_code = visit_doc.get("visit_code")
        if visit_doc.get("status") in FOLLOWUP_VISIT_TERMINAL_STATUSES:
            raise FormIntegrationError(
                f"随访节点已处于终态 {visit_doc.get('status')}，不能确认回写",
                error_code="FOLLOWUP_VISIT_TERMINAL", status_code=409)
        visit_mismatches = []
        if node_visit_code:
            if doc.get("visit_code") and doc["visit_code"] != node_visit_code:
                visit_mismatches.append({"source": "task", "visit_code": doc["visit_code"]})
            if evidence.get("visit_code") and evidence["visit_code"] != node_visit_code:
                visit_mismatches.append({"source": "remote_response",
                                         "visit_code": evidence["visit_code"]})
        if visit_mismatches:
            raise FormIntegrationError(
                "答卷访视与随访节点不一致，拒绝确认", error_code="RESPONSE_MISMATCH",
                status_code=409,
                details={"node_visit_code": node_visit_code, "actual": visit_mismatches})

    async def persist_confirmation(session=None):
        options = {"session": session} if session else {}
        current = await db[models.COLLECTION_NAME].find_one({"_id": doc["_id"]}, **options)
        if not current:
            raise FormIntegrationError("填报任务不存在", error_code="TASK_NOT_FOUND", status_code=404)
        if current.get("status") == models.TASK_STATUS_CONFIRMED:
            return current
        await require_task_reviewed_context(db, current, session=session)
        if current.get("status") in (models.TASK_STATUS_CANCELLED, models.TASK_STATUS_FAILED):
            raise FormIntegrationError("任务已关闭，不能确认", error_code="TASK_TERMINAL", status_code=409)
        if models.active_session(current).get("session_uuid") != session_uuid:
            raise FormIntegrationError("活动会话已改变，请重新核实", error_code="TASK_CONFLICT", status_code=409)
        confirmed = models.FollowUpFillTask(deepcopy(current))
        confirmed.mark_confirmed(evidence)
        if followup_visit_id:
            from app.models.health_record import FollowUpRecord
            from app.core.followup_semantics import (
                followup_conflict, followup_submission_fields, followup_version_filter)
            visit = await db[FollowUpRecord.collection_name].find_one(
                {"_id": ObjectId(followup_visit_id)}, **options)
            if not visit or str(visit.get("patient_id")) != str(current.get("patient_id")):
                raise followup_conflict("随访节点归属已改变")
            _visit_is_writable(visit)
            if visit.get("visit_code") != node_visit_code:
                raise followup_conflict("随访访视标识已改变，请重新核实")
            values = {"status": "in_review", "effective_response": {
                    "task_id": str(doc["_id"]), "response_id": evidence.get("response_id"),
                    "visit_code": node_visit_code or evidence.get("visit_code"),
                    "submitted_at": evidence.get("submitted_at"),
                    "confirmed_at": confirmed.doc["confirmed_at"].isoformat() + "Z"},
                    "updated_at": confirmed.doc["updated_at"],
                    "completion_data": None, "answers": [], "follow_up_result": None,
                    "actual_date": None}
            values.update(followup_submission_fields(visit, values, source="external_form",
                submitted_by=(current.get("operator") or {}).get("user_id"),
                submitted_at=confirmed.doc["confirmed_at"], confirmation=evidence))
            result = await db[FollowUpRecord.collection_name].update_one(
                followup_version_filter(visit),
                {"$set": values,
                 "$addToSet": {"fill_task_ids": doc["_id"]}, "$inc": {"mutation_version": 1}},
                **options)
            if result.matched_count != 1:
                raise followup_conflict("随访节点已被其他请求修改")
        await _write_task(db, current, {
            "status": confirmed.status, "confirmation": confirmed.doc["confirmation"],
            "confirmed_at": confirmed.doc["confirmed_at"],
            "session.response_id": evidence["response_id"],
            "fill_sessions": confirmed.doc.get("fill_sessions"), "last_error": None,
            "updated_at": confirmed.doc["updated_at"],
        }, session=session)
        return await db[models.COLLECTION_NAME].find_one({"_id": doc["_id"]}, **options)

    from app.db.transactions import run_followup_transaction
    return await run_followup_transaction(db, persist_confirmation)


async def list_fill_tasks(db: AsyncIOMotorDatabase, operator: Any,
                          status: Optional[str] = None,
                          patient_id: Optional[str] = None,
                          skip: int = 0, limit: int = 20) -> Dict[str, Any]:
    """填报任务列表：发起人只看自己创建的，admin 可看全部；按创建时间倒序分页。"""
    if operator.role not in OPERATOR_ROLES:
        raise FormIntegrationError("当前角色不能访问医护填报任务",
                                   error_code="OPERATOR_ROLE_NOT_ALLOWED", status_code=403)
    if status is not None and status not in models.TASK_STATUSES:
        raise FormIntegrationError(f"未知任务状态：{status}",
                                   error_code="INVALID_STATUS_FILTER", status_code=422)
    query: Dict[str, Any] = {}
    if operator.role != "admin":
        query["operator.user_id"] = str(operator.id)
    if status is not None:
        query["status"] = status
    if patient_id:
        await _verify_patient_assignment(db, patient_id, str(operator.id), operator.role)
        query["patient_id"] = patient_id
    elif operator.role != "admin":
        # 患者范围经共享读取适配器解析（角色化归属字段 + ObjectId/string 双字面
        # 兼容 + 多实体歧义防护），与上方显式 patient_id 分支的 ensure_patient_access
        # 同源（AUTH01 共享实现），不再直查 users 集合。
        query["patient_id"] = {"$in": await LegacyPatientRepository(db).assigned_ids(
            assigned_patient_query(str(operator.id), operator.role))}

    total = await db[models.COLLECTION_NAME].count_documents(query)
    cursor = (db[models.COLLECTION_NAME].find(query)
              .sort("created_at", -1)
              .skip(max(skip, 0))
              .limit(min(max(limit, 1), 100)))
    items = [models.serialize_task(doc) async for doc in cursor]
    return {"items": items, "total": total, "skip": skip, "limit": limit}


async def cancel_fill_task(db: AsyncIOMotorDatabase, client: FormPlatformClient,
                           task_id: str, operator: Any) -> Dict[str, Any]:
    doc = await get_fill_task(db, task_id, operator)
    task = models.FollowUpFillTask(deepcopy(doc))
    if task.status == models.TASK_STATUS_CONFIRMED:
        raise FormIntegrationError("已确认的填报任务不能取消", error_code="TASK_CONFIRMED",
                                   status_code=409)
    session_uuid = models.active_session(doc).get("session_uuid")
    if session_uuid and task.status not in (models.TASK_STATUS_CANCELLED, models.TASK_STATUS_FAILED):
        try:
            await client.cancel_fill_session(session_uuid)
        except FormPlatformError as exc:
            raise _map_remote_error(exc, "取消远端会话失败") from exc
    task.set_status(models.TASK_STATUS_CANCELLED)
    await _write_task(db, doc, {"status": task.status, "updated_at": task.doc["updated_at"]})
    return task.doc
