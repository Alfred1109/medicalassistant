"""集成填报任务路由（/api/integrations/forms）。

全部端点要求登录用户（get_current_active_user）；患者归属校验在 service 层。
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.auth import get_current_active_user
from app.db.mongodb import get_database
from .client import FormPlatformClient, FormPlatformError
from . import service
from .service import FormIntegrationError

def private_response(response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


router = APIRouter(prefix="/integrations/forms", tags=["form-integration"],
                   dependencies=[Depends(private_response)])


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
    }, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


def require_fill_entry_enabled() -> None:
    try:
        service.require_fill_enabled()
    except FormIntegrationError as exc:
        raise _form_error_response(exc) from exc


async def current_fill_delegation(request, db, current_user):
    from app.integrations.identity.access import unified_authentication, SESSION_COOKIE
    from app.integrations.identity.config import oidc_settings
    from app.integrations.identity.service import OidcClient, OidcFailure, OidcUnavailable

    if not unified_authentication():
        raise FormIntegrationError("填报需要统一身份登录", error_code="SOURCE_IDENTITY_REQUIRED", status_code=403)
    try:
        return await OidcClient(db, oidc_settings).fill_delegation(request.cookies.get(SESSION_COOKIE), current_user)
    except OidcUnavailable:
        raise FormIntegrationError("身份源暂不可用", error_code="SOURCE_IDENTITY_UNAVAILABLE", status_code=503) from None
    except OidcFailure:
        raise FormIntegrationError("请重新登录后发起填报", error_code="SOURCE_IDENTITY_REQUIRED", status_code=403) from None


@router.post("/fill-tasks")
async def create_fill_task(
    request: Request,
    payload: Dict[str, Any],
    current_user: Any = Depends(get_current_active_user),
    _fill_enabled: None = Depends(require_fill_entry_enabled),
    db: AsyncIOMotorDatabase = Depends(get_database),
    client: FormPlatformClient = Depends(get_form_platform_client),
):
    """创建已核实患者与问卷的填报任务引用。"""
    try:
        delegation = await current_fill_delegation(request, db, current_user)
        return await service.create_fill_task(db, client, current_user, payload, delegation=delegation)
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
    session_uuid = service.models.active_session(doc).get("session_uuid")
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
async def get_embed_url(task_id: str, current_user: Any = Depends(get_current_active_user)):
    raise HTTPException(410, detail={"error": "LEGACY_EMBED_URL_RETIRED",
        "message": "请使用任务的继续填写入口"},
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.post("/fill-tasks/{task_id}/launch")
async def launch_fill_task(
    task_id: str,
    request: Request,
    current_user: Any = Depends(get_current_active_user),
    _fill_enabled: None = Depends(require_fill_entry_enabled),
    db: AsyncIOMotorDatabase = Depends(get_database),
    client: FormPlatformClient = Depends(get_form_platform_client),
):
    try:
        delegation = await current_fill_delegation(request, db, current_user)
        return await service.launch_fill_task(db, client, task_id, current_user, delegation=delegation)
    except FormIntegrationError as exc:
        raise _form_error_response(exc) from exc


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


@router.get("/fill-tasks")
async def list_fill_tasks(
    status: Optional[str] = None,
    patient_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """填报任务列表：发起人只见自己创建的，admin 见全部；倒序分页。"""
    try:
        return await service.list_fill_tasks(db, current_user, status, patient_id, skip, limit)
    except FormIntegrationError as exc:
        raise _form_error_response(exc) from exc


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
