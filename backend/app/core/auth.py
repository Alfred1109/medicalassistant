"""
认证模块
处理用户认证、Token验证和当前用户获取
"""
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from typing import Optional, Any
import logging
import math
from datetime import datetime
from bson import ObjectId, errors
from fastapi import WebSocket

from app.core.config import settings
from app.schemas.user import UserResponse
from app.db.mongodb import get_database
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorClient
from app.integrations.identity.config import oidc_settings
from app.integrations.identity.access import unified_authentication, trusted_origin, SESSION_COOKIE
from app.integrations.identity.service import OidcClient, OidcUnavailable

# OAuth2 password bearer for token validation
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/login", auto_error=False)


def _access_token_user_id(token: str) -> Optional[str]:
    """HTTP 与 WebSocket 共用访问令牌语义；不记录令牌内容。"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM],
                             options={"require_exp": True})
    except (JWTError, TypeError, ValueError):
        return None
    user_id = payload.get("sub")
    # 旧版访问令牌没有 token_type；带类型的令牌必须明确为 access。
    expiry = payload.get("exp")
    try:
        valid_expiry = isinstance(expiry, (int, float)) and not isinstance(expiry, bool) and math.isfinite(expiry)
    except OverflowError:
        valid_expiry = False
    if not valid_expiry or not isinstance(user_id, str) or not user_id or payload.get("token_type", "access") != "access":
        return None
    return user_id


async def request_actor_role(request: Request, database) -> Optional[str]:
    """维护门闩用的角色读取：只取 role，不走完整登录。

    不停用账号、不因令牌无效而 401——无身份时返回 None，由门闩决定是否拒绝。
    统一身份与 Bearer 两条路径的判定与历史维护门闩一致。
    """
    if unified_authentication():
        _record, actor = await OidcClient(database, oidc_settings).actor_for_session(
            request.cookies.get(SESSION_COOKIE))
        return (actor or {}).get("role")
    header = request.headers.get("authorization") or ""
    token = header[7:] if header.lower().startswith("bearer ") else ""
    user_id = _access_token_user_id(token) if token else None
    if not user_id or not ObjectId.is_valid(user_id):
        return None
    user = await database.users.find_one({"_id": ObjectId(user_id)}, {"role": 1})
    return (user or {}).get("role")


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncIOMotorDatabase = Depends(get_database)
) -> UserResponse:
    """解析JWT令牌并返回当前登录用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if unified_authentication():
        # Legacy Bearer credentials are never a fallback when the source is down.
        if request.headers.get("authorization"):
            raise credentials_exception
        try:
            record, actor = await OidcClient(db, oidc_settings).actor_for_session(request.cookies.get(SESSION_COOKIE))
        except OidcUnavailable:
            raise HTTPException(503, detail={"code": "IDENTITY_SOURCE_UNAVAILABLE"}) from None
        if record is None:
            raise credentials_exception
        if actor is None:
            raise HTTPException(403, detail={"code": "IDENTITY_BINDING_REQUIRED"})
        from app.core.user_record import user_response_from_document
        request.state.identity_subject = record["subject"]
        request.state.identity_issuer = record["issuer"]
        request.state.authenticated_actor_id = str(actor["_id"])
        request.state.authenticated_actor_role = actor["role"]
        return user_response_from_document(actor)

    user_id = _access_token_user_id(token) if token else None
    if user_id is None:
        raise credentials_exception

    from app.core.user_record import load_user_response
    user = await load_user_response(db, user_id)
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账户已被停用")
    return user

async def get_current_active_user(
    current_user: UserResponse = Depends(get_current_user)
) -> UserResponse:
    """获取当前已激活的用户"""
    if not getattr(current_user, "is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被停用"
        )
    return current_user

# 添加WebSocket用户验证函数
async def get_current_user_ws(websocket: WebSocket, db: AsyncIOMotorClient) -> Optional[dict]:
    """
    从WebSocket连接中获取当前用户信息
    WebSocket连接应在查询参数或cookie中包含token
    """
    if unified_authentication():
        if (not trusted_origin(websocket.headers.get("origin")) or websocket.query_params.get("token")
                or websocket.headers.get("authorization")):
            return None
        try:
            _, actor = await OidcClient(db, oidc_settings).actor_for_session(websocket.cookies.get(SESSION_COOKIE))
            return actor
        except OidcUnavailable:
            return None
    token = None
    
    # 首先尝试从查询参数中获取token
    try:
        token = websocket.query_params.get("token")
    except Exception:
        pass
    
    # 如果查询参数中没有token，尝试从cookie中获取
    if not token:
        token = websocket.cookies.get(settings.TOKEN_COOKIE_NAME)
    
    if not token:
        return None
    
    user_id = _access_token_user_id(token)
    if user_id is None or not ObjectId.is_valid(user_id):
        return None

    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if user is None or not user.get("is_active", True):
        return None
    
    return user
