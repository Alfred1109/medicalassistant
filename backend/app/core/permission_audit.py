from typing import Callable, Optional, Dict, Any, List
from fastapi import Request, Response
import logging
from datetime import datetime
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.services.audit_log_service import AuditLogService
from app.schemas.audit_log import AuditLogCreate
from app.core.permissions import AUDITED_PERMISSIONS

logger = logging.getLogger(__name__)

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
        path = request.url.path
        
        # 排除不需要审计的路径
        if any(path.startswith(prefix) for prefix in self.exclude_paths):
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
        
        # 尝试获取用户信息
        user_id = None
        try:
            # 用户信息可能在请求头或会话中
            if "authorization" in request.headers:
                # 实际实现中需要从token中提取用户ID
                # 这里仅作为示例
                token = request.headers["authorization"].split(" ")[1]
                # 从token中提取用户ID的逻辑
                # user_id = decode_token(token)["sub"]
                pass
        except Exception as e:
            logger.error(f"Failed to extract user info from request: {str(e)}")
        
        # 尝试获取请求体
        request_body = None
        if method in ["POST", "PUT", "PATCH"]:
            try:
                # 读取请求体，但要确保不影响后续处理
                request_body = await request.body()
                # 重置request body以供后续中间件/路由处理
                await request._receive()
            except Exception as e:
                logger.error(f"Failed to read request body: {str(e)}")
        
        # 处理请求，记录响应状态
        start_time = datetime.utcnow()
        response = await call_next(request)
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        # 确定操作结果状态
        status = "success" if response.status_code < 400 else "failure"
        
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
            
            # 如果有请求体，添加到详情中
            if request_body:
                try:
                    # 可能需要解析请求体
                    # body_json = json.loads(request_body)
                    # 在实际应用中，可能需要过滤或脱敏敏感信息
                    # details["request"] = body_json
                    pass
                except:
                    pass
            
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
                if self.db:
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
            if self.db:
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
    if not db:
        from app.db.mongodb import get_database
        try:
            db = await anext(get_database())
        except Exception as e:
            logger.error(f"获取数据库连接失败: {str(e)}")
    
    return ResourcePermissionTracker(db) 