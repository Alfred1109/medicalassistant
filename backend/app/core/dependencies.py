from fastapi import Depends, HTTPException, Request, status
from typing import Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from datetime import datetime
import logging

from app.db.mongodb import get_database
from app.services.user_service import UserService
from app.services.agent_service import AgentService
from app.services.rehabilitation_service import RehabilitationService
from app.services.rehab_plan_structure_service import RehabPlanStructureService
from app.schemas.user import UserResponse
from app.core.permissions import PermissionChecker
from app.core.patient_access import PatientAccessError, load_patient_doc, ensure_patient_access
from app.services.health_record_service import HealthRecordService
from app.services.followup_service import FollowupService
from app.services.health_alert_service import HealthAlertService
from app.core.auth import get_current_user as auth_get_current_user, get_current_active_user

logger = logging.getLogger(__name__)

# 使用同一认证依赖，避免不同路由以不同方式解释同一令牌。
get_current_user = auth_get_current_user

# 业务服务依赖
async def get_user_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> UserService:
    logger.info("Attempting to get UserService instance.")
    try:
        # 这里假设 UserService 的构造函数是同步的，如果它是异步的，需要 await
        user_service = UserService(db)
        # 如果 UserService 有异步的初始化方法，比如 initialize()，并且需要在获取服务实例时调用：
        # await user_service.initialize() # 取消注释并调整（如果存在这样的方法）
        logger.info("UserService instance created successfully.")
        return user_service
    except Exception as e:
        logger.error(f"Error creating UserService instance: {str(e)}", exc_info=True)
        # 如果创建服务失败，可以抛出一个标准的服务器错误
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="无法初始化用户服务"
        )

async def get_agent_service(
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """获取代理服务"""
    return AgentService(db=db)

async def get_rehabilitation_service(
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """获取康复服务"""
    return RehabilitationService(db=db)

async def get_rehab_plan_structure_service(
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """获取康复方案结构化服务（REH01：方案版本/处方项/执行事件）"""
    return RehabPlanStructureService(db=db)

# 权限检查依赖
def check_permission(permission: str):
    """检查用户是否具有特定权限"""
    async def dependency(current_user: UserResponse = Depends(auth_get_current_user)):
        if not PermissionChecker.has_permission(current_user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足: 需要 {permission} 权限"
            )
        return current_user
    return dependency

def check_any_permission(permissions: List[str]):
    """检查用户是否具有任一权限"""
    async def dependency(current_user: UserResponse = Depends(auth_get_current_user)):
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
    async def dependency(current_user: UserResponse = Depends(auth_get_current_user)):
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
    async def dependency(current_user: UserResponse = Depends(auth_get_current_user)):
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要管理员权限"
            )
        return current_user
    return dependency

def is_doctor():
    """检查用户是否为医生"""
    async def dependency(current_user: UserResponse = Depends(auth_get_current_user)):
        if current_user.role != "doctor":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要医生权限"
            )
        return current_user
    return dependency

def is_health_manager():
    """检查用户是否为健康管理师"""
    async def dependency(current_user: UserResponse = Depends(auth_get_current_user)):
        if current_user.role != "health_manager":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要健康管理师权限"
            )
        return current_user
    return dependency

def is_patient():
    """检查用户是否为患者"""
    async def dependency(current_user: UserResponse = Depends(auth_get_current_user)):
        if current_user.role != "patient":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要患者权限"
            )
        return current_user
    return dependency

def is_medical_staff():
    """检查用户是否为医疗人员(医生或健康管理师)"""
    async def dependency(current_user: UserResponse = Depends(auth_get_current_user)):
        if current_user.role not in ["doctor", "health_manager"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要医疗人员(医生或健康管理师)权限"
            )
        return current_user
    return dependency

# 对象授权内核从 patient_access 转发，保留旧导入兼容；这里只组装 HTTP 依赖。
def verify_patient_access(source: str = "query", name: str = "patient_id",
                          required: bool = True):
    """依赖工厂：从 path/query 提取患者标识并校验当前用户归属（AUTH01 第一层）。

    - source="path"：路径参数（如 /patients/{patient_id}/assessments）；
    - source="query"：查询参数（如 /plans?patient_id=...）；
    - required=False：缺少参数时跳过校验（用于可选过滤，如 GET /plans）；
    - 登录校验仍由内部依赖 get_current_user 完成，未认证一律 401。
    """
    async def dependency(
        request: Request,
        current_user: UserResponse = Depends(get_current_active_user),
        db: AsyncIOMotorDatabase = Depends(get_database),
    ) -> UserResponse:
        if source == "path":
            patient_id = request.path_params.get(name)
        elif source == "query":
            patient_id = request.query_params.get(name)
        else:
            raise RuntimeError(f"未知的 patient_id 来源: {source}")

        if not patient_id:
            if required:
                raise PatientAccessError("缺少患者标识", error_code="PATIENT_ID_REQUIRED",
                                         status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
            return current_user

        await ensure_patient_access(db, patient_id, str(current_user.id), current_user.role)
        return current_user

    return dependency

# 服务依赖
async def get_health_record_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> HealthRecordService:
    """获取健康记录服务"""
    return HealthRecordService(db=db)

async def get_followup_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> FollowupService:
    """获取随访服务（FU01 S2 唯一随访服务入口，路由层一律经此转调）"""
    return FollowupService(db=db)

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
