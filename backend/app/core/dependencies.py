from fastapi import Depends, HTTPException, status
from typing import Dict, Any, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
import json
from datetime import datetime

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
    return UserService(db=db)

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

# 健康档案相关方法
async def get_health_record_for_patient(
    patient_id: str, 
    db: AsyncIOMotorDatabase
) -> Dict[str, Any]:
    """获取或创建患者健康档案"""
    try:
        # 获取患者数据
        users_collection = db["users"]
        patient = await users_collection.find_one({"_id": ObjectId(patient_id), "role": "patient"})
        
        if not patient:
            return {}
            
        # 获取健康档案
        health_records_collection = db["health_records"]
        health_record = await health_records_collection.find_one({"patient_id": patient_id})
        
        # 如果没有健康档案，创建基本结构
        if not health_record:
            # 将患者基本信息格式化为健康档案结构
            return {
                "id": patient_id,
                "patient_id": patient_id,
                "name": patient.get("name", "Unknown"),
                "age": patient.get("age", 0),
                "gender": patient.get("gender", "Unknown"),
                "height": patient.get("height", 0),
                "weight": patient.get("weight", 0),
                "blood_type": patient.get("blood_type", "Unknown"),
                "allergies": patient.get("allergies", []),
                "emergency_contact": patient.get("emergency_contact", "None"),
                "medical_history": [],
                "rehab_history": [],
                "medications": [],
                "vital_signs": [],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
        # 格式化MongoDB对象
        return format_mongo_doc(health_record)
    except Exception as e:
        print(f"获取患者健康档案时出错: {str(e)}")
        return {}

# MongoDB文档格式化函数
def format_mongo_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """格式化MongoDB文档，将ObjectId转换为字符串等"""
    if not doc:
        return {}
        
    def convert(obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert(item) for item in obj]
        else:
            return obj
            
    return convert(doc)