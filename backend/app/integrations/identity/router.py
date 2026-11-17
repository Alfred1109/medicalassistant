import logging
import html
from datetime import datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.encoders import jsonable_encoder

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.core.auth import get_current_active_user
from app.db.mongodb import get_database
from .applications import decide_application, list_applications, own_application, submit_application
from .config import oidc_settings
from .service import OidcClient, OidcFailure, OidcUnavailable, digest
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


def public_api_url(path):
    return oidc_settings.public_base_url + "/api/" + path.lstrip("/")


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
        sid, csrf, seconds, mini_transaction_id = await client.callback(request.query_params["state"],
            request.query_params["code"], request.cookies.get(TRANSACTION_COOKIE), include_transaction=True)
        if mini_transaction_id:
            record, actor = await client.actor_for_session(sid)
            if record is None:
                raise ValueError("OIDC session invalid")
            await client.set_mini_login_result(mini_transaction_id, record["_id"],
                                               approved_binding=actor is not None)
        try:
            from app.operations.runtime import record_login_notice
            result = await client.session(sid)
            if result and result.get("actor_id"):
                await record_login_notice(client.db, result["actor_id"])
        except Exception:
            logging.warning("OIDC 登录通知未能记录")
        old_sid = request.cookies.get(SESSION_COOKIE)
        if old_sid:
            from .service import digest
            await client.db.oidc_application_sessions.delete_one({"_id": digest(old_sid)})
    except Exception:
        return invalid_callback()
    # Identity-only status page until the reviewed clinical authorization adapter exists.
    target = (public_api_url("auth/mini/transactions/" + mini_transaction_id + "/confirm")
              if mini_transaction_id else
              oidc_settings.public_base_url + "/auth/oidc/complete" if unified_authentication() else oidc_settings.session_uri)
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


class MiniTransactionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    code_challenge: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


class MiniVerifierRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    verifier: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


def mini_user_summary(actor):
    return {"id": str(actor["_id"]),
            "display_name": str(actor.get("name") or actor.get("full_name") or actor.get("username") or "系统账号")[:120],
            "role": str(actor.get("role") or "")}


def require_mini_authentication():
    if not unified_authentication():
        raise HTTPException(403, detail={"code": "UNIFIED_AUTH_REQUIRED"})


@router.post("/mini/transactions")
async def create_mini_transaction(payload: MiniTransactionRequest, response: Response,
                                  client=Depends(oidc_client)):
    require_mini_authentication()
    try:
        transaction_id = await client.create_mini_transaction(payload.code_challenge)
    except Exception:
        raise HTTPException(503, detail={"code": "IDENTITY_SOURCE_UNAVAILABLE"}) from None
    headers(response)
    return {"transaction_id": transaction_id,
            "webview_url": public_api_url("auth/mini/authorize/" + transaction_id),
            "expires_in": 300, "poll_interval": 2}


@router.get("/mini/authorize/{transaction_id}")
async def authorize_mini_transaction(transaction_id: str, request: Request,
                                     client=Depends(oidc_client)):
    if len(transaction_id) > 128:
        raise HTTPException(404, detail={"code": "MINI_TRANSACTION_NOT_FOUND"})
    require_mini_authentication()
    transaction = await client.db.oidc_mini_login_transactions.find_one({
        "_id": digest(transaction_id), "expires_at": {"$gt": datetime.utcnow()}})
    if transaction is None:
        raise HTTPException(410, detail={"code": "MINI_TRANSACTION_EXPIRED"})
    if transaction.get("status") == "pending":
        started = await client.db.oidc_mini_login_transactions.update_one({
            "_id": transaction["_id"], "status": "pending",
            "expires_at": {"$gt": datetime.utcnow()}},
            {"$set": {"status": "oidc_started"}})
        if started.modified_count == 1:
            try:
                target, secret = await client.start(request.cookies.get(TRANSACTION_COOKIE),
                                                    mini_transaction_id=transaction_id)
            except Exception:
                await client.db.oidc_mini_login_transactions.update_one(
                    {"_id": transaction["_id"], "status": "oidc_started"},
                    {"$set": {"status": "pending"}})
                raise HTTPException(503, detail={"code": "IDENTITY_SOURCE_UNAVAILABLE"}) from None
            result = headers(RedirectResponse(target, status_code=303))
            cookie(result, TRANSACTION_COOKIE, secret, 300)
            return result
        transaction = await client.db.oidc_mini_login_transactions.find_one({
            "_id": transaction["_id"], "expires_at": {"$gt": datetime.utcnow()}})
    if not transaction or transaction.get("status") != "oidc_started":
        raise HTTPException(410, detail={"code": "MINI_TRANSACTION_EXPIRED"})
    secret = request.cookies.get(TRANSACTION_COOKIE)
    try:
        target = await client.mini_authorization_for_browser(transaction_id, secret)
    except OidcFailure:
        raise HTTPException(410, detail={"code": "MINI_TRANSACTION_EXPIRED"}) from None
    if target is None:
        raise HTTPException(410, detail={"code": "MINI_TRANSACTION_EXPIRED"})
    result = headers(RedirectResponse(target, status_code=303))
    cookie(result, TRANSACTION_COOKIE, secret, 300)
    return result


