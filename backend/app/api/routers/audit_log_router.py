from datetime import datetime
from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status as http_status
from pydantic import ValidationError

from app.core.auth import get_current_active_user
from app.core.permissions import Permission, PermissionChecker
from app.schemas.user import UserResponse
from app.schemas.audit_log import AuditLogCreate, AuditLogFilter, AuditLogList, AuditLogResponse, AuditSortField
from app.services.audit_log_service import AuditLogService, AuditLogStorageError
from app.db.mongodb import get_database

router = APIRouter(prefix="/audit-logs", tags=["审计日志"])


async def get_audit_service(db=Depends(get_database)):
    """Audit failures deny the read instead of returning unrecorded protected data."""
    try:
        yield AuditLogService(db)
    except AuditLogStorageError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="审计服务暂不可用，请稍后重试",
        ) from exc


async def require_admin(user: UserResponse, service: AuditLogService, request: Request, endpoint: str):
    if PermissionChecker.has_permission(user, Permission.SYSTEM_ADMIN):
        return
    await service.log_permission_check(
        user_id=user.id, permission=Permission.SYSTEM_ADMIN, is_granted=False,
        ip_address=request.client.host if request.client else None,
        details={"endpoint": endpoint},
    )
    raise HTTPException(
        status_code=http_status.HTTP_403_FORBIDDEN, detail="您没有访问审计日志的权限",
    )


@router.get("/", response_model=AuditLogList)
async def get_audit_logs(
    request: Request,
    user_id: Optional[str] = Query(None, description="用户ID"),
    action: Optional[str] = Query(None, description="操作类型"),
    resource_type: Optional[str] = Query(None, description="资源类型"),
    resource_id: Optional[str] = Query(None, description="资源ID"),
    status: Optional[Literal["success", "failure"]] = Query(None, description="操作状态"),
    start_date: Optional[datetime] = Query(None, description="开始日期(ISO格式；无时区按UTC)"),
    end_date: Optional[datetime] = Query(None, description="结束日期(ISO格式；包含边界，无时区按UTC)"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=100, description="返回记录数"),
    sort_by: AuditSortField = Query("created_at", description="排序字段"),
    sort_order: int = Query(-1, description="排序顺序 (-1:降序, 1:升序)"),
    current_user: UserResponse = Depends(get_current_active_user),
    audit_service: AuditLogService = Depends(get_audit_service)
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
    await require_admin(current_user, audit_service, request, "/audit-logs")
    if sort_order not in (-1, 1):
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="排序顺序只能为-1或1")
    
    # 构建过滤条件
    try:
        filter_params = AuditLogFilter(
            user_id=user_id, action=action, resource_type=resource_type,
            resource_id=resource_id, status=status, start_date=start_date, end_date=end_date,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="结束时间不能早于开始时间",
        ) from exc
    
    # 获取日志列表
    result = await audit_service.get_logs(
        filter_params=filter_params,
        skip=skip,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order
    )
    
    # 记录查询审计日志操作
    await audit_service.create_log(
        log_data=AuditLogCreate(
            user_id=current_user.id,
            action="query",
            resource_type="audit_log",
            details={
                "filters": filter_params.model_dump(exclude_none=True),
                "results_count": result.get("total", 0)
            }
        ),
        ip_address=request.client.host if request.client else None
    )
    
    return result


@router.get("/{log_id}", response_model=AuditLogResponse)
async def get_audit_log_by_id(
    request: Request,
    log_id: str = Path(..., pattern=r"^[0-9a-fA-F]{24}$", description="审计日志ObjectId"),
    current_user: UserResponse = Depends(get_current_active_user),
    audit_service: AuditLogService = Depends(get_audit_service)
):
    """
    获取审计日志详情
    
    参数说明:
    - log_id: 审计日志ID
    
    权限要求:
    - 系统管理员或system:admin权限
    """
    # 权限检查
    await require_admin(current_user, audit_service, request, f"/audit-logs/{log_id}")
    
    # 获取日志详情
    log = await audit_service.get_log_by_id(log_id)
    
    # 记录查看审计日志详情操作
    await audit_service.create_log(
        log_data=AuditLogCreate(
            user_id=current_user.id, action="view", resource_type="audit_log",
            resource_id=log_id, status="success" if log else "failure",
        ),
        ip_address=request.client.host if request.client else None
    )
    
    if not log:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="未找到指定的审计日志")
    return log


@router.get("/user/{user_id}/recent", response_model=list[AuditLogResponse])
async def get_recent_logs_by_user(
    user_id: str,
    request: Request,
    limit: int = Query(10, ge=1, le=50, description="返回记录数"),
    current_user: UserResponse = Depends(get_current_active_user),
    audit_service: AuditLogService = Depends(get_audit_service)
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
        await audit_service.log_permission_check(
            user_id=current_user.id,
            permission=Permission.SYSTEM_ADMIN,
            is_granted=False,
            ip_address=request.client.host if request.client else None,
            details={"endpoint": f"/audit-logs/user/{user_id}/recent"}
        )
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="您没有访问该用户审计日志的权限"
        )
    
    # 获取用户最近日志
    logs = await audit_service.get_recent_logs_by_user(user_id, limit)
    
    # 记录查询用户最近日志操作
    await audit_service.create_log(
        log_data=AuditLogCreate(
            user_id=current_user.id, action="query", resource_type="audit_log",
            resource_id=user_id,
            details={"limit": limit, "results_count": len(logs), "self_query": is_self},
        ),
        ip_address=request.client.host if request.client else None,
    )
    
    return logs
