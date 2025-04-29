"""
权限控制模块
实现基于角色的权限控制和细粒度权限管理
"""
from typing import Dict, List, Set, Optional, Callable, Any
from fastapi import Depends, HTTPException, status, Request
from functools import wraps
import logging
from datetime import datetime

from app.schemas.user import UserResponse
from app.services.audit_log_service import AuditLogService
from app.core.auth import get_current_active_user

# 配置日志
logger = logging.getLogger(__name__)

# 定义系统权限
class Permission:
    # 用户管理权限
    USER_CREATE = "user:create"
    USER_READ = "user:read"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"
    
    # 患者管理权限
    PATIENT_CREATE = "patient:create"
    PATIENT_READ = "patient:read"
    PATIENT_UPDATE = "patient:update"
    PATIENT_DELETE = "patient:delete"
    
    # 医生管理权限
    DOCTOR_CREATE = "doctor:create"
    DOCTOR_READ = "doctor:read"
    DOCTOR_UPDATE = "doctor:update"
    DOCTOR_DELETE = "doctor:delete"
    
    # 健康管理师权限
    HEALTH_MANAGER_CREATE = "health_manager:create"
    HEALTH_MANAGER_READ = "health_manager:read"
    HEALTH_MANAGER_UPDATE = "health_manager:update"
    HEALTH_MANAGER_DELETE = "health_manager:delete"
    
    # 康复计划权限
    REHAB_PLAN_CREATE = "rehab_plan:create"
    REHAB_PLAN_READ = "rehab_plan:read"
    REHAB_PLAN_UPDATE = "rehab_plan:update"
    REHAB_PLAN_DELETE = "rehab_plan:delete"
    REHAB_PLAN_APPROVE = "rehab_plan:approve"
    
    # 健康记录权限
    HEALTH_RECORD_CREATE = "health_record:create"
    HEALTH_RECORD_READ = "health_record:read"
    HEALTH_RECORD_UPDATE = "health_record:update"
    HEALTH_RECORD_DELETE = "health_record:delete"
    
    # 健康档案高级权限
    VIEW_ANY_HEALTH_RECORD = "health_record:view_any"  # 查看任何患者的健康档案
    MANAGE_FOLLOW_UP = "follow_up:manage"  # 管理随访记录
    CREATE_LAB_RESULT = "health_data:create_lab_result"  # 创建实验室检查结果
    
    # 组织机构权限
    ORGANIZATION_CREATE = "organization:create"
    ORGANIZATION_READ = "organization:read"
    ORGANIZATION_UPDATE = "organization:update"
    ORGANIZATION_DELETE = "organization:delete"
    
    # 设备管理权限
    DEVICE_CREATE = "device:create"
    DEVICE_READ = "device:read"
    DEVICE_UPDATE = "device:update"
    DEVICE_DELETE = "device:delete"
    DEVICE_DATA_READ = "device_data:read"
    
    # 系统管理权限
    SYSTEM_ADMIN = "system:admin"
    SYSTEM_CONFIG = "system:config"
    
    # LLM/Agent权限
    AGENT_CREATE = "agent:create"
    AGENT_READ = "agent:read"
    AGENT_UPDATE = "agent:update"
    AGENT_DELETE = "agent:delete"
    AGENT_EXECUTE = "agent:execute"
    
    # 审计权限
    AUDIT_LOG_READ = "audit_log:read"
    AUDIT_LOG_EXPORT = "audit_log:export"


