from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import List, Optional
from datetime import datetime, timedelta
from app.schemas.user import UserResponse
from app.schemas.followup import FollowUpRecordCreate, FollowUpRecordResponse
from app.core.dependencies import get_current_user, get_database, format_mongo_doc, get_health_record_for_patient, get_followup_service
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.db.crud_services import PatientCRUD
from app.models.user import Patient
from app.core.patient_access import assigned_patient_query, ensure_patient_access, PatientAccessError
from app.services.followup_service import FollowupService
from app.core.followup_access import ensure_followup_patient_access, followup_patient_scope
from bson.objectid import ObjectId

router = APIRouter()

# 医生功能路由

# 患者管理
@router.get("/patients", response_model=List[dict])
async def get_doctor_patients(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """获取医生管理的患者列表"""
    if current_user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    
    # 从数据库获取患者数据
    patient_crud = PatientCRUD(db, Patient)

    try:
        # 获取当前医生的所有患者
        doctor_id = current_user.id
        patients_data = await patient_crud.find_by_doctor_id(doctor_id)
    except Exception as e:
        # 记录错误并如实上抛为 500，绝不返回模拟患者
        print(f"获取患者数据时出错: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取患者列表失败，请稍后重试"
        )

    # 空库/该医生暂无关联患者：如实返回空列表（不再返回 mock_i 模拟数据）
    return patients_data

# 健康档案
@router.get("/health-records/{patient_id}", response_model=dict)
async def get_patient_health_record(
    patient_id: str, 
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """获取患者健康档案"""
    if current_user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    
    try:
        patient = await ensure_patient_access(
            db, patient_id, str(current_user.id), current_user.role)
        
        # 使用通用函数获取健康档案
        record = await get_health_record_for_patient(patient_id, db)
        
        if not record:
            # 构建基本的健康档案结构
            return {
                "id": patient_id,
                "name": patient.get("name", "未知患者"),
                "age": patient.get("age", 0),
                "gender": patient.get("gender", "未知"),
                "height": patient.get("height", 0),
                "weight": patient.get("weight", 0),
                "bloodType": patient.get("blood_type", "未知"),
                "allergies": patient.get("allergies", []),
                "emergencyContact": patient.get("emergency_contact", "未设置"),
                "medicalHistory": [],
                "rehabHistory": [],
                "medications": [],
                "vitalSigns": []
            }
        
        # 将后端字段名转换为前端字段名
        formatted_record = {
            "id": record.get("id") or record.get("_id") or patient_id,
            "name": record.get("name", "未知患者"),
            "age": record.get("age", 0),
            "gender": record.get("gender", "未知"),
            "height": record.get("height", 0),
            "weight": record.get("weight", 0),
            "bloodType": record.get("blood_type", "未知"),
            "allergies": record.get("allergies", []),
            "emergencyContact": record.get("emergency_contact", "未设置"),
            "medicalHistory": record.get("medical_history", []),
            "rehabHistory": record.get("rehab_history", []),
            "medications": record.get("medications", []),
            "vitalSigns": record.get("vital_signs", [])
        }
        
        return formatted_record
    except (HTTPException, PatientAccessError):
        raise
    except Exception as e:
        print(f"获取患者健康档案时出错: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取健康档案失败，请稍后重试"
        )

# 随访管理
# FU01 S2 收敛：/api/doctors/follow-ups 与唯一正典入口 /api/health-records/followups
# 同源（FollowupService）同形状（FollowUpRecordResponse 响应契约），
# 删除路由层直连 followup_records 集合与 new_follow_up_id 假 ID 逻辑
@router.get("/follow-ups", response_model=List[FollowUpRecordResponse])
async def get_follow_ups(
    followup_status: Optional[str] = Query(None, alias="status"),
    current_user: UserResponse = Depends(get_current_user),
    followup_service: FollowupService = Depends(get_followup_service)
):
    """获取当前医生的随访列表（转调 FollowupService，同源同形状）"""
    if current_user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")

    try:
        scope = await followup_patient_scope(followup_service.db, current_user)
        return await followup_service.list_followups_for_provider(
            current_user.id, status=followup_status, patient_ids=scope)
    except Exception as e:
        print(f"获取随访列表时出错: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取随访列表失败，请稍后重试"
        )

@router.post("/follow-ups", status_code=status.HTTP_201_CREATED, response_model=FollowUpRecordResponse)
async def create_follow_up(
    follow_up_data: FollowUpRecordCreate,
    current_user: UserResponse = Depends(get_current_user),
    followup_service: FollowupService = Depends(get_followup_service)
):
    """创建随访计划（转调 FollowupService，返回真实记录 ID 与响应契约）"""
    if current_user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 创建人缺省为当前医生（与 canonical 创建端点一致；provider_id 为必填契约字段）
    await ensure_followup_patient_access(followup_service.db, follow_up_data.patient_id, current_user, write=True)
    follow_up_data.created_by = current_user.id
    return await followup_service.create_followup_record(follow_up_data)

# 数据监测
@router.get("/patient-monitoring/{patient_id}", response_model=dict)
async def get_patient_monitoring_data(
    patient_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """获取患者监测数据（真实聚合快照，2026-11-08 替换存根空对象）

    字段语义（均来自真实集合，无数据时如实为 0）：
    - boundDevices:  绑定到该患者的设备数（devices.patient_id）
    - rehabPlans:    该患者的康复计划总数/进行中/已完成（rehab_plans.patient_id）
    - completedSessionsLast30Days: 近 30 天完成的训练进度记录数
                    （rehab_progress，completed=true 且 date 在近 30 天内；
                    该集合当前无写入方，通常为 0 —— 是真实空数据而非存根）
    - implemented:   显式标记端点已实现真实聚合
    - start_date/end_date 参数为历史签名保留，当前快照类指标不按时间切片
    """
    if current_user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    if not ObjectId.is_valid(patient_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到患者信息")
    try:
        await ensure_patient_access(db, patient_id, str(current_user.id), current_user.role)

        plans_collection = db["rehab_plans"]
        total_plans = await plans_collection.count_documents({"patient_id": patient_id})
        active_plans = await plans_collection.count_documents(
            {"patient_id": patient_id, "status": "active"})
        completed_plans = await plans_collection.count_documents(
            {"patient_id": patient_id, "status": "completed"})

        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        completed_sessions = await db["rehab_progress"].count_documents({
            "patient_id": patient_id,
            "completed": True,
            "date": {"$gte": thirty_days_ago},
        })

        return {
            "implemented": True,
            "patientId": patient_id,
            "boundDevices": await db["devices"].count_documents({"patient_id": patient_id}),
            "rehabPlans": {
                "total": total_plans,
                "active": active_plans,
                "completed": completed_plans,
            },
            "completedSessionsLast30Days": completed_sessions,
        }
    except (HTTPException, PatientAccessError):
        raise
    except Exception as e:
        print(f"获取患者监测数据时出错: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取患者监测数据失败，请稍后重试"
        )

# 医患沟通
@router.get("/communications", response_model=List[dict])
async def get_communications(
    patient_id: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user)
):
    """获取医患沟通记录"""
    if current_user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return []

@router.post("/communications", status_code=status.HTTP_201_CREATED)
async def create_communication(
    message_data: dict,
    current_user: UserResponse = Depends(get_current_user)
):
    """创建新的沟通消息"""
    if current_user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return {"id": "new_message_id"}

# 数据统计
@router.get("/statistics", response_model=dict)
async def get_doctor_statistics(
    time_range: Optional[str] = "month",
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """获取医生工作统计数据（真实聚合，2026-11-08 替换存根空对象）

    字段语义（均来自真实集合，无数据时如实为 0）：
    - patientCount: 患者 practitioners 中关联该医生的真实患者数
    - rehabPlans:   该医生作为 practitioner_id 的康复计划总数/进行中/已完成
                    （rehab_plans 集合，status: active/completed）
    - completedSessionsThisMonth: 该医生患者本月完成的训练进度记录数
                    （rehab_progress，completed=true 且 date 不早于本月；
                    该集合当前无写入方，通常为 0 —— 是真实空数据而非存根）
    - implemented:  显式标记端点已实现真实聚合
    """
    if current_user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    try:
        doctor_id = current_user.id
        doctor = await db["users"].find_one({"_id": ObjectId(doctor_id), "role": "doctor"})
        if not doctor:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到医生信息")

        patient_ids = [str(patient["_id"]) async for patient in
                       db["users"].find(assigned_patient_query(str(doctor_id)), {"_id": 1})]
        plans_collection = db["rehab_plans"]
        total_plans = await plans_collection.count_documents({"practitioner_id": doctor_id})
        active_plans = await plans_collection.count_documents(
            {"practitioner_id": doctor_id, "status": "active"})
        completed_plans = await plans_collection.count_documents(
            {"practitioner_id": doctor_id, "status": "completed"})

        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        completed_sessions = 0
        if patient_ids:
            completed_sessions = await db["rehab_progress"].count_documents({
                "patient_id": {"$in": [str(p) for p in patient_ids]},
                "completed": True,
                "date": {"$gte": month_start},
            })

        return {
            "implemented": True,
            "timeRange": time_range,
            "patientCount": len(patient_ids),
            "rehabPlans": {
                "total": total_plans,
                "active": active_plans,
                "completed": completed_plans,
            },
            "completedSessionsThisMonth": completed_sessions,
        }
    except (HTTPException, PatientAccessError):
        raise
    except Exception as e:
        print(f"获取医生统计数据时出错: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取医生统计数据失败，请稍后重试"
        )

# 知情同意
@router.get("/informed-consents", response_model=List[dict])
async def get_informed_consents(
    status: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user)
):
    """获取知情同意书列表"""
    if current_user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return []

@router.post("/informed-consents", status_code=status.HTTP_201_CREATED)
async def create_informed_consent(
    consent_data: dict,
    current_user: UserResponse = Depends(get_current_user)
):
    """创建知情同意书"""
    if current_user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return {"id": "new_consent_id"}
