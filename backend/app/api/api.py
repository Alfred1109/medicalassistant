"""
API路由聚合模块
注册所有API路由到主应用
"""
from fastapi import APIRouter

from app.api.endpoints import (
    auth, users, utils, agents, patients, health, 
    doctor, dashboard, rehabilitation, analytics, device, 
    chat, permission, prediction, agent_optimized, db_optimizer
)

# 创建API路由集合
api_router = APIRouter()

# 注册各模块路由
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(utils.router, prefix="/utils", tags=["utils"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(patients.router, prefix="/patients", tags=["patients"])
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(doctor.router, prefix="/doctor", tags=["doctor"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(rehabilitation.router, prefix="/rehabilitation", tags=["rehabilitation"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(device.router, prefix="/device", tags=["device"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(permission.router, prefix="/permission", tags=["permission"])

# 添加新路由
api_router.include_router(prediction.router, prefix="/prediction", tags=["prediction"])
api_router.include_router(agent_optimized.router, prefix="/agent-optimized", tags=["agent-optimized"])
api_router.include_router(db_optimizer.router, prefix="/system/db-optimizer", tags=["database-optimizer"]) 