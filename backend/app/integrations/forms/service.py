"""集成填报任务服务：患者归属校验、远端会话创建、状态确认。

边界：
- 服务凭证只用于服务端对服务端调用，绝不当作操作者身份；
- 远端查询结果必须与本任务记录的远端引用一致才可确认（防止状态串号）；
- 远端失败如实记录 last_error / 任务 failed，不伪装完成。
"""

from typing import Any, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import AppBaseException
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


async def _load_patient_doc(db: AsyncIOMotorDatabase, patient_id: str) -> Dict[str, Any]:
    from bson import ObjectId, errors as bson_errors

    query: Dict[str, Any] = {}
    if ObjectId.is_valid(patient_id):
        query["_id"] = ObjectId(patient_id)
    else:
        query["_id"] = patient_id
    doc = await db.users.find_one({**query, "role": "patient"})
    if not doc:
        raise FormIntegrationError("患者不存在", error_code="PATIENT_NOT_FOUND", status_code=404)
    return doc


async def _verify_patient_assignment(db: AsyncIOMotorDatabase, patient_id: str,
                                     operator_id: str, operator_role: str) -> None:
    """默认拒绝：操作者必须是患者档案中的主治医生（或管理员）。"""
    if operator_role == "admin":
        return
    patient = await _load_patient_doc(db, patient_id)
    practitioners = patient.get("practitioners") or []
    normalized = {str(item) for item in practitioners}
    if operator_id not in normalized:
        raise FormIntegrationError(
            "当前用户不是该患者的主治医生，不能为其发起表单填报任务",
            error_code="PATIENT_NOT_ASSIGNED", status_code=403)


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

    refs = _extract_remote_refs(payload)
    allowed_origin = (payload.get("allowed_origin") or "").strip().rstrip("/")
    if not allowed_origin:
        raise FormIntegrationError("allowed_origin 必填（发起嵌入页面的来源）",
                                   error_code="INVALID_ORIGIN", status_code=422)

    task = models.IntegrationFillTask.new_task(
        patient_id=patient_id,
        operator_id=operator_id,
        operator_role=operator_role,
        remote_refs=refs,
        allowed_origin=allowed_origin,
        ma_task_ref=payload.get("ma_task_ref"),
        visit_code=payload.get("visit_code"),
        visit_name=payload.get("visit_name"),
        ttl_seconds=payload.get("ttl_seconds"),
    )

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

    try:
        session_body = await client.create_fill_session(remote_payload)
    except FormPlatformError as exc:
        mapped = _map_remote_error(exc, "创建填报会话失败")
        raise mapped from exc

    token = session_body.get("embed_token")
    task.record_remote_session(session_body, models.hash_embed_token(token) if token else None)
    if not task.doc["session"]["session_uuid"] or not token:
        # 远端响应缺关键材料：不落一条看似成功的任务
        raise FormIntegrationError("表单平台返回的会话缺少 embed_url/embed_token",
                                   error_code="FORM_PLATFORM_INVALID_RESPONSE", status_code=502)

    result = await db[models.COLLECTION_NAME].insert_one(task.doc)
    body = models.serialize_task(task.doc)
    body["id"] = str(result.inserted_id)
    # 一次性透传：明文令牌只在创建响应出现，不写日志不落库
    body["embedToken"] = token
    return body


async def get_fill_task(db: AsyncIOMotorDatabase, task_id: str,
                        operator: Any) -> Dict[str, Any]:
    from bson import ObjectId, errors as bson_errors

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
    return doc


async def confirm_fill_task(db: AsyncIOMotorDatabase, client: FormPlatformClient,
                            task_id: str, operator: Any) -> Dict[str, Any]:
    """向远端核实会话与答卷真实状态；只有远端确认提交才转 confirmed。"""
    doc = await get_fill_task(db, task_id, operator)
    task = models.IntegrationFillTask(doc)
    session_uuid = (doc.get("session") or {}).get("session_uuid")

    if task.status == models.TASK_STATUS_CONFIRMED:
        return doc
    if task.status in (models.TASK_STATUS_CANCELLED, models.TASK_STATUS_FAILED):
        raise FormIntegrationError(f"任务已处于终态 {task.status}，不能确认",
                                   error_code="TASK_TERMINAL", status_code=409)

    try:
        session_body = await client.get_fill_session(session_uuid)
    except FormPlatformError as exc:
        task.record_error(str(exc))
        await db[models.COLLECTION_NAME].update_one(
            {"_id": doc["_id"]},
            {"$set": {"last_error": task.doc["last_error"], "updated_at": models.utcnow()}})
        raise _map_remote_error(exc, "查询填报会话失败") from exc

    remote_status = session_body.get("status")
    if remote_status == "cancelled":
        task.set_status(models.TASK_STATUS_CANCELLED)
        await db[models.COLLECTION_NAME].update_one(
            {"_id": doc["_id"]},
            {"$set": {"status": task.status, "updated_at": task.doc["updated_at"]}})
        return doc
    if remote_status != "submitted":
        # 未提交：如实保留 waiting_fill/session_created，记录远端状态
        new_status = (models.TASK_STATUS_WAITING_FILL
                      if remote_status == "embedded" else task.status)
        await db[models.COLLECTION_NAME].update_one(
            {"_id": doc["_id"]},
            {"$set": {"status": new_status, "updated_at": models.utcnow()}})
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
        await db[models.COLLECTION_NAME].update_one(
            {"_id": doc["_id"]},
            {"$set": {"last_error": task.doc["last_error"], "updated_at": models.utcnow()}})
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
    task.mark_confirmed(evidence)
    await db[models.COLLECTION_NAME].update_one(
        {"_id": doc["_id"]},
        {"$set": {
            "status": task.status,
            "confirmation": task.doc["confirmation"],
            "confirmed_at": task.doc["confirmed_at"],
            "session.response_id": evidence["response_id"],
            "last_error": None,
            "updated_at": task.doc["updated_at"],
        }})
    return doc


async def cancel_fill_task(db: AsyncIOMotorDatabase, client: FormPlatformClient,
                           task_id: str, operator: Any) -> Dict[str, Any]:
    doc = await get_fill_task(db, task_id, operator)
    task = models.IntegrationFillTask(doc)
    if task.status == models.TASK_STATUS_CONFIRMED:
        raise FormIntegrationError("已确认的填报任务不能取消", error_code="TASK_CONFIRMED",
                                   status_code=409)
    session_uuid = (doc.get("session") or {}).get("session_uuid")
    if session_uuid and task.status not in (models.TASK_STATUS_CANCELLED, models.TASK_STATUS_FAILED):
        try:
            await client.cancel_fill_session(session_uuid)
        except FormPlatformError as exc:
            raise _map_remote_error(exc, "取消远端会话失败") from exc
    task.set_status(models.TASK_STATUS_CANCELLED)
    await db[models.COLLECTION_NAME].update_one(
        {"_id": doc["_id"]},
        {"$set": {"status": task.status, "updated_at": task.doc["updated_at"]}})
    return doc
