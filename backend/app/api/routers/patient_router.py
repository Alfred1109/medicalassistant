from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Dict, Any
from app.schemas.user import UserResponse
from app.core.dependencies import get_current_user, get_database
from motor.motor_asyncio import AsyncIOMotorClient
from app.services.dashboard_service import DashboardService
from app.models.user import User

router = APIRouter()

# 患者功能路由

# 健康档案
@router.get("/health-records", response_model=dict)
async def get_health_record(current_user: UserResponse = Depends(get_current_user)):
    """获取当前患者的健康档案"""
    if current_user.role != "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return {}

# 日常记录
@router.get("/daily-records", response_model=List[dict])
async def get_daily_records(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user)
):
    """获取日常记录列表"""
    if current_user.role != "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return []

@router.post("/daily-records", status_code=status.HTTP_201_CREATED)
async def create_daily_record(
    record_data: dict,
    current_user: UserResponse = Depends(get_current_user)
):
    """创建日常记录"""
    if current_user.role != "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return {"id": "new_record_id"}

# 设备绑定
@router.get("/devices", response_model=List[dict])
async def get_bound_devices(current_user: UserResponse = Depends(get_current_user)):
    """获取已绑定的设备列表"""
    if current_user.role != "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return []

@router.post("/devices", status_code=status.HTTP_201_CREATED)
async def bind_device(
    device_data: dict,
    current_user: UserResponse = Depends(get_current_user)
):
    """绑定新设备"""
    if current_user.role != "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return {"id": "new_device_binding_id"}

@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unbind_device(
    device_id: str,
    current_user: UserResponse = Depends(get_current_user)
):
    """解绑设备"""
    if current_user.role != "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return None

# 医患沟通
@router.get("/communications", response_model=List[dict])
async def get_communications(current_user: UserResponse = Depends(get_current_user)):
    """获取与医生/健康管理师的沟通记录"""
    if current_user.role != "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return []

@router.post("/communications", status_code=status.HTTP_201_CREATED)
async def create_communication(
    message_data: dict,
    current_user: UserResponse = Depends(get_current_user)
):
    """发送新消息"""
    if current_user.role != "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return {"id": "new_message_id"}

# 数据统计
@router.get("/statistics", response_model=dict)
async def get_patient_statistics(
    time_range: Optional[str] = "month",
    current_user: UserResponse = Depends(get_current_user)
):
    """获取患者健康数据统计"""
    if current_user.role != "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 这里调用相应的服务层功能
    return {}

@router.get("/dashboard-data", response_model=Dict[str, Any])
async def get_dashboard_data(
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """获取患者仪表盘所需的所有数据"""
    if current_user["role"] != "patient":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="只有患者用户才能访问此接口"
        )
        
    user_id = str(current_user["_id"])
    return await DashboardService.get_all_dashboard_data(db, user_id)

@router.get("/health-metrics", response_model=List[Dict[str, Any]])
async def get_health_metrics(
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """获取患者健康指标数据"""
    if current_user["role"] != "patient":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="只有患者用户才能访问此接口"
        )
        
    user_id = str(current_user["_id"])
    return await DashboardService.get_health_metrics(db, user_id)

@router.get("/todo-items", response_model=List[Dict[str, Any]])
async def get_todo_items(
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """获取患者待办事项"""
    if current_user["role"] != "patient":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="只有患者用户才能访问此接口"
        )
        
    user_id = str(current_user["_id"])
    return await DashboardService.get_todo_items(db, user_id)

@router.get("/rehab-progress", response_model=Dict[str, Any])
async def get_rehab_progress(
    db: AsyncIOMotorClient = Depends(get_database),
    current_user: User = Depends(get_current_user)
):
    """获取患者康复进度"""
    if current_user["role"] != "patient":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="只有患者用户才能访问此接口"
        )
        
    user_id = str(current_user["_id"])
    rehab_progress = await DashboardService.get_rehab_progress(db, user_id)
    
    if not rehab_progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="未找到康复进度数据"
        )
    
    return rehab_progress 