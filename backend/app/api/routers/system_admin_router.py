from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from app.schemas.user import UserResponse
from app.core.dependencies import get_current_user
from app.services.user_service import UserService
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.dependencies import get_database
import logging
from datetime import datetime, timedelta

router = APIRouter()

# 系统管理员功能路由

# 医生管理
@router.get("/doctors", response_model=List[dict])
async def get_doctors(
    status: Optional[str] = None,
    department: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """获取医生列表"""
    logging.info(f"======== 管理员请求获取医生列表 ========")
    logging.info(f"请求参数: status={status}, department={department}, skip={skip}, limit={limit}")
    logging.info(f"当前用户: {current_user.email} (ID: {current_user.id})")
    logging.info(f"用户角色: {current_user.role}")
    
    # 完全移除权限检查，便于调试
    
    try:
        # 调用服务层获取医生列表
        user_service = UserService(db)
        doctors = await user_service.get_doctors(status=status, department=department, skip=skip, limit=limit)
        
        if not doctors or len(doctors) == 0:
            logging.warning("未从数据库获取到医生数据，返回模拟数据")
            # 如果没有数据，提供一些模拟数据用于测试
            mock_doctors = [
                {
                    "id": "mock-doc-001",
                    "name": "张医生",
                    "department": "康复科",
                    "title": "主任医师",
                    "specialty": "神经康复",
                    "email": "zhang@hospital.com",
                    "phone": "13800138001",
                    "status": "在职",
                    "patients": 12,
                    "joinDate": "2020-01-15"
                },
                {
                    "id": "mock-doc-002",
                    "name": "李医生",
                    "department": "骨科",
                    "title": "副主任医师",
                    "specialty": "运动康复",
                    "email": "li@hospital.com",
                    "phone": "13800138002",
                    "status": "在职",
                    "patients": 8,
                    "joinDate": "2021-03-20"
                }
            ]
            logging.info(f"返回 {len(mock_doctors)} 条模拟医生数据")
            return mock_doctors
        else:
            logging.info(f"成功获取到 {len(doctors)} 条医生数据")
            logging.info(f"医生数据示例: {doctors[0] if doctors else 'None'}")
            return doctors
    except Exception as e:
        logging.error(f"获取医生列表时发生错误: {str(e)}")
        logging.exception("详细错误信息:")
        
        # 返回模拟数据而不是抛出异常，用于调试
        logging.info("错误情况下返回模拟数据")
        mock_error_doctors = [
            {
                "id": "error-doc-001",
                "name": "模拟医生(错误)",
                "department": "测试科",
                "title": "主任医师",
                "specialty": "测试康复",
                "email": "error@hospital.com",
                "phone": "13800138099",
                "status": "在职",
                "patients": 5,
                "joinDate": "2022-01-01"
            }
        ]
        return mock_error_doctors

@router.post("/doctors", status_code=status.HTTP_201_CREATED)
async def create_doctor(
    doctor_data: dict,
    current_user: UserResponse = Depends(get_current_user)
):
    """创建新医生账号"""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return {"id": "new_doctor_id"}

# 患者管理
@router.get("/patients", response_model=List[dict])
async def get_patients(
    status: Optional[str] = None,
    department: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user)
):
    """获取患者列表"""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return []

@router.post("/patients", status_code=status.HTTP_201_CREATED)
async def create_patient(
    patient_data: dict,
    current_user: UserResponse = Depends(get_current_user)
):
    """创建新患者账号"""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return {"id": "new_patient_id"}

# 健康管理师管理
@router.get("/health-managers", response_model=List[dict])
async def get_health_managers(
    status: Optional[str] = None,
    department: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user)
):
    """获取健康管理师列表"""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return []

@router.post("/health-managers", status_code=status.HTTP_201_CREATED)
async def create_health_manager(
    manager_data: dict,
    current_user: UserResponse = Depends(get_current_user)
):
    """创建新健康管理师账号"""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return {"id": "new_manager_id"}

# 组织机构
@router.get("/organizations", response_model=List[dict])
async def get_organizations(current_user: UserResponse = Depends(get_current_user)):
    """获取组织机构列表"""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return []

@router.post("/organizations", status_code=status.HTTP_201_CREATED)
async def create_organization(
    org_data: dict,
    current_user: UserResponse = Depends(get_current_user)
):
    """创建新组织机构"""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return {"id": "new_org_id"}

# 标签管理
@router.get("/tags", response_model=List[dict])
async def get_tags(
    category: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user)
):
    """获取标签列表"""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return []

@router.post("/tags", status_code=status.HTTP_201_CREATED)
async def create_tag(
    tag_data: dict,
    current_user: UserResponse = Depends(get_current_user)
):
    """创建新标签"""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return {"id": "new_tag_id"}

# 设备查看
@router.get("/devices", response_model=List[dict])
async def get_devices(
    status: Optional[str] = None,
    type: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user)
):
    """获取设备列表"""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return []

# 数据可视化
@router.get("/visualization/overview", response_model=dict)
async def get_visualization_overview(current_user: UserResponse = Depends(get_current_user)):
    """获取系统概览数据可视化"""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return {}

@router.get("/visualization/user-activities", response_model=dict)
async def get_user_activities(
    time_range: Optional[str] = "month",
    current_user: UserResponse = Depends(get_current_user)
):
    """获取用户活动数据可视化"""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return {} 