# 基于角色的默认权限
ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "admin": [
        # 管理员拥有所有权限
        Permission.SYSTEM_ADMIN,
        Permission.SYSTEM_CONFIG,
        Permission.USER_CREATE,
        Permission.USER_READ,
        Permission.USER_UPDATE,
        Permission.USER_DELETE,
        Permission.PATIENT_CREATE,
        Permission.PATIENT_READ,
        Permission.PATIENT_UPDATE,
        Permission.PATIENT_DELETE,
        Permission.DOCTOR_CREATE,
        Permission.DOCTOR_READ,
        Permission.DOCTOR_UPDATE,
        Permission.DOCTOR_DELETE,
        Permission.HEALTH_MANAGER_CREATE,
        Permission.HEALTH_MANAGER_READ,
        Permission.HEALTH_MANAGER_UPDATE,
        Permission.HEALTH_MANAGER_DELETE,
        Permission.REHAB_PLAN_CREATE,
        Permission.REHAB_PLAN_READ,
        Permission.REHAB_PLAN_UPDATE,
        Permission.REHAB_PLAN_DELETE,
        Permission.REHAB_PLAN_APPROVE,
        Permission.HEALTH_RECORD_CREATE,
        Permission.HEALTH_RECORD_READ,
        Permission.HEALTH_RECORD_UPDATE,
        Permission.HEALTH_RECORD_DELETE,
        Permission.ORGANIZATION_CREATE,
        Permission.ORGANIZATION_READ,
        Permission.ORGANIZATION_UPDATE,
        Permission.ORGANIZATION_DELETE,
        Permission.DEVICE_CREATE,
        Permission.DEVICE_READ,
        Permission.DEVICE_UPDATE,
        Permission.DEVICE_DELETE,
        Permission.DEVICE_DATA_READ,
        Permission.AGENT_CREATE,
        Permission.AGENT_READ,
        Permission.AGENT_UPDATE,
        Permission.AGENT_DELETE,
        Permission.AGENT_EXECUTE,
        Permission.VIEW_ANY_HEALTH_RECORD,
        Permission.MANAGE_FOLLOW_UP,
        Permission.CREATE_LAB_RESULT,
        Permission.AUDIT_LOG_READ,
        Permission.AUDIT_LOG_EXPORT,
    ],
    "doctor": [
        Permission.PATIENT_READ,
        Permission.HEALTH_RECORD_READ,
        Permission.HEALTH_RECORD_CREATE,
        Permission.HEALTH_RECORD_UPDATE,
        Permission.REHAB_PLAN_READ,
        Permission.REHAB_PLAN_CREATE,
        Permission.REHAB_PLAN_UPDATE,
        Permission.DEVICE_DATA_READ,
        Permission.AGENT_READ,
        Permission.AGENT_EXECUTE,
        Permission.MANAGE_FOLLOW_UP,
        Permission.CREATE_LAB_RESULT,
    ],
    "health_manager": [
        Permission.PATIENT_READ,
        Permission.HEALTH_RECORD_READ,
        Permission.HEALTH_RECORD_CREATE,
        Permission.DEVICE_DATA_READ,
        Permission.AGENT_READ,
        Permission.AGENT_EXECUTE,
    ],
    "patient": [
        # 患者只能查看自己的信息
        Permission.HEALTH_RECORD_READ,
        Permission.AGENT_READ,
        Permission.AGENT_EXECUTE,
        Permission.DEVICE_DATA_READ,
    ]
}

# 定义需要记录审计日志的关键权限
AUDITED_PERMISSIONS = [
    Permission.SYSTEM_ADMIN,
    Permission.USER_CREATE,
    Permission.USER_DELETE,
    Permission.DOCTOR_CREATE,
    Permission.DOCTOR_DELETE,
    Permission.HEALTH_MANAGER_CREATE,
    Permission.HEALTH_MANAGER_DELETE,
    Permission.VIEW_ANY_HEALTH_RECORD,
    Permission.ORGANIZATION_CREATE,
    Permission.ORGANIZATION_DELETE,
    Permission.AUDIT_LOG_READ,
    Permission.AUDIT_LOG_EXPORT,
]


