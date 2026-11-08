"""Application authentication switch and cookie CSRF boundary."""
from urllib.parse import urlsplit

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


class IdentityCsrfMiddleware(BaseHTTPMiddleware):
    """All application writes use same-origin cookie credentials in unified mode.

    OIDC callback is GET and has independent state/nonce/PKCE. No public write,
    local password route, API side channel or machine bypass is implicitly exempt.
    """
    async def dispatch(self, request: Request, call_next):
        # scope.path is the internal route after the trusted proxy strips root_path;
        # request.url.path includes root_path and is only suitable for public URLs.
        route_path = request.scope["path"]
        if unified_authentication() and route_path.rstrip("/") in {
                "/api/users/login", "/api/users/login/refresh", "/api/users/refresh-token", "/api/users/register"}:
            return JSONResponse({"code": "LOCAL_AUTH_DISABLED"}, status_code=403, headers={"Cache-Control": "no-store"})
        callback = request.method == "GET" and route_path == "/api/auth/oidc/callback"
        if (unified_authentication() and not callback and request.headers.get("origin")
                and not trusted_origin(request.headers["origin"])):
            return JSONResponse({"code": "ORIGIN_REJECTED"}, status_code=403, headers={"Cache-Control": "no-store"})
        if unified_authentication() and request.method not in {"GET", "HEAD", "OPTIONS"}:
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
