from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.encoders import jsonable_encoder

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.core.auth import get_current_active_user
from app.db.mongodb import get_database
from .applications import decide_application, list_applications, own_application, submit_application
from .config import oidc_settings
from .service import OidcClient, OidcUnavailable
from .access import unified_authentication

router = APIRouter(prefix="/auth", tags=["identity"])
TRANSACTION_COOKIE = "__Host-rehab_oidc"
SESSION_COOKIE = "__Host-rehab_session"
CSRF_COOKIE = "__Host-rehab_csrf"


def enabled():
    if not oidc_settings.enabled:
        raise HTTPException(404, detail={"code": "OIDC_DISABLED"})


async def oidc_client(_=Depends(enabled), db=Depends(get_database)):
    return OidcClient(db, oidc_settings)


def headers(response):
    response.headers.update({"Cache-Control": "no-store", "Pragma": "no-cache",
                             "Referrer-Policy": "no-referrer"})
    return response


def cookie(response, name, value, max_age, *, httponly=True):
    response.set_cookie(name, value, secure=True, httponly=httponly,
                        samesite="lax", path="/", max_age=max_age)


def invalid_callback():
    if unified_authentication():
        response = RedirectResponse(oidc_settings.public_base_url + "/auth/oidc/complete?error=OIDC_VALIDATION_FAILED", status_code=303)
    else:
        response = JSONResponse({"code": "OIDC_VALIDATION_FAILED"}, status_code=400)
    response.delete_cookie(TRANSACTION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    return headers(response)


@router.get("/config")
async def configuration():
    return headers(JSONResponse({"mode": oidc_settings.authentication_mode,
        "oidc_enabled": oidc_settings.enabled,
        "login_url": oidc_settings.public_base_url + "/api/auth/oidc/start" if oidc_settings.enabled else None}))


@router.get("/oidc/start")
async def start(request: Request, client=Depends(oidc_client)):
    try:
        target, secret = await client.start(request.cookies.get(TRANSACTION_COOKIE))
    except Exception:
        raise HTTPException(503, detail={"code": "IDENTITY_SOURCE_UNAVAILABLE"}) from None
    response = headers(RedirectResponse(target, status_code=303))
    cookie(response, TRANSACTION_COOKIE, secret, 300)
    return response


@router.get("/oidc/callback")
async def callback(request: Request, client=Depends(oidc_client)):
    # Reject duplicate parameters; accept no browser-selected return target.
    required = ("state", "code")
    if any(len(request.query_params.getlist(key)) != 1 for key in required):
        return invalid_callback()
    try:
        sid, csrf, seconds = await client.callback(request.query_params["state"],
            request.query_params["code"], request.cookies.get(TRANSACTION_COOKIE))
        try:
            from app.operations.runtime import record_login_notice, session_timeout_minutes
            from app.core.config import settings as runtime_settings
            limit = await session_timeout_minutes(client.db, runtime_settings.ACCESS_TOKEN_EXPIRE_MINUTES)
            seconds = min(int(seconds), limit * 60)
            result = await client.session(sid)
            if result and result.get("actor_id"):
                await record_login_notice(client.db, result["actor_id"])
        except Exception:
            pass
        old_sid = request.cookies.get(SESSION_COOKIE)
        if old_sid:
            from .service import digest
            await client.db.oidc_application_sessions.delete_one({"_id": digest(old_sid)})
    except Exception:
        return invalid_callback()
    # Identity-only status page until the reviewed clinical authorization adapter exists.
    target = oidc_settings.public_base_url + "/auth/oidc/complete" if unified_authentication() else oidc_settings.session_uri
    response = headers(RedirectResponse(target, status_code=303))
    response.delete_cookie(TRANSACTION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    cookie(response, SESSION_COOKIE, sid, seconds)
    cookie(response, CSRF_COOKIE, csrf, seconds, httponly=False)
    return response


@router.get("/session")
async def session(request: Request, client=Depends(oidc_client)):
    try:
        result = await client.session(request.cookies.get(SESSION_COOKIE))
        if result and result["clinical_access"]:
            from app.services.user_service import UserService
            from app.core.permissions import get_user_permissions
            user = await UserService(client.db).get_user_by_id(result["actor_id"])
            result["user"] = jsonable_encoder(user)
            result["clinical_permissions"] = sorted(get_user_permissions(user))
        elif result:
            result["user"] = None
    except OidcUnavailable:
        return headers(JSONResponse({"code": "IDENTITY_SOURCE_UNAVAILABLE"}, status_code=503))
    return headers(JSONResponse(result or {"authenticated": False}, status_code=200 if result else 401))


class AccessApplicationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    requested_role: str = Field(pattern=r"^(patient|doctor|health_manager)$")
    note: str = ""


class AccessDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    approved: StrictBool
    local_user_id: str = ""
    evidence_reference: str = ""
    reason: str = ""


async def current_session(request: Request, client=Depends(oidc_client)):
    try:
        return await client.session(request.cookies.get(SESSION_COOKIE))
    except OidcUnavailable:
        raise HTTPException(503, detail={"code": "IDENTITY_SOURCE_UNAVAILABLE"}) from None


@router.get("/access-applications/mine")
async def my_access_application(response: Response, session=Depends(current_session), db=Depends(get_database)):
    headers(response)
    return await own_application(db, session)


@router.post("/access-applications", status_code=201)
async def create_access_application(payload: AccessApplicationRequest, response: Response,
                                    session=Depends(current_session), db=Depends(get_database)):
    headers(response)
    return await submit_application(db, session, payload.requested_role, payload.note)


def require_admin(user=Depends(get_current_active_user)):
    if user.role != "admin":
        raise HTTPException(403, detail={"code": "ADMIN_REQUIRED"})
    return user


@router.get("/access-applications")
async def access_applications(response: Response, status: str = "pending",
                              _=Depends(require_admin), db=Depends(get_database)):
    headers(response)
    return {"applications": await list_applications(db, status)}


@router.post("/access-applications/{application_id}/decision")
async def access_decision(application_id: str, payload: AccessDecisionRequest, response: Response,
                          actor=Depends(require_admin), db=Depends(get_database)):
    headers(response)
    return await decide_application(db, actor, application_id, approved=payload.approved,
                                    local_user_id=payload.local_user_id, evidence_reference=payload.evidence_reference,
                                    reason=payload.reason)


@router.post("/logout")
async def logout(request: Request, client=Depends(oidc_client)):
    public = urlsplit(oidc_settings.public_base_url)
    if request.headers.get("origin") != public.scheme + "://" + public.netloc:
        raise HTTPException(403, detail={"code": "CSRF_REJECTED"})
    try:
        await client.logout(request.cookies.get(SESSION_COOKIE), request.headers.get("x-csrf-token"))
    except OidcUnavailable:
        raise HTTPException(503, detail={"code": "SOURCE_LOGOUT_UNAVAILABLE"}) from None
    except Exception:
        raise HTTPException(403, detail={"code": "CSRF_REJECTED"}) from None
    response = headers(Response(status_code=204))
    for name in (SESSION_COOKIE, CSRF_COOKIE, TRANSACTION_COOKIE):
        response.delete_cookie(name, path="/", secure=True, httponly=name != CSRF_COOKIE, samesite="lax")
    return response
