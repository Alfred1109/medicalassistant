from typing import Dict, List, Set, Optional, Callable, Any, Union
from functools import wraps
import logging
from datetime import datetime
from fastapi import Depends, HTTPException, status, Request, Path
from bson.objectid import ObjectId

from app.schemas.user import UserResponse
from app.core.auth import get_current_active_user
from app.core.permissions import Permission, PermissionChecker
from app.core.permission_audit import get_permission_tracker
from app.db.mongodb import get_database

logger = logging.getLogger(__name__)

class ResourcePermission:
    """
    资源级权限控制
    提供对特定资源实例的细粒度权限控制
    """
    
    @staticmethod
    def require_resource_permission(
        resource_type: str,
        permission: str,
        resource_id_param: str = "resource_id",
        owner_field: Optional[str] = "owner_id",
        check_ownership: bool = True
    ):
        """
        要求对特定资源实例的权限
        
        参数:
        - resource_type: 资源类型
        - permission: 所需权限
        - resource_id_param: 路径参数中资源ID的参数名
        - owner_field: 资源中表示所有者的字段名
        - check_ownership: 是否检查资源所有权
        """
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # 获取当前用户
                current_user = kwargs.get("current_user")
                if not current_user:
                    for arg in args:
                        if isinstance(arg, UserResponse):
                            current_user = arg
                            break
                
                if not current_user:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="需要认证"
                    )
                
                # 获取资源ID
                resource_id = kwargs.get(resource_id_param)
                if not resource_id:
                    for key, value in kwargs.items():
                        if key.endswith("_id") and resource_id_param in key:
                            resource_id = value
                            break
                
                # 获取数据库连接
                db = kwargs.get("db")
                if db is None:
                    for arg in args:
                        if hasattr(arg, "command"):  # MongoDB数据库连接通常有command方法
                            db = arg
                            break
                
                if db is None:
                    # 尝试从依赖中获取
                    db = await get_database()
                
                # 记录审计
                request = kwargs.get("request")
                ip_address = None
                if request and hasattr(request, 'client') and request.client:
                    ip_address = request.client.host
                
                # 获取权限跟踪器
                permission_tracker = await get_permission_tracker(db)
                
                # 系统管理员直接通过
                if current_user.role == "admin":
                    await permission_tracker.track_permission_check(
                        user_id=current_user.id,
                        permission=permission,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        is_granted=True,
                        ip_address=ip_address,
                        details={"reason": "admin_role"}
                    )
                    return await func(*args, **kwargs)
                
                # 检查全局权限
                if PermissionChecker.has_permission(current_user, permission):
                    await permission_tracker.track_permission_check(
                        user_id=current_user.id,
                        permission=permission,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        is_granted=True,
                        ip_address=ip_address,
                        details={"reason": "global_permission"}
                    )
                    return await func(*args, **kwargs)
                
                # 检查资源所有权
                if check_ownership and resource_id and db is not None:
                    try:
                        # 获取资源集合
                        collection = db[resource_type]
                        # 查询资源
                        resource = await collection.find_one({"_id": ObjectId(resource_id)})
                        
                        if resource:
                            # 检查所有权
                            if owner_field in resource and resource[owner_field] == current_user.id:
                                await permission_tracker.track_permission_check(
                                    user_id=current_user.id,
                                    permission=permission,
                                    resource_type=resource_type,
                                    resource_id=resource_id,
                                    is_granted=True,
                                    ip_address=ip_address,
                                    details={"reason": "resource_ownership"}
                                )
                                return await func(*args, **kwargs)
                            
                            # 检查共享权限（如适用）
                            if "shared_with" in resource and isinstance(resource["shared_with"], list):
                                if current_user.id in resource["shared_with"]:
                                    # 检查共享权限级别
                                    if "shared_permissions" in resource and isinstance(resource["shared_permissions"], dict):
                                        shared_perms = resource["shared_permissions"].get(current_user.id, [])
                                        if permission in shared_perms:
                                            await permission_tracker.track_permission_check(
                                                user_id=current_user.id,
                                                permission=permission,
                                                resource_type=resource_type,
                                                resource_id=resource_id,
                                                is_granted=True,
                                                ip_address=ip_address,
                                                details={"reason": "resource_sharing"}
                                            )
                                            return await func(*args, **kwargs)
                    except Exception as e:
                        logger.error(f"Error checking resource permission: {str(e)}")
                
                # 权限检查失败
                await permission_tracker.track_permission_check(
                    user_id=current_user.id,
                    permission=permission,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    is_granted=False,
                    ip_address=ip_address,
                    details={"reason": "permission_denied"}
                )
                
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"没有权限操作此{resource_type}资源"
                )
            
            return wrapper
        return decorator
    
    @staticmethod
    def check_data_permission(
        current_user: UserResponse,
        data: Dict[str, Any],
        permission: str,
        resource_type: str,
        owner_field: str = "owner_id"
    ) -> bool:
        """
        检查用户对数据的权限
        
        参数:
        - current_user: 当前用户
        - data: 要检查的数据
        - permission: 所需权限
        - resource_type: 资源类型
        - owner_field: 数据中表示所有者的字段名
        
        返回:
        - 是否有权限
        """
        # 系统管理员有所有权限
        if current_user.role == "admin":
            return True
        
        # 检查全局权限
        if PermissionChecker.has_permission(current_user, permission):
            return True
        
        # 检查所有权
        if owner_field in data and data[owner_field] == current_user.id:
            return True
        
        # 检查共享权限
        if "shared_with" in data and isinstance(data["shared_with"], list):
            if current_user.id in data["shared_with"]:
                # 检查共享权限级别
                if "shared_permissions" in data and isinstance(data["shared_permissions"], dict):
                    shared_perms = data["shared_permissions"].get(current_user.id, [])
                    if permission in shared_perms:
                        return True
        
        return False

    @staticmethod
    async def filter_permitted_resources(
        current_user: UserResponse,
        resources: List[Dict[str, Any]],
        permission: str,
        owner_field: str = "owner_id"
    ) -> List[Dict[str, Any]]:
        """
        过滤用户有权访问的资源
        
        参数:
        - current_user: 当前用户
        - resources: 资源列表
        - permission: 所需权限
        - owner_field: 资源中表示所有者的字段名
        
        返回:
        - 过滤后的资源列表
        """
        # 系统管理员可以访问所有资源
        if current_user.role == "admin":
            return resources
        
        # 如果有全局权限，可以访问所有资源
        if PermissionChecker.has_permission(current_user, permission):
            return resources
        
        # 过滤用户拥有或共享的资源
        permitted_resources = []
        for resource in resources:
            # 检查所有权
            if owner_field in resource and resource[owner_field] == current_user.id:
                permitted_resources.append(resource)
                continue
            
            # 检查共享权限
            if "shared_with" in resource and isinstance(resource["shared_with"], list):
                if current_user.id in resource["shared_with"]:
                    # 检查共享权限级别
                    if "shared_permissions" in resource and isinstance(resource["shared_permissions"], dict):
                        shared_perms = resource["shared_permissions"].get(current_user.id, [])
                        if permission in shared_perms:
                            permitted_resources.append(resource)
        
        return permitted_resources


