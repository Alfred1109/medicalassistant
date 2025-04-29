from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from app.core.auth import get_current_active_user
from app.core.permissions import Permission, PermissionChecker
from app.schemas.user import UserResponse
from app.schemas.audit_log import AuditLogFilter, AuditLogList, AuditLogResponse
from app.services.audit_log_service import AuditLogService
from app.db.mongodb import get_database

router = APIRouter(prefix="/audit-logs", tags=["审计日志"])


@router.get("/", response_model=AuditLogList)
async def get_audit_logs(
    request: Request,
    user_id: Optional[str] = Query(None, description="用户ID"),
    action: Optional[str] = Query(None, description="操作类型"),
    resource_type: Optional[str] = Query(None, description="资源类型"),
    resource_id: Optional[str] = Query(None, description="资源ID"),
    status: Optional[str] = Query(None, description="操作状态"),
    start_date: Optional[str] = Query(None, description="开始日期(ISO格式)"),
    end_date: Optional[str] = Query(None, description="结束日期(ISO格式)"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=100, description="返回记录数"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: int = Query(-1, description="排序顺序 (-1:降序, 1:升序)"),
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_database)
):
    """
    获取审计日志列表
    
    参数说明:
    - user_id: 选填，按用户ID过滤
    - action: 选填，按操作类型过滤 (access, grant, revoke等)
    - resource_type: 选填，按资源类型过滤 (permission, role等)
    - resource_id: 选填，按资源ID过滤
    - status: 选填，按操作状态过滤 (success, failure)
    - start_date: 选填，开始日期，ISO格式 (YYYY-MM-DDTHH:MM:SS)
    - end_date: 选填，结束日期，ISO格式 (YYYY-MM-DDTHH:MM:SS)
    - skip: 选填，跳过记录数，默认0
    - limit: 选填，返回记录数，默认50，最大100
    - sort_by: 选填，排序字段，默认created_at
    - sort_order: 选填，排序顺序，-1为降序，1为升序，默认-1
    
    权限要求:
    - 系统管理员或system:admin权限
    """
    # 权限检查
    if not PermissionChecker.has_permission(current_user, Permission.SYSTEM_ADMIN):
        # 记录权限检查失败
        audit_service = AuditLogService(db)
        await audit_service.log_permission_check(
            user_id=current_user.id,
            permission=Permission.SYSTEM_ADMIN,
            is_granted=False,
            ip_address=request.client.host if request.client else None,
            details={"endpoint": "/audit-logs"}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您没有访问审计日志的权限"
        )
    
    # 构建过滤条件
    filter_params = AuditLogFilter(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        start_date=start_date,
        end_date=end_date
    )
    
    # 获取日志列表
    audit_service = AuditLogService(db)
    result = await audit_service.get_logs(
        filter_params=filter_params,
        skip=skip,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order
    )
    
    # 记录查询审计日志操作
    await audit_service.create_log(
        log_data={
            "user_id": current_user.id,
            "action": "query",
            "resource_type": "audit_log",
            "details": {
                "filters": filter_params.dict(exclude_none=True),
                "results_count": result.get("total", 0)
            }
        },
        ip_address=request.client.host if request.client else None
    )
    
    return result


@router.get("/{log_id}", response_model=AuditLogResponse)
async def get_audit_log_by_id(
    log_id: str,
    request: Request,
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_database)
):
    """
    获取审计日志详情
    
    参数说明:
    - log_id: 审计日志ID
    
    权限要求:
    - 系统管理员或system:admin权限
    """
    # 权限检查
    if not PermissionChecker.has_permission(current_user, Permission.SYSTEM_ADMIN):
        # 记录权限检查失败
        audit_service = AuditLogService(db)
        await audit_service.log_permission_check(
            user_id=current_user.id,
            permission=Permission.SYSTEM_ADMIN,
            is_granted=False,
            ip_address=request.client.host if request.client else None,
            details={"endpoint": f"/audit-logs/{log_id}"}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您没有访问审计日志的权限"
        )
    
    # 获取日志详情
    audit_service = AuditLogService(db)
    log = await audit_service.get_log_by_id(log_id)
    
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到指定的审计日志"
        )
    
    # 记录查看审计日志详情操作
    await audit_service.create_log(
        log_data={
            "user_id": current_user.id,
            "action": "view",
            "resource_type": "audit_log",
            "resource_id": log_id
        },
        ip_address=request.client.host if request.client else None
    )
    
    return log


@router.get("/user/{user_id}/recent", response_model=list[AuditLogResponse])
async def get_recent_logs_by_user(
    user_id: str,
    request: Request,
    limit: int = Query(10, ge=1, le=50, description="返回记录数"),
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_database)
):
    """
    获取用户最近的审计日志
    
    参数说明:
    - user_id: 用户ID
    - limit: 选填，返回记录数，默认10，最大50
    
    权限要求:
    - 系统管理员或system:admin权限
    - 或者查询自己的日志
    """
    # 权限检查
    is_self = current_user.id == user_id
    has_admin_permission = PermissionChecker.has_permission(current_user, Permission.SYSTEM_ADMIN)
    
    if not (is_self or has_admin_permission):
        # 记录权限检查失败
        audit_service = AuditLogService(db)
        await audit_service.log_permission_check(
            user_id=current_user.id,
            permission=Permission.SYSTEM_ADMIN,
            is_granted=False,
            ip_address=request.client.host if request.client else None,
            details={"endpoint": f"/audit-logs/user/{user_id}/recent"}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您没有访问该用户审计日志的权限"
        )
    
    # 获取用户最近日志
    audit_service = AuditLogService(db)
    logs = await audit_service.get_recent_logs_by_user(user_id, limit)
    
    # 记录查询用户最近日志操作
    if not is_self:
        await audit_service.create_log(
            log_data={
                "user_id": current_user.id,
                "action": "query",
                "resource_type": "audit_log",
                "resource_id": user_id,
                "details": {
                    "limit": limit,
                    "results_count": len(logs)
                }
            },
            ip_address=request.client.host if request.client else None
        )
    
    return logs 