@router.get("/mini/transactions/{transaction_id}/confirm")
async def mini_browser_confirmation(transaction_id: str, request: Request,
                                    client=Depends(oidc_client)):
    require_mini_authentication()
    if len(transaction_id) > 128:
        raise HTTPException(404, detail={"code": "MINI_TRANSACTION_NOT_FOUND"})
    transaction = await client.db.oidc_mini_login_transactions.find_one({
        "_id": digest(transaction_id), "status": "awaiting_confirmation",
        "source_session_id": digest(request.cookies.get(SESSION_COOKIE) or ""),
        "expires_at": {"$gt": datetime.utcnow()}})
    if transaction is None:
        return headers(Response("<h1>登录已失效或无法确认，请返回小程序重新发起。</h1>",
                                status_code=410, media_type="text/html"))
    try:
        record, actor = await client.actor_for_session(request.cookies.get(SESSION_COOKIE))
    except OidcUnavailable:
        raise HTTPException(503, detail={"code": "IDENTITY_SOURCE_UNAVAILABLE"}) from None
    if record is None or actor is None:
        return headers(Response("<h1>此 OneID 尚未完成账号授权绑定，无法登录小程序。</h1>",
                                status_code=403, media_type="text/html"))
    summary = mini_user_summary(actor)
    csrf = request.cookies.get(CSRF_COOKIE, "")
    action = html.escape(public_api_url(
        "auth/mini/transactions/" + transaction_id + "/approve"), quote=True)
    page = f"""<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>确认小程序登录</title>
<h1>确认登录小程序</h1><p>当前 OneID 对应系统账号：<strong>{html.escape(summary['display_name'])}</strong></p><p>角色：{html.escape(summary['role'])}</p>
<p>请确认这是你要用于登录小程序的账号。</p><button id="approve">确认继续</button><p id="result" role="status"></p>
<script>document.getElementById('approve').onclick=async()=>{{const r=await fetch('{action}',{{method:'POST',headers:{{'x-csrf-token':'{html.escape(csrf, quote=True)}'}},credentials:'same-origin'}});document.getElementById('result').textContent=r.ok?'已确认，请返回小程序继续。':'确认失败，请返回小程序重新发起。';document.getElementById('approve').disabled=true;}};</script></html>"""
    return headers(Response(page, media_type="text/html"))


@router.post("/mini/transactions/{transaction_id}/approve")
async def approve_mini_transaction(transaction_id: str, request: Request,
                                  client=Depends(oidc_client)):
    require_mini_authentication()
    if len(transaction_id) > 128:
        raise HTTPException(404, detail={"code": "MINI_TRANSACTION_NOT_FOUND"})
    try:
        actor = await client.approve_mini_transaction(transaction_id, request.cookies.get(SESSION_COOKIE))
    except OidcUnavailable:
        raise HTTPException(503, detail={"code": "IDENTITY_SOURCE_UNAVAILABLE"}) from None
    except Exception:
        raise HTTPException(403, detail={"code": "MINI_CONFIRMATION_REJECTED"}) from None
    return headers(JSONResponse({"confirmed": True, "user": mini_user_summary(actor)}))


@router.post("/mini/transactions/{transaction_id}/poll")
async def poll_mini_transaction(transaction_id: str, payload: MiniVerifierRequest,
                                response: Response, client=Depends(oidc_client)):
    require_mini_authentication()
    try:
        transaction, status = await client.mini_transaction_status(transaction_id, payload.verifier)
        if transaction is None:
            raise HTTPException(401, detail={"code": "MINI_TRANSACTION_INVALID"})
        user = None
        if status == "ready":
            record, actor = await client.actor_for_session_hash(transaction.get("source_session_id"))
            if record is None or actor is None:
                await client.db.oidc_mini_login_transactions.update_one(
                    {"_id": transaction["_id"], "status": "ready"}, {"$set": {"status": "denied"}})
                status = "denied"
            else:
                user = mini_user_summary(actor)
        headers(response)
        public_status = status if status in {"ready", "denied", "expired"} else "pending"
        return {"status": public_status, "expires_in": max(0, int((transaction["expires_at"] - datetime.utcnow()).total_seconds())), **({"user": user} if user else {})}
    except OidcUnavailable:
        raise HTTPException(503, detail={"code": "IDENTITY_SOURCE_UNAVAILABLE"}) from None


@router.post("/mini/transactions/{transaction_id}/exchange")
async def exchange_mini_transaction(transaction_id: str, payload: MiniVerifierRequest,
                                    response: Response, client=Depends(oidc_client)):
    require_mini_authentication()
    try:
        token, seconds, actor = await client.exchange_mini_transaction(transaction_id, payload.verifier)
    except OidcUnavailable:
        raise HTTPException(503, detail={"code": "IDENTITY_SOURCE_UNAVAILABLE"}) from None
    except Exception:
        raise HTTPException(401, detail={"code": "MINI_TRANSACTION_INVALID"}) from None
    from app.core.user_record import user_response_from_document
    headers(response)
    return {"access_token": token, "token_type": "Bearer", "expires_in": seconds,
            "user": jsonable_encoder(user_response_from_document(actor))}


@router.post("/mini/transactions/{transaction_id}/cancel", status_code=204)
async def cancel_mini_transaction(transaction_id: str, payload: MiniVerifierRequest,
                                  client=Depends(oidc_client)):
    require_mini_authentication()
    challenge = client.mini_challenge(payload.verifier)
    if challenge is None:
        raise HTTPException(401, detail={"code": "MINI_TRANSACTION_INVALID"})
    await client.db.oidc_mini_login_transactions.delete_one({
        "_id": digest(transaction_id), "challenge_hash": digest(challenge)})
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post("/mini/session/logout", status_code=204)
async def logout_mini_session(request: Request, client=Depends(oidc_client)):
    require_mini_authentication()
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else ""
    if not await client.revoke_mini_session(token):
        raise HTTPException(401, detail={"code": "INVALID_CREDENTIALS"})
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


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
