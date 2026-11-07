"""集成填报任务路由（/api/integrations/forms）。

全部端点要求登录用户（get_current_active_user）；患者归属校验在 service 层。
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.auth import get_current_active_user
from app.db.mongodb import get_database
from .client import FormPlatformClient, FormPlatformError
from . import service
from .service import FormIntegrationError

router = APIRouter(prefix="/integrations/forms", tags=["form-integration"])


def get_form_platform_client() -> FormPlatformClient:
    try:
        return FormPlatformClient.from_settings()
    except FormPlatformError as exc:
        raise HTTPException(status_code=503, detail={
            "error": "FORM_PLATFORM_NOT_CONFIGURED",
            "message": "表单平台集成未配置",
        }) from exc


def _form_error_response(exc: FormIntegrationError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={
        "error": exc.error_code,
        "message": exc.message,
        "details": exc.details,
    })


@router.post("/fill-tasks")
async def create_fill_task(
    payload: Dict[str, Any],
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    client: FormPlatformClient = Depends(get_form_platform_client),
):
    """为患者创建嵌入填报任务（校验患者归属；embed_token 只在本响应出现一次）。"""
    try:
        return await service.create_fill_task(db, client, current_user, payload)
    except FormIntegrationError as exc:
        raise _form_error_response(exc) from exc


@router.get("/fill-tasks/{task_id}")
async def get_fill_task(
    task_id: str,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    client: FormPlatformClient = Depends(get_form_platform_client),
):
    """任务详情 + 远端会话当前状态（不一致时以远端为准的确认走 confirm）。"""
    try:
        doc = await service.get_fill_task(db, task_id, current_user)
    except FormIntegrationError as exc:
        raise _form_error_response(exc) from exc
    body = service.models.serialize_task(doc)
    session_uuid = (doc.get("session") or {}).get("session_uuid")
    remote_status: Optional[str] = None
    if session_uuid:
        try:
            session_body = await client.get_fill_session(session_uuid)
            remote_status = session_body.get("status")
        except FormPlatformError as exc:
            body["remoteQueryError"] = str(exc)
    body["remoteStatus"] = remote_status
    return body


@router.get("/fill-tasks/{task_id}/embed-url")
async def get_embed_url(
    task_id: str,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """返回嵌入 URL（明文 embed_token 不可再取；令牌过期需重新创建任务）。"""
    try:
        doc = await service.get_fill_task(db, task_id, current_user)
    except FormIntegrationError as exc:
        raise _form_error_response(exc) from exc
    if doc.get("status") not in (service.models.TASK_STATUS_SESSION_CREATED,
                                 service.models.TASK_STATUS_WAITING_FILL):
        raise HTTPException(status_code=409, detail={
            "error": "EMBED_URL_NOT_AVAILABLE",
            "message": f"任务状态为 {doc.get('status')}，嵌入链接不可用；请重新创建填报任务",
        })
    return service.models.serialize_embed_url(doc)


@router.post("/fill-tasks/{task_id}/confirm")
async def confirm_fill_task(
    task_id: str,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    client: FormPlatformClient = Depends(get_form_platform_client),
):
    """向 113.44 核实真实提交状态；确认后任务转 confirmed（待审阅）。"""
    try:
        doc = await service.confirm_fill_task(db, client, task_id, current_user)
    except FormIntegrationError as exc:
        raise _form_error_response(exc) from exc
    return service.models.serialize_task(doc)


@router.post("/fill-tasks/{task_id}/cancel")
async def cancel_fill_task(
    task_id: str,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    client: FormPlatformClient = Depends(get_form_platform_client),
):
    try:
        doc = await service.cancel_fill_task(db, client, task_id, current_user)
    except FormIntegrationError as exc:
        raise _form_error_response(exc) from exc
    return service.models.serialize_task(doc)
