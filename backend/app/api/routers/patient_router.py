from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Dict, Any
from app.schemas.user import UserResponse
from app.core.dependencies import get_current_user, get_database
from motor.motor_asyncio import AsyncIOMotorClient
from app.services.dashboard_service import DashboardService
from app.models.user import User
from datetime import datetime, timedelta
import json
from bson import ObjectId

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
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorClient = Depends(get_database)
):
    """获取日常记录列表"""
    if current_user.role != "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    
    # 尝试从数据库获取记录
    user_id = str(current_user.id)
    collection = db.patientmanager.daily_records
    query = {"user_id": user_id}
    
    # 如果提供了日期范围，添加到查询条件
    if start_date:
        query["date"] = {"$gte": start_date}
    if end_date:
        if "date" in query:
            query["date"]["$lte"] = end_date
        else:
            query["date"] = {"$lte": end_date}
    
    # 从数据库查询记录
    records = await collection.find(query).to_list(length=100)
    
    # 如果没有记录，返回示例数据
    if not records:
        # 创建示例记录
        today = datetime.now()
        example_records = [
            {
                "_id": str(ObjectId()),
                "user_id": user_id,
                "date": (today - timedelta(days=2)).isoformat(),
                "pain_level": 3,
                "mood": "良好",
                "sleep": "6小时",
                "exercise_completed": True,
                "note": "今天完成了所有康复训练，感觉腿部力量有所恢复。"
            },
            {
                "_id": str(ObjectId()),
                "user_id": user_id,
                "date": (today - timedelta(days=1)).isoformat(),
                "pain_level": 2,
                "mood": "很好",
                "sleep": "7小时",
                "exercise_completed": True,
                "note": "今天继续训练，疼痛感有所减轻。"
            },
            {
                "_id": str(ObjectId()),
                "user_id": user_id,
                "date": today.isoformat(),
                "pain_level": 4,
                "mood": "一般",
                "sleep": "5小时",
                "exercise_completed": False,
                "note": "今天感觉有些疲惫，没有完成所有训练。"
            }
        ]
        
        # 将示例记录插入数据库
        try:
            await collection.insert_many(example_records)
            return example_records
        except Exception as e:
            # 如果数据库插入失败，仍然返回示例数据
            print(f"插入示例记录失败: {e}")
            return example_records
    
    # 为了JSON序列化，将ObjectId转换为字符串
    for record in records:
        record["_id"] = str(record["_id"])
    
    return records

@router.post("/daily-records", status_code=status.HTTP_201_CREATED)
async def create_daily_record(
    record_data: dict,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorClient = Depends(get_database)
):
    """创建日常记录"""
    if current_user.role != "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    
    # 添加用户ID到记录
    record_data["user_id"] = str(current_user.id)
    record_data["created_at"] = datetime.now().isoformat()
    
    # 插入数据库
    try:
        collection = db.patientmanager.daily_records
        result = await collection.insert_one(record_data)
        return {"id": str(result.inserted_id)}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建记录失败: {str(e)}"
        )

@router.delete("/daily-records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_daily_record(
    record_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorClient = Depends(get_database)
):
    """删除日常记录"""
    if current_user.role != "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    
    try:
        collection = db.patientmanager.daily_records
        query = {"_id": ObjectId(record_id), "user_id": str(current_user.id)}
        
        # 确保只能删除自己的记录
        result = await collection.delete_one(query)
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="未找到记录或无权删除"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除记录失败: {str(e)}"
        )
    
    return None

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