def require_object_permission(
    obj_key: str,
    permission: str,
    resource_type: str,
    owner_field: str = "owner_id",
):
    """
    装饰器：要求对对象的特定权限
    
    参数:
    - obj_key: 函数参数中对象的名称
    - permission: 所需权限
    - resource_type: 资源类型
    - owner_field: 对象中表示所有者的字段名
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取当前用户
            current_user = kwargs.get("current_user")
            if not current_user:
                for arg in args:
                    if isinstance(arg, UserResponse):
                        current_user = arg
                        break
            
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="需要认证"
                )
            
            # 获取对象
            obj = kwargs.get(obj_key)
            if not obj:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"缺少参数 {obj_key}"
                )
            
            # 检查权限
            has_permission = ResourcePermission.check_data_permission(
                current_user=current_user,
                data=obj.dict() if hasattr(obj, "dict") else obj,
                permission=permission,
                resource_type=resource_type,
                owner_field=owner_field
            )
            
            if not has_permission:
                # 获取请求对象以记录审计
                request = kwargs.get("request")
                ip_address = None
                if request and hasattr(request, 'client') and request.client:
                    ip_address = request.client.host
                
                # 获取数据库连接和权限跟踪器
                db = kwargs.get("db")
                if not db:
                    for arg in args:
                        if hasattr(arg, "command"):
                            db = arg
                            break
                
                if db:
                    permission_tracker = await get_permission_tracker(db)
                    # 记录权限检查失败
                    await permission_tracker.track_permission_check(
                        user_id=current_user.id,
                        permission=permission,
                        resource_type=resource_type,
                        resource_id=getattr(obj, "id", None),
                        is_granted=False,
                        ip_address=ip_address,
                        details={"reason": "object_permission_denied"}
                    )
                
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"没有权限操作此{resource_type}"
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator 