"""Application authentication switch and cookie CSRF boundary."""
from urllib.parse import urlsplit
import re

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .config import oidc_settings
from .service import OidcClient

SESSION_COOKIE = "__Host-rehab_session"
CSRF_COOKIE = "__Host-rehab_csrf"


def unified_authentication():
    return oidc_settings.authentication_mode == "oidc"


def reject_legacy_credentials():
    if unified_authentication():
        raise HTTPException(403, detail={"code": "LOCAL_AUTH_DISABLED"})


def trusted_origin(origin):
    public = urlsplit(oidc_settings.public_base_url)
    return origin == public.scheme + "://" + public.netloc


def mini_proof_route(method, path):
    """Exact transaction endpoints authenticate with one-time proof in JSON."""
    if method == "POST" and path == "/api/auth/mini/transactions":
        return True
    if method == "POST" and re.fullmatch(
            r"/api/auth/mini/transactions/[A-Za-z0-9_-]{1,128}/(poll|exchange|cancel)", path):
        return True
    return method == "POST" and path == "/api/auth/mini/session/logout"


def mini_bearer_route(method, path):
    """Permit only the mobile workflows; each endpoint still enforces object access."""
    if method == "GET" and path in {
            "/api/users/me", "/api/doctors/patients", "/api/health-managers/patients",
            "/api/devices/", "/api/patients/dashboard-data", "/api/patients/health-metrics",
            "/api/patients/todo-items", "/api/patients/daily-records",
            "/api/health-records/patient-context", "/api/health-records",
            "/api/health-records/followups", "/api/health-records/followup-workbench",
            "/api/rehabilitation/publications/my-plans",
            "/api/consent/documents",
            "/api/integrations/forms/fill-candidates", "/api/integrations/forms/fill-tasks",
            "/api/integrations/forms/patient-self/tasks",
            "/api/communications/conversations", "/api/communications/unread-count",
            "/api/communications/contacts"}:
        return True
    if method == "GET" and re.fullmatch(
            r"/api/(?:doctors|health-managers)/health-records/[A-Za-z0-9_-]{1,128}", path):
        return True
    if method == "GET" and re.fullmatch(
            r"/api/rehabilitation/publications/my-plans/[0-9a-fA-F]{24}", path):
        return True
    if method == "GET" and re.fullmatch(r"/api/consent/documents/[0-9a-fA-F]{24}", path):
        return True
    if method == "POST" and re.fullmatch(r"/api/consent/documents/[0-9a-fA-F]{24}/signature", path):
        return True
    if method in {"GET", "POST"} and re.fullmatch(
            r"/api/rehabilitation/plans/[0-9a-fA-F]{24}/patient-feedback", path):
        return True
    if method == "POST" and re.fullmatch(
            r"/api/rehabilitation/plans/[0-9a-fA-F]{24}/patient-feedback/media", path):
        return True
    if method == "GET" and re.fullmatch(
            r"/api/rehabilitation/plans/[0-9a-fA-F]{24}/patient-feedback/media/[a-f0-9]{32}", path):
        return True
    if method == "POST" and re.fullmatch(
            r"/api/rehabilitation/plans/[0-9a-fA-F]{24}/patient-feedback/[0-9a-fA-F]{24}/supplements", path):
        return True
    if method == "GET" and re.fullmatch(
            r"/api/rehabilitation/plans/[0-9a-fA-F]{24}/training-cycles", path):
        return True
    if method == "GET" and re.fullmatch(r"/api/integrations/forms/fill-tasks/[0-9a-fA-F]{24}", path):
        return True
    if method == "GET" and re.fullmatch(r"/api/integrations/forms/patient-self/tasks/[0-9a-fA-F]{24}", path):
        return True
    if method == "POST" and re.fullmatch(
            r"/api/integrations/forms/fill-tasks/[0-9a-fA-F]{24}/(?:launch|confirm|cancel)", path):
        return True
    if method == "POST" and path in {"/api/patients/daily-records", "/api/health-records/followups",
                                      "/api/integrations/forms/fill-tasks",
                                      "/api/integrations/forms/patient-self/tasks",
                                      "/api/communications/authorized-conversations"}:
        return True
    if method in {"PUT", "DELETE"} and re.fullmatch(
            r"/api/patients/daily-records/(?:object:[0-9a-fA-F]{24}|string:[^/\x00-\x1f]+)", path):
        return True
    if method == "GET" and re.fullmatch(
            r"/api/health-records/followups/[0-9a-fA-F]{24}", path):
        return True
    if method == "POST" and re.fullmatch(
            r"/api/integrations/forms/patient-self/tasks/[0-9a-fA-F]{24}/(?:launch|revoke|confirm)", path):
        return True
    if method == "POST" and re.fullmatch(
            r"/api/health-records/followups/[0-9a-fA-F]{24}/(?:complete|review|re-evaluate)", path):
        return True
    if method in {"GET", "POST"} and re.fullmatch(
            r"/api/communications/conversations/[0-9a-fA-F]{24}/messages", path):
        return True
    if method == "GET" and re.fullmatch(
            r"/api/communications/conversations/[0-9a-fA-F]{24}", path):
        return True
    if method == "PUT" and re.fullmatch(
            r"/api/communications/conversations/[0-9a-fA-F]{24}/read", path):
        return True
    if method == "GET" and re.fullmatch(r"/api/devices/[0-9a-fA-F]{24}", path):
        return True
    if method == "GET" and re.fullmatch(r"/api/devices/[0-9a-fA-F]{24}/data", path):
        return True
    if method == "POST" and path == "/api/devices/bind":
        return True
    return method == "POST" and bool(re.fullmatch(
        r"/api/devices/[0-9a-fA-F]{24}/veepoo/readings", path))