class PermissionChecker:
    """
    权限检查类，用于验证用户是否具有特定权限
    """
    @staticmethod
    def has_permission(user: UserResponse, permission: str) -> bool:
        """检查用户是否具有特定权限"""
        # 获取用户角色的默认权限
        role_perms = ROLE_PERMISSIONS.get(user.role, [])
        
        # 检查特定权限
        if permission in role_perms:
            return True
            
        # 检查特殊情况：
        # 1. 管理员拥有所有权限
        if user.role == "admin" or Permission.SYSTEM_ADMIN in role_perms:
            return True
            
        # 2. 用户自身资源访问权限
        if permission.endswith(":read") and user.id in permission:
            return True
            
        # 检查用户自定义权限（未来扩展）
        # user_custom_perms = getattr(user, "permissions", [])
        # if permission in user_custom_perms:
        #     return True
            
        return False

    @staticmethod
    async def check_permission_with_audit(
        user: UserResponse, 
        permission: str, 
        resource_id: Optional[str] = None,
        db = None,
        request: Optional[Request] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        检查用户是否具有特定权限，并记录审计日志
        
        参数:
        - user: 当前用户
        - permission: 要检查的权限
        - resource_id: 资源ID（可选）
        - db: 数据库连接（可选，如果需要记录审计日志）
        - request: HTTP请求对象（可选，用于获取IP地址）
        - details: 额外的详细信息（可选）
        
        返回:
        - bool: 是否具有权限
        """
        has_permission = PermissionChecker.has_permission(user, permission)
        
        # 记录审计日志（仅针对重要权限或权限检查失败的情况）
        if db and (not has_permission or permission in AUDITED_PERMISSIONS):
            try:
                # 获取IP地址
                ip_address = None
                if request and hasattr(request, 'client') and request.client:
                    ip_address = request.client.host
                
                # 创建审计日志服务
                audit_service = AuditLogService(db)
                
                # 记录权限检查日志
                await audit_service.log_permission_check(
                    user_id=user.id,
                    permission=permission,
                    resource_id=resource_id,
                    is_granted=has_permission,
                    ip_address=ip_address,
                    details=details
                )
            except Exception as e:
                # 记录日志错误，但不影响权限检查结果
                logger.error(f"Failed to create audit log: {str(e)}")
        
        return has_permission


# 权限依赖函数，使用方式：
# @router.get("/endpoint")
# async def endpoint(current_user: User = Depends(get_current_user),
#                   _: None = Depends(require_permission(Permission.SOME_PERMISSION))):
def require_permission(permission: str, resource_id: Optional[str] = None):
    """
    创建权限检查的依赖函数
    
    参数:
    - permission: 要检查的权限
    - resource_id: 资源ID（可选）
    
    用法示例:
    @router.get("/users")
    async def get_users(
        current_user: User = Depends(get_current_user),
        _: None = Depends(require_permission(Permission.USER_READ))
    ):
        # 如果用户没有权限，会抛出HTTPException
        # 实现代码...
    """
    
    async def check_permission(
        current_user: UserResponse = Depends(get_current_active_user),
        request: Request = None,
        db = None
    ):
        # 使用带审计功能的权限检查
        has_permission = await PermissionChecker.check_permission_with_audit(
            user=current_user,
            permission=permission,
            resource_id=resource_id,
            db=db,
            request=request,
            details={"endpoint": request.url.path if request else None}
        )
        
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"您没有执行此操作的权限：{permission}"
            )
    
    return check_permission


# 获取当前用户的所有权限
def get_user_permissions(user: UserResponse) -> Set[str]:
    """获取用户所有的权限"""
    # 获取角色默认权限
    permissions = set(ROLE_PERMISSIONS.get(user.role, []))
    
    # 如果是管理员，拥有所有权限
    if user.role == "admin":
        # 将所有权限类型添加到结果中
        for attr in dir(Permission):
            if not attr.startswith('_'):
                permissions.add(getattr(Permission, attr))
    
    # 将来可以从用户对象中获取自定义权限
    # if hasattr(user, 'permissions'):
    #     permissions.update(user.permissions)
    
    return permissions 