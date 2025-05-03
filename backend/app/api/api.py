"""
API路由聚合模块
注册所有API路由到主应用
"""
from fastapi import APIRouter

from app.api.routers import (
    user_router, 
    auth_router, 
    patient_router,
    rehabilitation_router,
    health_record_router,  # 健康档案路由
    device_router,  # 设备路由
    device_analysis_router,  # 设备分析路由
    audit_log_router,  # 审计日志路由
    notification_router,  # 通知路由
)

# 创建API路由集合
api_router = APIRouter()

# 注册各模块路由
api_router.include_router(auth_router.router, prefix="/auth", tags=["认证"])
api_router.include_router(user_router.router, prefix="/users", tags=["用户"])
api_router.include_router(patient_router.router, prefix="/patients", tags=["患者"])
api_router.include_router(rehabilitation_router.router)
api_router.include_router(health_record_router.router)  # 健康档案路由已设置前缀和标签
api_router.include_router(device_router.router)  # 设备路由已设置前缀和标签
api_router.include_router(device_analysis_router.router)  # 设备分析路由已设置前缀和标签
api_router.include_router(audit_log_router.router)  # 审计日志路由已设置前缀和标签
api_router.include_router(notification_router.router)  # 通知路由已设置前缀和标签 