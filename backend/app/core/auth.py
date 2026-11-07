"""
认证模块
处理用户认证、Token验证和当前用户获取
"""
from fastapi import Depends, HTTPException, status
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

# OAuth2 password bearer for token validation
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/login")


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


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncIOMotorDatabase = Depends(get_database)
) -> UserResponse:
    """解析JWT令牌并返回当前登录用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    user_id = _access_token_user_id(token)
    if user_id is None:
        raise credentials_exception
        
    # 动态导入UserService，避免循环导入
    from app.services.user_service import UserService
    
    # 直接创建UserService
    user_service = UserService(db=db)
    
    # 获取用户信息
    user = await user_service.get_user_by_id(user_id)
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
    token = None
    
    # 首先尝试从查询参数中获取token
    try:
        token = websocket.query_params.get("token")
    except Exception:
        pass
    
    # 如果查询参数中没有token，尝试从cookie中获取
    if not token:
        try:
            cookies = websocket.cookies
            token = cookies.get(settings.TOKEN_COOKIE_NAME)
        except Exception:
            pass
    
    if not token:
        return None
    
    user_id = _access_token_user_id(token)
    if user_id is None or not ObjectId.is_valid(user_id):
        return None

    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if user is None or not user.get("is_active", True):
        return None
    
    return user
