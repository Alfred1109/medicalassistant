from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from app.schemas.user import UserResponse
from app.core.dependencies import get_current_user, get_database, format_mongo_doc, get_health_record_for_patient
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.db.crud_services import PatientCRUD, DoctorCRUD
from app.models.user import Doctor, Patient
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
    doctor_crud = DoctorCRUD(db, Doctor)
    patient_crud = PatientCRUD(db, Patient)
    
    try:
        # 获取当前医生的所有患者
        doctor_id = current_user.id
        patients_data = await patient_crud.find_by_doctor_id(doctor_id)
        
        # 直接返回find_by_doctor_id的结果，无需再次格式化
        return patients_data
    except Exception as e:
        # 记录错误，但不返回硬编码数据
        print(f"获取患者数据时出错: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取患者数据失败，请稍后重试"
        )

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
        # 检查该患者是否属于当前医生
        doctor_crud = DoctorCRUD(db, Doctor)
        doctor_id = current_user.id
        patient_ids = await doctor_crud.get_patients(doctor_id)
        
        # 兼容处理医生记录中没有patients字段或为空的情况
        if not patient_ids:
            # 直接从数据库检查医生记录
            doctor_collection = db["users"]
            doctor = await doctor_collection.find_one({"_id": ObjectId(doctor_id), "role": "doctor"})
            if doctor and "patients" in doctor:
                patient_ids = doctor["patients"]
        
        # 检查患者是否属于当前医生
        if patient_id not in patient_ids:
            # 尝试直接查询患者信息确认是否存在
            patient_collection = db["users"]
            patient = await patient_collection.find_one({"_id": ObjectId(patient_id), "role": "patient"})
            if not patient:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到患者信息")
            
            # 如果患者存在但不属于当前医生，提示权限不足
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="您无权查看该患者的健康档案")
        
        # 使用通用函数获取健康档案
        record = await get_health_record_for_patient(patient_id, db)
        
        if not record:
            # 获取患者基本信息，创建空的健康档案结构
            patient_collection = db["users"]
            patient = await patient_collection.find_one({"_id": ObjectId(patient_id), "role": "patient"})
            
            if not patient:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到患者信息")
                
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
    except HTTPException:
        raise
    except Exception as e:
        print(f"获取患者健康档案时出错: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取健康档案失败，请稍后重试"
        )

# 随访管理
@router.get("/follow-ups", response_model=List[dict])
async def get_follow_ups(
    status: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """获取随访列表"""
    if current_user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    
    try:
        # 获取当前医生的所有随访记录
        doctor_id = current_user.id
        query = {"doctor_id": doctor_id}
        
        # 如果指定了状态，添加到查询条件
        if status:
            query["status"] = status
        
        follow_up_collection = db["follow_ups"]
        follow_ups = []
        
        # 执行查询
        cursor = follow_up_collection.find(query)
        async for follow_up in cursor:
            # 转换ObjectId为字符串
            follow_up["_id"] = str(follow_up["_id"])
            follow_ups.append(follow_up)
        
        return follow_ups
    except Exception as e:
        print(f"获取随访列表时出错: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取随访列表失败，请稍后重试"
        )

@router.post("/follow-ups", status_code=status.HTTP_201_CREATED)
async def create_follow_up(
    follow_up_data: dict,
    current_user: UserResponse = Depends(get_current_user)
):
    """创建随访计划"""
    if current_user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return {"id": "new_follow_up_id"}

# 数据监测
@router.get("/patient-monitoring/{patient_id}", response_model=dict)
async def get_patient_monitoring_data(
    patient_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user)
):
    """获取患者监测数据"""
    if current_user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return {}

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
    current_user: UserResponse = Depends(get_current_user)
):
    """获取医生工作统计数据"""
    if current_user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return {}

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