class IdentityCsrfMiddleware(BaseHTTPMiddleware):
    """All application writes use same-origin cookie credentials in unified mode.

    OIDC callback is GET and has independent state/nonce/PKCE. No public write,
    local password route, API side channel or machine bypass is implicitly exempt.
    """
    async def dispatch(self, request: Request, call_next):
        # scope.path is the internal route after the trusted proxy strips root_path;
        # request.url.path includes root_path and is only suitable for public URLs.
        route_path = request.scope["path"]
        mini_proof = mini_proof_route(request.method, route_path)
        mini_api = (mini_bearer_route(request.method, route_path)
                    and (request.headers.get("authorization") or "").lower().startswith("bearer "))
        # This one machine-to-machine route authenticates its own independent
        # service credential; browser cookies cannot authorize the callback.
        self_fill_callback = (request.method == "POST" and
                              route_path == "/api/integrations/forms/patient-self/authorize")
        if unified_authentication() and route_path.rstrip("/") in {
                "/api/users/login", "/api/users/login/refresh", "/api/users/refresh-token", "/api/users/register"}:
            return JSONResponse({"code": "LOCAL_AUTH_DISABLED"}, status_code=403, headers={"Cache-Control": "no-store"})
        callback = request.method == "GET" and route_path == "/api/auth/oidc/callback"
        if (unified_authentication() and not callback and not mini_proof and not mini_api and not self_fill_callback and request.headers.get("origin")
                and not trusted_origin(request.headers["origin"])):
            return JSONResponse({"code": "ORIGIN_REJECTED"}, status_code=403, headers={"Cache-Control": "no-store"})
        if (unified_authentication() and request.method not in {"GET", "HEAD", "OPTIONS"}
                and not mini_proof and not mini_api and not self_fill_callback):
            if not trusted_origin(request.headers.get("origin")):
                return JSONResponse({"code": "CSRF_REJECTED"}, status_code=403, headers={"Cache-Control": "no-store"})
            from app.db.mongodb import get_db
            try:
                client = OidcClient(await get_db(), oidc_settings)
                valid = await client.verify_csrf(request.cookies.get(SESSION_COOKIE), request.headers.get("x-csrf-token"))
            except Exception:
                return JSONResponse({"code": "IDENTITY_SOURCE_UNAVAILABLE"}, status_code=503, headers={"Cache-Control": "no-store"})
            if not valid:
                return JSONResponse({"code": "CSRF_REJECTED"}, status_code=403, headers={"Cache-Control": "no-store"})
        response = await call_next(request)
        if unified_authentication():
            response.headers["Cache-Control"] = "no-store"
        return response
