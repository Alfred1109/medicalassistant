"""
权限控制模块
实现基于角色的权限控制和细粒度权限管理
"""
from typing import Dict, List, Set, Optional, Callable, Any
from fastapi import Depends, HTTPException, status
from functools import wraps

from app.schemas.user import UserResponse

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
    ],
    "doctor": [
        # 医生权限
        Permission.USER_READ,
        Permission.PATIENT_READ,
        Permission.PATIENT_UPDATE,
        Permission.REHAB_PLAN_CREATE,
        Permission.REHAB_PLAN_READ,
        Permission.REHAB_PLAN_UPDATE,
        Permission.REHAB_PLAN_APPROVE,
        Permission.HEALTH_RECORD_CREATE,
        Permission.HEALTH_RECORD_READ,
        Permission.HEALTH_RECORD_UPDATE,
        Permission.VIEW_ANY_HEALTH_RECORD,
        Permission.MANAGE_FOLLOW_UP,
        Permission.CREATE_LAB_RESULT,
        Permission.DEVICE_READ,
        Permission.DEVICE_DATA_READ,
        Permission.AGENT_READ,
        Permission.AGENT_EXECUTE,
    ],
    "health_manager": [
        # 健康管理师权限
        Permission.USER_READ,
        Permission.PATIENT_READ,
        Permission.PATIENT_UPDATE,
        Permission.REHAB_PLAN_READ,
        Permission.REHAB_PLAN_UPDATE,
        Permission.HEALTH_RECORD_CREATE,
        Permission.HEALTH_RECORD_READ,
        Permission.HEALTH_RECORD_UPDATE,
        Permission.VIEW_ANY_HEALTH_RECORD,
        Permission.MANAGE_FOLLOW_UP,
        Permission.DEVICE_READ,
        Permission.DEVICE_DATA_READ,
        Permission.AGENT_READ,
        Permission.AGENT_EXECUTE,
    ],
    "patient": [
        # 患者权限
        Permission.USER_READ,
        Permission.REHAB_PLAN_READ,
        Permission.HEALTH_RECORD_READ,
        Permission.DEVICE_READ,
        Permission.DEVICE_DATA_READ,
        Permission.AGENT_READ,
        Permission.AGENT_EXECUTE,
    ],
}

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
    def require_permission(permission: str):
        """
        权限要求装饰器
        用于API端点，要求用户具有特定权限
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # 获取当前用户
                current_user = kwargs.get("current_user")
                if not current_user:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="需要认证",
                    )
                
                # 检查权限
                if not PermissionChecker.has_permission(current_user, permission):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"权限不足: 需要 {permission} 权限",
                    )
                    
                return await func(*args, **kwargs)
            return wrapper
        return decorator
        
    @staticmethod
    def require_any_permission(permissions: List[str]):
        """
        要求用户具有任意一个列出的权限
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # 获取当前用户
                current_user = kwargs.get("current_user")
                if not current_user:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="需要认证",
                    )
                
                # 检查是否有任一权限
                has_any = any(PermissionChecker.has_permission(current_user, perm) for perm in permissions)
                if not has_any:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"权限不足: 需要以下权限之一: {', '.join(permissions)}",
                    )
                    
                return await func(*args, **kwargs)
            return wrapper
        return decorator
        
    @staticmethod
    def require_all_permissions(permissions: List[str]):
        """
        要求用户具有所有列出的权限
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # 获取当前用户
                current_user = kwargs.get("current_user")
                if not current_user:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="需要认证",
                    )
                
                # 检查是否有所有权限
                missing_perms = [perm for perm in permissions if not PermissionChecker.has_permission(current_user, perm)]
                if missing_perms:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"权限不足: 缺少以下权限: {', '.join(missing_perms)}",
                    )
                    
                return await func(*args, **kwargs)
            return wrapper
        return decorator


# FastAPI依赖项，用于检查特定权限
def has_permission(permission: str):
    """
    检查用户是否具有特定权限的依赖项
    """
    async def dependency(current_user: UserResponse):
        if not PermissionChecker.has_permission(current_user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足: 需要 {permission} 权限",
            )
        return current_user
    return dependency


def has_any_permission(permissions: List[str]):
    """
    检查用户是否具有任一权限的依赖项
    """
    async def dependency(current_user: UserResponse):
        has_any = any(PermissionChecker.has_permission(current_user, perm) for perm in permissions)
        if not has_any:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足: 需要以下权限之一: {', '.join(permissions)}",
            )
        return current_user
    return dependency


def has_all_permissions(permissions: List[str]):
    """
    检查用户是否具有所有权限的依赖项
    """
    async def dependency(current_user: UserResponse):
        missing_perms = [perm for perm in permissions if not PermissionChecker.has_permission(current_user, perm)]
        if missing_perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足: 缺少以下权限: {', '.join(missing_perms)}",
            )
        return current_user
    return dependency 