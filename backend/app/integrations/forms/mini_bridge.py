"""One-use server bridge for WeChat web-view form launches.

The remote platform's launch credential is kept encrypted server-side and
submitted in a POST body. Only a short-lived, single-use ticket crosses the
web-view URL boundary.
"""

import base64
import html
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from bson import ObjectId
from cryptography.fernet import Fernet
from fastapi import Response
from starlette.responses import RedirectResponse

from app.integrations.identity.service import digest
from . import models
from .service import FormIntegrationError

COLLECTION = "integration_fill_launch_bridges"


def _response(body, *, status=200, media_type="text/html"):
    return Response(body, status_code=status, media_type=media_type, headers={
        "Cache-Control": "no-store, no-cache, must-revalidate, private",
        "Pragma": "no-cache", "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
    })


def _encrypt(value, settings):
    return Fernet(settings.session_encryption_key.get_secret_value().encode("ascii")).encrypt(value.encode("utf-8")).decode("ascii")


async def issue_launch_bridge(db, launch, task, delegation, settings):
    """Store a short-lived, one-use bridge bound to the exact mini/source session."""
    source = delegation.record
    if not delegation.mini_session_id or not delegation.session_hash:
        raise FormIntegrationError("小程序填报委托无效", error_code="SOURCE_IDENTITY_REQUIRED", status_code=403)
    if (launch.get("taskId") != str(task.get("_id"))
            or launch.get("allowedOrigin") != task.get("allowed_origin")
            or launch.get("mode") not in {"launch", "resume"}):
        raise FormIntegrationError("填报启动上下文不匹配", error_code="FORM_PLATFORM_INVALID_LAUNCH", status_code=502)
    mode = launch["mode"]
    target = launch.get("action") if mode == "launch" else launch.get("url")
    parsed = urlsplit(target or "")
    session_uuid = models.active_session(task).get("session_uuid")
    expected_path = f"/integration/{'embed' if mode == 'launch' else 'resume'}/{session_uuid}"
    if (parsed.scheme != "https" or parsed.netloc.lower() != source.get("issuer", "").split("://", 1)[-1].lower()
            or parsed.path != expected_path or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise FormIntegrationError("表单平台启动地址无效", error_code="FORM_PLATFORM_INVALID_LAUNCH", status_code=502)
    token = launch.get("token") if mode == "launch" else None
    if mode == "launch" and (not isinstance(token, str) or not token):
        raise FormIntegrationError("缺少一次性表单启动凭证", error_code="FORM_PLATFORM_INVALID_LAUNCH", status_code=502)

    now = datetime.utcnow()
    expires_at = min(now + timedelta(seconds=90), datetime.fromisoformat(launch["expiresAt"].replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None))
    ticket = secrets.token_urlsafe(32)
    collection = db[COLLECTION]
    await collection.create_index("expires_at", expireAfterSeconds=0, name="fill_launch_bridge_expiry")
    document = {
        "_id": digest(ticket), "task_id": str(task["_id"]),
        "operator_id": str(delegation.actor_id), "role": delegation.role,
        "source_session_hash": delegation.session_hash,
        "mini_session_id": delegation.mini_session_id,
        "issuer": source["issuer"], "subject": source["subject"],
        "binding_revision": source["binding_revision"],
        "mode": mode, "target": target, "session_uuid": session_uuid,
        "allowed_origin": task.get("allowed_origin"),
        "token_encrypted": _encrypt(token, settings) if token else None,
        "expires_at": expires_at,
    }
    await collection.insert_one(document)
    return ticket


async def consume_launch_bridge(db, ticket, browser_sid, oidc_client, settings):
    """Consume one ticket, re-check source authorization, then POST or redirect."""
    invalid = _response("<!doctype html><meta charset=utf-8><h1>填报入口已失效，请返回小程序重新启动。</h1>", status=410)
    if not isinstance(ticket, str) or len(ticket) > 128:
        return invalid
    now = datetime.utcnow()
    query = {"_id": digest(ticket), "expires_at": {"$gt": now}}
    doc = await db[COLLECTION].find_one(query)
    if not doc:
        return invalid
    if not browser_sid or digest(browser_sid) != doc.get("source_session_hash"):
        return _response("<!doctype html><meta charset=utf-8><h1>请在已登录的微信页面中重新打开问卷入口。</h1>", status=403)

    try:
        source, actor = await oidc_client.actor_for_session(browser_sid)
        mini = await db.oidc_mini_sessions.find_one({
            "_id": doc.get("mini_session_id"),
            "source_session_id": doc.get("source_session_hash"),
            "actor_id": doc.get("operator_id"), "expires_at": {"$gt": now},
        })
    except Exception:
        return _response("<!doctype html><meta charset=utf-8><h1>身份服务暂不可用，请返回小程序稍后重试。</h1>", status=503)
    if (source is None or actor is None or mini is None
            or source.get("_id") != doc.get("source_session_hash")
            or str(actor.get("_id")) != doc.get("operator_id") or actor.get("role") != doc.get("role")
            or source.get("issuer") != doc.get("issuer") or source.get("subject") != doc.get("subject")
            or source.get("binding_revision") != doc.get("binding_revision")):
        return invalid

    # A leaked URL alone cannot consume a ticket; only the browser session that
    # approved the mini login can redeem it. Atomic deletion gives one-use use.
    doc = await db[COLLECTION].find_one_and_delete({
        **query, "source_session_hash": digest(browser_sid),
        "mini_session_id": doc.get("mini_session_id"),
        "operator_id": str(actor.get("_id")), "binding_revision": source.get("binding_revision"),
    })
    if not doc:
        return invalid

    try:
        task = await db[models.COLLECTION_NAME].find_one({"_id": ObjectId(doc["task_id"])})
    except Exception:
        return invalid
    identity = (task or {}).get("identity_context") or {}
    if (not task or (task.get("operator") or {}).get("user_id") != doc.get("operator_id")
            or identity.get("issuer") != doc.get("issuer") or identity.get("subject") != doc.get("subject")
            or identity.get("session_hash") != source.get("_id")
            or identity.get("binding_revision") != doc.get("binding_revision")
            or task.get("allowed_origin") != doc.get("allowed_origin")
            or models.active_session(task).get("session_uuid") != doc.get("session_uuid")
            or task.get("status") not in {models.TASK_STATUS_SESSION_CREATED, models.TASK_STATUS_WAITING_FILL}):
        return invalid

    # The bridge is a second authorization boundary. Re-check live patient
    # assignment and reviewed source records instead of trusting task snapshots.
    try:
        from . import service
        await service._verify_patient_assignment(
            db, task.get("patient_id"), doc.get("operator_id"), doc.get("role"))
        await service.require_task_reviewed_context(db, task)
        followup_visit_id = task.get("followup_visit_id")
        if followup_visit_id:
            visit = await service._load_followup_visit(db, str(followup_visit_id))
            service._visit_is_writable(visit)
            if str(visit.get("patient_id")) != str(task.get("patient_id")):
                raise FormIntegrationError("随访节点与任务患者不一致", error_code="FOLLOWUP_VISIT_PATIENT_MISMATCH", status_code=409)
    except FormIntegrationError as exc:
        status = 503 if exc.status_code >= 500 else 403 if exc.status_code == 403 else 409
        return _response("<!doctype html><meta charset=utf-8><h1>患者授权或问卷关联已变化，请返回小程序重新核实。</h1>", status=status)

    parsed = urlsplit(doc.get("target", ""))
    expected_path = f"/integration/{'embed' if doc.get('mode') == 'launch' else 'resume'}/{doc.get('session_uuid')}"
    if (parsed.scheme != "https" or parsed.netloc.lower() != doc.get("issuer", "").split("://", 1)[-1].lower()
            or parsed.path != expected_path or parsed.query or parsed.fragment or parsed.username or parsed.password):
        return invalid
    if doc.get("mode") == "resume":
        return RedirectResponse(doc["target"], status_code=303, headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, private",
            "Referrer-Policy": "no-referrer",
        })
    if doc.get("mode") != "launch" or not doc.get("token_encrypted"):
        return invalid
    try:
        token = Fernet(settings.session_encryption_key.get_secret_value().encode("ascii")).decrypt(
            doc["token_encrypted"].encode("ascii")).decode("utf-8")
    except Exception:
        return _response("<!doctype html><meta charset=utf-8><h1>无法恢复一次性启动凭证，请返回小程序重新启动。</h1>", status=503)

    nonce = base64.urlsafe_b64encode(secrets.token_bytes(18)).decode("ascii").rstrip("=")
    action = html.escape(doc["target"], quote=True)
    value = html.escape(token, quote=True)
    page = ("<!doctype html><html lang=\"zh\"><head><meta charset=\"utf-8\">"
            "<meta name=\"referrer\" content=\"no-referrer\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>正在打开问卷</title></head><body><p>正在打开已核实的问卷，请稍候。</p>"
            f"<form id=\"launch\" method=\"post\" action=\"{action}\"><input type=\"hidden\" name=\"token\" value=\"{value}\"></form>"
            f"<script nonce=\"{nonce}\">document.getElementById('launch').submit();</script>"
            "<noscript><button form=\"launch\">打开问卷</button></noscript></body></html>")
    response = _response(page)
    response.headers["Content-Security-Policy"] = f"default-src 'none'; form-action {doc['issuer']}; script-src 'nonce-{nonce}'; base-uri 'none'"
    return response
