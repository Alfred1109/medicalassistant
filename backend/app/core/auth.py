"""
认证模块
处理用户认证、Token验证和当前用户获取
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from typing import Optional, Any
import logging
from datetime import datetime
from bson import ObjectId
from fastapi import WebSocket

from app.core.config import settings
from app.schemas.user import UserResponse, TokenData, TokenPayload
from app.db.mongodb import get_database
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorClient

# OAuth2 password bearer for token validation
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/users/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncIOMotorDatabase = Depends(get_database)
) -> UserResponse:
    """解析JWT令牌并返回当前登录用户"""
    logging.info(f"验证用户令牌: {token[:15]}...")
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # 解码JWT令牌
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        logging.info(f"令牌解析成功，用户ID: {user_id}")
        
        if user_id is None:
            logging.warning("令牌中没有用户ID (sub)")
            raise credentials_exception
            
        token_data = TokenData(user_id=user_id)
    except JWTError as e:
        logging.error(f"令牌解析错误: {str(e)}")
        raise credentials_exception
        
    # 动态导入UserService，避免循环导入
    from app.services.user_service import UserService
    
    # 直接创建UserService
    user_service = UserService(db=db)
    
    # 获取用户信息
    try:
        user = await user_service.get_user_by_id(token_data.user_id)
        if user is None:
            logging.warning(f"未找到用户(ID: {token_data.user_id})")
            raise credentials_exception
        logging.info(f"成功获取用户: {user.email}, 角色: {user.role}")
        return user
    except Exception as e:
        logging.error(f"获取用户时发生错误: {str(e)}")
        raise credentials_exception

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
    
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
            
        token_data = TokenPayload(**payload)
        if token_data.exp and datetime.fromtimestamp(token_data.exp) < datetime.now():
            return None
    except JWTError:
        return None
    
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if user is None:
        return None
    
    return user 