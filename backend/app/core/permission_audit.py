from typing import Callable, Optional, Dict, Any, List, Tuple
from fastapi import Request, Response
from jose import JWTError, jwt
from math import isfinite
import logging
from datetime import datetime
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import settings
from app.services.audit_log_service import AuditLogService
from app.schemas.audit_log import AuditLogCreate
from app.core.permissions import AUDITED_PERMISSIONS
from app.integrations.identity.access import unified_authentication

logger = logging.getLogger(__name__)


def _extract_identity_from_token(token: str) -> Tuple[Optional[str], Optional[str]]:
    """旁路审计用：解码访问令牌，返回 (user_id, role)。

    解码失败或令牌无效时返回 (None, None)，由调用方记为 anonymous。
    语义与 app.core.auth._access_token_user_id 保持一致；不记录令牌内容。
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM],
            options={"require_exp": True},
        )
    except (JWTError, TypeError, ValueError):
        return None, None
    user_id = payload.get("sub")
    expiry = payload.get("exp")
    try:
        valid_expiry = isinstance(expiry, (int, float)) and not isinstance(expiry, bool) and isfinite(expiry)
    except OverflowError:
        valid_expiry = False
    # 旧版访问令牌没有 token_type；带类型的令牌必须明确为 access。
    if not valid_expiry or not isinstance(user_id, str) or not user_id \
            or payload.get("token_type", "access") != "access":
        return None, None
    role = payload.get("role")
    return user_id, (role if isinstance(role, str) and role else None)

class PermissionAuditMiddleware(BaseHTTPMiddleware):
    """
    权限审计中间件
    拦截API请求，记录与权限相关的操作
    """
    
    def __init__(
        self, 
        app: ASGIApp,
        audit_paths: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None
    ):
        super().__init__(app)
        # 默认监控的路径前缀
        self.audit_paths = audit_paths or [
            "/api/users",
            "/api/roles",
            "/api/permissions",
            "/api/audit-logs"
        ]
        # 排除的路径前缀
        self.exclude_paths = exclude_paths or [
            "/api/health", 
            "/docs", 
            "/openapi.json"
        ]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 检查是否需要审计此路径
        path = request.scope["path"]

        # 排除不需要审计的路径
        if any(path.startswith(prefix) for prefix in self.exclude_paths):
            return await call_next(request)

        # CORS 预检不承载业务语义（中间件在无 CORS 的裸应用上使用时也会命中），不产生审计噪音
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # 确定是否需要审计
        need_audit = False
        resource_type = None
        
        # 检查是否是需要审计的路径
        for prefix in self.audit_paths:
            if path.startswith(prefix):
                need_audit = True
                # 提取资源类型
                parts = path.split("/")
                if len(parts) > 2:
                    resource_type = parts[2]  # 例如/api/users -> users
                break
        
        # 如果不需要审计，直接处理请求
        if not need_audit:
            return await call_next(request)
        
        # 获取请求方法
        method = request.method
        
        # 映射HTTP方法到操作类型
        action_map = {
            "GET": "access",
            "POST": "create",
            "PUT": "update",
            "PATCH": "update",
            "DELETE": "delete"
        }
        action = action_map.get(method, "access")
        
        # 提取操作目标ID
        resource_id = None
        parts = path.split("/")
        if len(parts) > 3 and parts[3] and parts[3].isalnum():
            resource_id = parts[3]
        
        # 尝试获取用户信息（旁路审计提取，不做鉴权判断；失败时保持匿名）
        user_id = None
        role = None
        token = None
        auth_header = request.headers.get("authorization")
        if auth_header:
            scheme, _, credentials = auth_header.partition(" ")
            if scheme.lower() == "bearer" and credentials.strip():
                token = credentials.strip()
        if not token:
            # 部分客户端通过 cookie 携带令牌（与 WebSocket 认证一致）
            token = request.cookies.get(settings.TOKEN_COOKIE_NAME)
        if token and not unified_authentication():
            user_id, role = _extract_identity_from_token(token)
            if user_id is None:
                logger.warning("Audit identity extraction failed: invalid or expired access token")
        
        # 审计为旁路记录：不消费请求体，避免阻塞等待下游 receive 事件
        # 或影响路由对请求体的读取（此前预留的 body 采集逻辑从未被使用，已移除）。
        
        # 处理请求，记录响应状态
        start_time = datetime.utcnow()
        response = await call_next(request)
        duration = (datetime.utcnow() - start_time).total_seconds()
        if unified_authentication():
            user_id = getattr(request.state, "authenticated_actor_id", None)
            role = getattr(request.state, "authenticated_actor_role", None)
        
        # 确定操作结果状态
        status = "success" if response.status_code < 400 else "failure"
        
        # 审计为旁路记录：仅在应用已完成数据库连接时落库，绝不从审计路径主动发起
        # 连接（否则无库环境下每个被审计请求都会阻塞到 serverSelectionTimeoutMS）。
        # 未连接时跳过记录，业务响应不受影响；连接后由下方 try/except 兜底落库失败。
        from app.db.mongodb import db as app_db
        if not app_db.is_connected():
            return response

        # 检查是否需要记录审计日志
        try:
            # 获取数据库连接
            # 注意：实际实现中可能需要从应用状态获取数据库连接
            from app.db.mongodb import get_database
            db = await anext(get_database())
            audit_service = AuditLogService(db)
            
            # 记录审计日志
            details = {
                "path": path,
                "method": method,
                "duration_ms": round(duration * 1000),
                "status_code": response.status_code
            }

            # 令牌中携带角色时写入审计详情，便于归因分析
            if role:
                details["role"] = role
            
            # 创建审计日志
            await audit_service.create_log(
                log_data=AuditLogCreate(
                    user_id=user_id or "anonymous",
                    action=action,
                    resource_type=resource_type or "unknown",
                    resource_id=resource_id,
                    status=status,
                    details=details
                ),
                ip_address=request.client.host if request.client else None
            )
        except Exception as e:
            logger.error(f"Failed to create audit log: {str(e)}")
        
        return response


class ResourcePermissionTracker:
    """
    资源权限跟踪器
    用于记录对特定资源的权限访问
    通过装饰器方式应用于需要细粒度权限审计的路由
    """
    
    def __init__(self, db=None):
        self.db = db
    
    async def track_permission_check(
        self,
        user_id: str,
        permission: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        is_granted: bool = True,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        记录权限检查结果
        
        参数:
        - user_id: 用户ID
        - permission: 检查的权限
        - resource_type: 资源类型
        - resource_id: 资源ID
        - is_granted: 是否授予权限
        - ip_address: IP地址
        - details: 其他详细信息
        """
        # 关键权限或访问失败时才记录
        if permission in AUDITED_PERMISSIONS or not is_granted:
            try:
                if self.db is not None:
                    audit_service = AuditLogService(self.db)
                    await audit_service.log_permission_check(
                        user_id=user_id,
                        permission=permission,
                        resource_id=resource_id,
                        is_granted=is_granted,
                        ip_address=ip_address,
                        details={
                            "resource_type": resource_type,
                            **(details or {})
                        }
                    )
            except Exception as e:
                logger.error(f"Failed to track permission check: {str(e)}")
    
    async def track_resource_access(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        success: bool = True,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        记录资源访问
        
        参数:
        - user_id: 用户ID
        - resource_type: 资源类型
        - resource_id: 资源ID
        - action: 操作类型 (create, read, update, delete)
        - success: 操作是否成功
        - ip_address: IP地址
        - details: 其他详细信息
        """
        try:
            if self.db is not None:
                audit_service = AuditLogService(self.db)
                await audit_service.create_log(
                    log_data=AuditLogCreate(
                        user_id=user_id,
                        action=action,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        status="success" if success else "failure",
                        details=details or {}
                    ),
                    ip_address=ip_address
                )
        except Exception as e:
            logger.error(f"Failed to track resource access: {str(e)}")


# 创建单例实例以便在应用中使用
async def get_permission_tracker(db=None):
    """获取权限跟踪器实例"""
    if db is None:
        from app.db.mongodb import get_database
        try:
            db = await anext(get_database())
        except Exception as e:
            logger.error(f"获取数据库连接失败: {str(e)}")
    
    return ResourcePermissionTracker(db)
