"""集成填报任务路由（/api/integrations/forms）。

全部端点要求登录用户（get_current_active_user）；患者归属校验在 service 层。
"""

from typing import Any, Dict, Optional
from datetime import datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.auth import get_current_active_user
from app.db.mongodb import get_database
from .client import FormPlatformClient, FormPlatformError
from . import service
from .candidates import list_fill_candidates
from .service import FormIntegrationError
from .mini_bridge import issue_launch_bridge, consume_launch_bridge
from . import patient_self

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


@router.get("/fill-candidates")
async def fill_candidates(
    skip: int = Query(0, ge=0, le=10_000),
    limit: int = Query(50, ge=1, le=100),
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    client: FormPlatformClient = Depends(get_form_platform_client),
):
    """列出当前操作者可发起填报的本地患者及已审核来源表单。"""
    try:
        return await list_fill_candidates(
            db, current_user, client.source_origin, skip=skip, limit=limit)
    except FormPlatformError as exc:
        raise HTTPException(status_code=503, detail={
            "error": "FORM_PLATFORM_NOT_CONFIGURED", "message": "表单平台来源配置无效",
        }) from exc


async def current_fill_delegation(request, db, current_user):
    from app.integrations.identity.access import unified_authentication, SESSION_COOKIE
    from app.integrations.identity.config import oidc_settings
    from app.integrations.identity.service import OidcClient, OidcFailure, OidcUnavailable

    if not unified_authentication():
        raise FormIntegrationError("填报需要统一身份登录", error_code="SOURCE_IDENTITY_REQUIRED", status_code=403)
    try:
        client = OidcClient(db, oidc_settings)
        if getattr(request.state, "identity_transport", None) == "mini_bearer":
            authorization = request.headers.get("authorization", "")
            token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
            if not token:
                raise OidcFailure()
            return await client.fill_delegation_for_mini_session(token, current_user)
        return await client.fill_delegation(request.cookies.get(SESSION_COOKIE), current_user)
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
        if getattr(request.state, "identity_transport", None) == "mini_bearer":
            from app.integrations.identity.config import oidc_settings
            from urllib.parse import urlsplit
            expected_origin = urlsplit(oidc_settings.public_base_url)
            allowed_origin = str(payload.get("allowed_origin") or "").rstrip("/")
            if allowed_origin != f"{expected_origin.scheme}://{expected_origin.netloc}":
                raise FormIntegrationError("小程序填报来源必须是系统已配置的 HTTPS 域名", error_code="INVALID_ORIGIN", status_code=422)
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
        result = await service.launch_fill_task(db, client, task_id, current_user, delegation=delegation)
        if getattr(request.state, "identity_transport", None) == "mini_bearer":
            from app.integrations.identity.config import oidc_settings
            task = await service.get_fill_task(db, task_id, current_user)
            ticket = await issue_launch_bridge(db, result, task, delegation, oidc_settings)
            return {
                "taskId": result["taskId"], "mode": result["mode"],
                "webviewUrl": oidc_settings.public_base_url + "/api/integrations/forms/fill-tasks/launch-bridge/" + ticket,
                "sessionUuid": result["sessionUuid"], "expiresAt": result["expiresAt"],
                "allowedOrigin": result["allowedOrigin"],
            }
        return result
    except FormIntegrationError as exc:
        raise _form_error_response(exc) from exc


@router.get("/fill-tasks/launch-bridge/{ticket}", include_in_schema=False)
async def fill_task_launch_bridge(ticket: str, request: Request,
                                  db: AsyncIOMotorDatabase = Depends(get_database)):
    # The URL ticket is not sufficient: require the browser cookie that approved
    # the mini session, then revalidate both browser and mini state server-side.
    from app.integrations.identity.config import oidc_settings as current_oidc_settings
    from app.integrations.identity.router import SESSION_COOKIE
    from app.integrations.identity.service import OidcClient
    return await consume_launch_bridge(
        db, ticket, request.cookies.get(SESSION_COOKIE), OidcClient(db, current_oidc_settings), current_oidc_settings)


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


def _require_patient_session(request: Request, current_user: Any):
    from app.integrations.identity.access import SESSION_COOKIE, unified_authentication
    if current_user.role != "patient":
        raise FormIntegrationError("仅患者本人可访问本人填报任务",
                                   error_code="SELF_FILL_ROLE_REQUIRED", status_code=403)
    if getattr(request.state, "identity_transport", None) == "mini_bearer":
        return
    if not unified_authentication() or not request.cookies.get(SESSION_COOKIE):
        raise FormIntegrationError("患者本人填报需要有效的 OneID 浏览器会话",
                                   error_code="SOURCE_IDENTITY_REQUIRED", status_code=403)


@router.post("/patient-self/tasks")
async def create_patient_self_task(
    request: Request,
    payload: Dict[str, Any],
    current_user: Any = Depends(get_current_active_user),
    _fill_enabled: None = Depends(require_fill_entry_enabled),
    db: AsyncIOMotorDatabase = Depends(get_database),
    client: FormPlatformClient = Depends(get_form_platform_client),
):
    """医护显式分配本人填报任务；未在这里创建源端患者会话。"""
    try:
        delegation = await current_fill_delegation(request, db, current_user)
        if getattr(request.state, "identity_transport", None) == "mini_bearer":
            from app.integrations.identity.config import oidc_settings
            expected_origin = urlsplit(oidc_settings.public_base_url)
            if str(payload.get("allowed_origin") or "").rstrip("/") != f"{expected_origin.scheme}://{expected_origin.netloc}":
                raise FormIntegrationError("小程序填报来源必须是系统已配置的 HTTPS 域名",
                                           error_code="INVALID_ORIGIN", status_code=422)
        return await patient_self.create_patient_task(db, client, current_user, payload, delegation=delegation)
    except FormIntegrationError as exc:
        raise _form_error_response(exc) from exc


