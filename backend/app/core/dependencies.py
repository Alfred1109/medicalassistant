from fastapi import Depends, HTTPException, status
from typing import Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongodb import get_database
from app.db.crud_services import (
    get_crud_services, UserCRUD, DoctorCRUD, PatientCRUD, HealthManagerCRUD,
    OrganizationCRUD, HealthRecordCRUD, FollowUpRecordCRUD,
    RehabilitationPlanCRUD, ExerciseCRUD, ProgressRecordCRUD,
    DeviceCRUD, DeviceDataCRUD, AgentCRUD, MessageCRUD, ConversationCRUD
)
from app.services.user_service import UserService
from app.services.agent_service import AgentService
from app.services.rehabilitation_service import RehabilitationService
from app.schemas.user import UserResponse
from app.core.permissions import PermissionChecker, Permission
from app.services.health_record_service import HealthRecordService
from app.services.health_alert_service import HealthAlertService
from app.core.auth import get_current_user, get_current_active_user

# CRUD服务依赖
async def get_crud(db: AsyncIOMotorDatabase = Depends(get_database)):
    """获取CRUD服务字典"""
    return get_crud_services(db)

# 用户相关CRUD依赖
async def get_user_crud(crud=Depends(get_crud)):
    """获取用户CRUD服务"""
    return crud["user"]

async def get_doctor_crud(crud=Depends(get_crud)):
    """获取医生CRUD服务"""
    return crud["doctor"]

async def get_patient_crud(crud=Depends(get_crud)):
    """获取患者CRUD服务"""
    return crud["patient"]

async def get_health_manager_crud(crud=Depends(get_crud)):
    """获取健康管理师CRUD服务"""
    return crud["health_manager"]

# 组织相关CRUD依赖
async def get_organization_crud(crud=Depends(get_crud)):
    """获取组织CRUD服务"""
    return crud["organization"]

# 健康记录相关CRUD依赖
async def get_health_record_crud(crud=Depends(get_crud)):
    """获取健康记录CRUD服务"""
    return crud["health_record"]

async def get_followup_record_crud(crud=Depends(get_crud)):
    """获取随访记录CRUD服务"""
    return crud["followup_record"]

# 康复相关CRUD依赖
async def get_rehabilitation_plan_crud(crud=Depends(get_crud)):
    """获取康复计划CRUD服务"""
    return crud["rehabilitation_plan"]

async def get_exercise_crud(crud=Depends(get_crud)):
    """获取锻炼CRUD服务"""
    return crud["exercise"]

async def get_progress_record_crud(crud=Depends(get_crud)):
    """获取进度记录CRUD服务"""
    return crud["progress_record"]

# 设备相关CRUD依赖
async def get_device_crud(crud=Depends(get_crud)):
    """获取设备CRUD服务"""
    return crud["device"]

async def get_device_data_crud(crud=Depends(get_crud)):
    """获取设备数据CRUD服务"""
    return crud["device_data"]

# 代理相关CRUD依赖
async def get_agent_crud(crud=Depends(get_crud)):
    """获取代理CRUD服务"""
    return crud["agent"]

# 通信相关CRUD依赖
async def get_message_crud(crud=Depends(get_crud)):
    """获取消息CRUD服务"""
    return crud["message"]

async def get_conversation_crud(crud=Depends(get_crud)):
    """获取对话CRUD服务"""
    return crud["conversation"]

# 业务服务依赖
async def get_user_service(
    db: AsyncIOMotorDatabase = Depends(get_database),
    user_crud: UserCRUD = Depends(get_user_crud),
    doctor_crud: DoctorCRUD = Depends(get_doctor_crud),
    patient_crud: PatientCRUD = Depends(get_patient_crud),
    health_manager_crud: HealthManagerCRUD = Depends(get_health_manager_crud)
):
    """获取用户服务"""
    return UserService(
        db=db,
        user_crud=user_crud,
        doctor_crud=doctor_crud,
        patient_crud=patient_crud,
        health_manager_crud=health_manager_crud
    )

async def get_agent_service(
    db: AsyncIOMotorDatabase = Depends(get_database),
    agent_crud: AgentCRUD = Depends(get_agent_crud)
):
    """获取代理服务"""
    return AgentService(db=db)

async def get_rehabilitation_service(
    db: AsyncIOMotorDatabase = Depends(get_database),
    plan_crud: RehabilitationPlanCRUD = Depends(get_rehabilitation_plan_crud),
    exercise_crud: ExerciseCRUD = Depends(get_exercise_crud),
    progress_crud: ProgressRecordCRUD = Depends(get_progress_record_crud)
):
    """获取康复服务"""
    return RehabilitationService(
        db=db,
        plan_crud=plan_crud,
        exercise_crud=exercise_crud,
        progress_crud=progress_crud
    )

# 权限检查依赖
def check_permission(permission: str):
    """检查用户是否具有特定权限"""
    async def dependency(current_user: UserResponse = Depends(get_current_user)):
        if not PermissionChecker.has_permission(current_user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足: 需要 {permission} 权限"
            )
        return current_user
    return dependency

def check_any_permission(permissions: List[str]):
    """检查用户是否具有任一权限"""
    async def dependency(current_user: UserResponse = Depends(get_current_user)):
        has_any = any(PermissionChecker.has_permission(current_user, perm) for perm in permissions)
        if not has_any:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足: 需要以下权限之一: {', '.join(permissions)}"
            )
        return current_user
    return dependency

def check_all_permissions(permissions: List[str]):
    """检查用户是否具有所有权限"""
    async def dependency(current_user: UserResponse = Depends(get_current_user)):
        missing_perms = [perm for perm in permissions if not PermissionChecker.has_permission(current_user, perm)]
        if missing_perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足: 缺少以下权限: {', '.join(missing_perms)}"
            )
        return current_user
    return dependency

# 角色检查依赖
def is_admin():
    """检查用户是否为管理员"""
    async def dependency(current_user: UserResponse = Depends(get_current_user)):
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要管理员权限"
            )
        return current_user
    return dependency

def is_doctor():
    """检查用户是否为医生"""
    async def dependency(current_user: UserResponse = Depends(get_current_user)):
        if current_user.role != "doctor":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要医生权限"
            )
        return current_user
    return dependency

def is_health_manager():
    """检查用户是否为健康管理师"""
    async def dependency(current_user: UserResponse = Depends(get_current_user)):
        if current_user.role != "health_manager":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要健康管理师权限"
            )
        return current_user
    return dependency

def is_patient():
    """检查用户是否为患者"""
    async def dependency(current_user: UserResponse = Depends(get_current_user)):
        if current_user.role != "patient":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要患者权限"
            )
        return current_user
    return dependency

def is_medical_staff():
    """检查用户是否为医疗人员(医生或健康管理师)"""
    async def dependency(current_user: UserResponse = Depends(get_current_user)):
        if current_user.role not in ["doctor", "health_manager"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要医疗人员(医生或健康管理师)权限"
            )
        return current_user
    return dependency

# 服务依赖
async def get_health_record_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> HealthRecordService:
    """获取健康记录服务"""
    return HealthRecordService(db=db)

async def get_health_alert_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> HealthAlertService:
    """获取健康预警服务"""
    return HealthAlertService(db=db)