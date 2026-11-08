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

from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from pymongo.errors import PyMongoError

from app.core.exceptions import AppBaseException
from app.core.patient_access import PatientAccessError, ensure_patient_access
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


async def _verify_patient_assignment(db: AsyncIOMotorDatabase, patient_id: str,
                                     operator_id: str, operator_role: str) -> None:
    """默认拒绝：操作者必须是患者档案中的主治医生（或管理员）。

    校验逻辑复用 app.core.patient_access.ensure_patient_access（AUTH01 共享实现）；
    此处仅把 PatientAccessError 翻译回集成侧错误类型，保持对外行为不变。
    """
    try:
        await ensure_patient_access(db, patient_id, operator_id, operator_role)
    except PatientAccessError as exc:
        if exc.error_code == "PATIENT_NOT_FOUND":
            raise FormIntegrationError("患者不存在",
                                       error_code="PATIENT_NOT_FOUND",
                                       status_code=404) from exc
        raise FormIntegrationError(
            "当前用户不是该患者的主治医生，不能为其发起表单填报任务",
            error_code="PATIENT_NOT_ASSIGNED", status_code=403) from exc


# 随访节点终态（confirm 回写前置校验：终态节点不接受答卷回写）
FOLLOWUP_VISIT_TERMINAL_STATUSES = {"completed", "canceled", "cancelled"}


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
        "remote_operator_user_id": payload.get("remote_operator_user_id"),
    }
    missing = [key for key, value in refs.items() if not isinstance(value, int) or isinstance(value, bool)]
    if missing:
        raise FormIntegrationError(
            "远端引用字段必须为整数：" + ", ".join(missing),
            error_code="INVALID_REMOTE_REFS", status_code=422)
    return refs


async def create_fill_task(db: AsyncIOMotorDatabase, client: FormPlatformClient,
                           operator: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    """创建填报任务：校验患者归属 → 远端建会话 → 落库任务（含一次性 embed_url 透传）。"""
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
    allowed_origin = (payload.get("allowed_origin") or "").strip().rstrip("/")
    if not allowed_origin:
        raise FormIntegrationError("allowed_origin 必填（发起嵌入页面的来源）",
                                   error_code="INVALID_ORIGIN", status_code=422)

    # visit_code 缺省时取节点 visit_code（设计稿 §3.3 第 1 步：visit_code=节点.visit_code）
    visit_code = payload.get("visit_code")
    if not visit_code and followup_visit:
        visit_code = followup_visit.get("visit_code")

    task = models.FollowUpFillTask.new_task(
        patient_id=patient_id,
        operator_id=operator_id,
        operator_role=operator_role,
        remote_refs=refs,
        allowed_origin=allowed_origin,
        ma_task_ref=payload.get("ma_task_ref"),
        visit_code=visit_code,
        visit_name=payload.get("visit_name"),
        ttl_seconds=payload.get("ttl_seconds"),
        followup_visit_id=str(followup_visit_id) if followup_visit_id else None,
    )
    task.doc["_id"] = ObjectId()
    task.doc["mutation_version"] = 0

    remote_payload = {
        "operator_user_id": refs["remote_operator_user_id"],
        "project_id": refs["project_id"],
        "center_id": refs["center_id"],
        "subject_id": refs["subject_id"],
        "questionnaire_id": refs["questionnaire_id"],
        "allowed_origin": allowed_origin,
    }
    if payload.get("visit_code"):
        remote_payload["visit_code"] = payload["visit_code"]
    if payload.get("visit_name"):
        remote_payload["visit_name"] = payload["visit_name"]
    if payload.get("ma_task_ref"):
        remote_payload["ma_task_ref"] = payload["ma_task_ref"]
    if payload.get("ttl_seconds") is not None:
        remote_payload["ttl_seconds"] = payload["ttl_seconds"]

    await _require_transaction_topology(db)
    try:
        session_body = await client.create_fill_session(remote_payload)
    except FormPlatformError as exc:
        mapped = _map_remote_error(exc, "创建填报会话失败")
        raise mapped from exc

    token = session_body.get("embed_token")
    task.record_remote_session(session_body, models.hash_embed_token(token) if token else None)
    if not task.doc["session"]["session_uuid"] or not token:
        # 远端响应缺关键材料：不落一条看似成功的任务
        invalid_response = FormIntegrationError("表单平台返回的会话缺少 embed_url/embed_token",
                                                error_code="FORM_PLATFORM_INVALID_RESPONSE", status_code=502)
        if task.doc["session"]["session_uuid"]:
            await _recover_failed_creation(db, client, task, invalid_response)
        raise invalid_response

    from app.db.transactions import run_followup_transaction
    from app.services.followup_service import followup_version_filter, followup_conflict

    async def persist_task(session):
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
    body = models.serialize_task(task.doc)
    # 一次性透传：明文令牌只在创建响应出现，不写日志不落库
    body["embedToken"] = token
    return body


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


async def confirm_fill_task(db: AsyncIOMotorDatabase, client: FormPlatformClient,
                            task_id: str, operator: Any) -> Dict[str, Any]:
    """向远端核实会话与答卷真实状态；只有远端确认提交才转 confirmed。"""
    doc = await get_fill_task(db, task_id, operator)
    task = models.FollowUpFillTask(deepcopy(doc))
    session_uuid = models.active_session(doc).get("session_uuid")

    if task.status == models.TASK_STATUS_CONFIRMED:
        return doc
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
        if current.get("status") in (models.TASK_STATUS_CANCELLED, models.TASK_STATUS_FAILED):
            raise FormIntegrationError("任务已关闭，不能确认", error_code="TASK_TERMINAL", status_code=409)
        if models.active_session(current).get("session_uuid") != session_uuid:
            raise FormIntegrationError("活动会话已改变，请重新核实", error_code="TASK_CONFLICT", status_code=409)
        confirmed = models.FollowUpFillTask(deepcopy(current))
        confirmed.mark_confirmed(evidence)
        if followup_visit_id:
            from app.models.health_record import FollowUpRecord
            from app.services.followup_service import followup_version_filter, followup_conflict
            visit = await db[FollowUpRecord.collection_name].find_one(
                {"_id": ObjectId(followup_visit_id)}, **options)
            if not visit or str(visit.get("patient_id")) != str(current.get("patient_id")):
                raise followup_conflict("随访节点归属已改变")
            _visit_is_writable(visit)
            if visit.get("visit_code") != node_visit_code:
                raise followup_conflict("随访访视标识已改变，请重新核实")
            result = await db[FollowUpRecord.collection_name].update_one(
                followup_version_filter(visit),
                {"$set": {"status": "in_review", "effective_response": {
                    "task_id": str(doc["_id"]), "response_id": evidence.get("response_id"),
                    "visit_code": node_visit_code or evidence.get("visit_code"),
                    "submitted_at": evidence.get("submitted_at"),
                    "confirmed_at": confirmed.doc["confirmed_at"].isoformat() + "Z"},
                    "updated_at": confirmed.doc["updated_at"]},
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

    if followup_visit_id:
        from app.db.transactions import run_followup_transaction
        return await run_followup_transaction(db, persist_confirmation)
    return await persist_confirmation()


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
        actor_ids = [str(operator.id)]
        if ObjectId.is_valid(str(operator.id)):
            actor_ids.append(ObjectId(str(operator.id)))
        cursor = db.users.find({"role": "patient", "practitioners": {"$in": actor_ids}}, {"_id": 1})
        query["patient_id"] = {"$in": [str(patient["_id"]) async for patient in cursor]}

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