@router.get("/patient-self/tasks")
async def list_patient_self_tasks(
    request: Request,
    skip: int = Query(0, ge=0, le=10_000), limit: int = Query(20, ge=1, le=100),
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        if current_user.role == "patient":
            _require_patient_session(request, current_user)
        return await patient_self.list_tasks(db, current_user, skip=skip, limit=limit)
    except FormIntegrationError as exc:
        raise _form_error_response(exc) from exc


@router.get("/patient-self/tasks/{task_id}")
async def get_patient_self_task(
    request: Request, task_id: str,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    client: FormPlatformClient = Depends(get_form_platform_client),
):
    try:
        task = await patient_self._task_for_id(db, task_id)
        if current_user.role == "patient":
            _require_patient_session(request, current_user)
            from app.integrations.identity.config import oidc_settings
            await patient_self._verify_live_patient_identity(db, task, current_user, oidc_settings.issuer)
        elif current_user.role in patient_self.PATIENT_ROLES:
            if (task.get("operator") or {}).get("user_id") != str(current_user.id):
                raise FormIntegrationError("只能查看自己分配的患者任务", error_code="SELF_FILL_TASK_FORBIDDEN", status_code=403)
            await service._verify_patient_assignment(db, task.get("patient_id"), str(current_user.id), current_user.role)
        else:
            raise FormIntegrationError("当前角色不能查看患者填报任务", error_code="SELF_FILL_ROLE_REQUIRED", status_code=403)
        task = await patient_self.refresh_remote_status(db, client, task)
        return patient_self.serialize_patient_task(task,
            include_staff=current_user.role in patient_self.PATIENT_ROLES,
            include_evidence=current_user.role in patient_self.PATIENT_ROLES)
    except FormIntegrationError as exc:
        raise _form_error_response(exc) from exc


@router.post("/patient-self/tasks/{task_id}/confirm")
async def confirm_patient_self_task(
    task_id: str,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    client: FormPlatformClient = Depends(get_form_platform_client),
):
    """Verify a patient-owned submission without relying on the patient's Mini session."""
    try:
        task = await patient_self.confirm_task(db, client, task_id, current_user)
        return patient_self.serialize_patient_task(task, include_staff=True, include_evidence=True)
    except FormIntegrationError as exc:
        raise _form_error_response(exc) from exc


@router.post("/patient-self/tasks/{task_id}/launch")
async def launch_patient_self_task(
    request: Request, task_id: str,
    current_user: Any = Depends(get_current_active_user),
    _fill_enabled: None = Depends(require_fill_entry_enabled),
    db: AsyncIOMotorDatabase = Depends(get_database),
    client: FormPlatformClient = Depends(get_form_platform_client),
):
    try:
        _require_patient_session(request, current_user)
        is_mini = getattr(request.state, "identity_transport", None) == "mini_bearer"
        authorization = request.headers.get("authorization", "")
        mini_token = authorization[7:].strip() if is_mini and authorization.lower().startswith("bearer ") else None
        if is_mini and not mini_token:
            raise FormIntegrationError("小程序登录已失效，请重新登录", error_code="MINI_SESSION_REQUIRED", status_code=403)
        from app.integrations.identity.config import oidc_settings
        from app.integrations.identity.access import SESSION_COOKIE
        from app.integrations.identity.service import OidcClient
        return await patient_self.launch_task(db, client, task_id, current_user, mini_token=mini_token,
            browser_sid=None if is_mini else request.cookies.get(SESSION_COOKIE),
            oidc_client=OidcClient(db, oidc_settings), settings_obj=oidc_settings)
    except FormIntegrationError as exc:
        raise _form_error_response(exc) from exc


@router.post("/patient-self/tasks/{task_id}/revoke")
async def revoke_patient_self_task(
    task_id: str,
    payload: Dict[str, Any],
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    client: FormPlatformClient = Depends(get_form_platform_client),
):
    try:
        return await patient_self.revoke_task(db, client, task_id, current_user,
                                              reason=payload.get("reason"))
    except FormIntegrationError as exc:
        raise _form_error_response(exc) from exc


@router.get("/patient-self/launch-bridge/{ticket}", include_in_schema=False)
async def patient_self_launch_bridge(ticket: str, request: Request,
                                     db: AsyncIOMotorDatabase = Depends(get_database)):
    from app.integrations.identity.config import oidc_settings
    from app.integrations.identity.router import SESSION_COOKIE
    from app.integrations.identity.service import OidcClient
    return await patient_self.consume_launch_bridge(db, ticket, request.cookies.get(SESSION_COOKIE),
        OidcClient(db, oidc_settings), oidc_settings)


@router.post("/patient-self/authorize", include_in_schema=False)
async def patient_self_authorize_callback(
    request: Request,
    payload: Dict[str, Any],
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Source-only callback; independent secret is mandatory even for cookie/Mini requests."""
    authorization = request.headers.get("authorization", "")
    supplied = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    try:
        await patient_self.callback_authorize(db, payload, supplied)
    except FormIntegrationError as exc:
        raise _form_error_response(exc) from exc
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
