from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from app.db.mongodb import get_database
from app.services.analytics_service import AnalyticsService
from app.core.auth import get_current_active_user
from app.schemas.user import UserResponse
from app.core.permissions import Permission, PermissionChecker

router = APIRouter(tags=["analytics"])

# 获取统计数据概览
@router.get("/system/visualization/overview", response_model=Dict[str, Any])
async def get_stats_overview(
    request: Request,
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_database)
):
    """
    获取系统统计数据概览，包括患者数量、医生数量、设备数量等
    """
    # 权限检查 - 要求管理员或者医生权限
    if not (PermissionChecker.has_permission(current_user, Permission.SYSTEM_ADMIN) or 
            current_user.role == "doctor"):  # 直接检查用户角色
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您没有权限访问这些数据"
        )
    
    analytics_service = AnalyticsService(db)
    stats = await analytics_service.get_stats_overview()
    
    return {
        "status": "success",
        "message": "成功获取统计数据",
        "data": stats
    }

# 获取趋势数据
@router.get("/analytics/trend", response_model=Dict[str, Any])
async def get_trend_data(
    request: Request,
    data_type: str = Query(..., description="数据类型 (patient, doctor, device, rehabilitation)"),
    time_range: str = Query(..., description="时间范围 (day, week, month, quarter, year)"),
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_database)
):
    """
    获取趋势数据，用于绘制折线图等
    """
    # 权限检查 - 要求管理员或者医生权限
    if not (PermissionChecker.has_permission(current_user, Permission.SYSTEM_ADMIN) or 
            current_user.role == "doctor"):  # 直接检查用户角色
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您没有权限访问这些数据"
        )
    
    analytics_service = AnalyticsService(db)
    trend_data = await analytics_service.get_trend_data(data_type, time_range)
    
    return {
        "status": "success",
        "message": "成功获取趋势数据",
        "data": trend_data
    }

# 获取分布数据
@router.get("/analytics/distribution", response_model=Dict[str, Any])
async def get_distribution_data(
    request: Request,
    data_type: str = Query(..., description="数据类型 (patient, doctor, device, rehabilitation)"),
    time_range: str = Query(..., description="时间范围 (day, week, month, quarter, year)"),
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_database)
):
    """
    获取分布数据，用于绘制饼图等
    """
    # 权限检查 - 要求管理员或者医生权限
    if not (PermissionChecker.has_permission(current_user, Permission.SYSTEM_ADMIN) or 
            current_user.role == "doctor"):  # 直接检查用户角色
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您没有权限访问这些数据"
        )
    
    analytics_service = AnalyticsService(db)
    distribution_data = await analytics_service.get_distribution_data(data_type, time_range)
    
    return {
        "status": "success",
        "message": "成功获取分布数据",
        "data": distribution_data
    }

# 获取对比数据
@router.get("/analytics/comparison", response_model=Dict[str, Any])
async def get_comparison_data(
    request: Request,
    data_type: str = Query(..., description="数据类型 (patient, doctor, device, rehabilitation)"),
    time_range: str = Query(..., description="时间范围 (day, week, month, quarter, year)"),
    compare_with: str = Query(..., description="对比对象 (lastPeriod, lastYear, target)"),
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_database)
):
    """
    获取对比数据，用于绘制柱状图等
    """
    # 权限检查 - 要求管理员或者医生权限
    if not (PermissionChecker.has_permission(current_user, Permission.SYSTEM_ADMIN) or 
            current_user.role == "doctor"):  # 直接检查用户角色
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您没有权限访问这些数据"
        )
    
    analytics_service = AnalyticsService(db)
    comparison_data = await analytics_service.get_comparison_data(data_type, time_range, compare_with)
    
    return {
        "status": "success",
        "message": "成功获取对比数据",
        "data": comparison_data
    } 