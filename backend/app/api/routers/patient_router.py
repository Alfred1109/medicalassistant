from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Dict, Any
from app.schemas.user import UserResponse
from app.core.dependencies import get_current_user, get_database
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.services.dashboard_service import DashboardService
from app.models.user import User
from datetime import date, datetime, timedelta, timezone
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator
from pymongo.errors import PyMongoError
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

# 日常记录：保留历史集合名称，避免未经迁移让已有记录消失。
DAILY_RECORDS_COLLECTION = "patientmanager.daily_records"


def _record_day(value: str) -> date:
    """Accept calendar dates and legacy ISO timestamps without guessing a timezone."""
    if not isinstance(value, str):
        raise ValueError("日期必须为 ISO 日期或时间")
    try:
        return date.fromisoformat(value)
    except ValueError:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


class DailyRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: str
    pain_level: StrictInt = Field(ge=0, le=10)
    mood: str
    sleep: str
    exercise_completed: StrictBool
    note: str

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        _record_day(value)
        return value

    @field_validator("mood", "sleep", "note")
    @classmethod
    def nonempty_text(cls, value):
        if not value.strip():
            raise ValueError("内容不能为空")
        return value


def _daily_record_response(record):
    result = dict(record)
    result["_id"] = str(result["_id"])
    result["id"] = ("string:" + result["_id"]) if isinstance(record["_id"], str) else "object:" + result["_id"]
    if isinstance(result.get("date"), (date, datetime)):
        result["date"] = result["date"].isoformat()
    return result


async def _daily_record_query(db, record_id: str, user_id: str):
    if record_id.startswith("object:"):
        object_id = record_id[len("object:"):]
        if not ObjectId.is_valid(object_id):
            raise HTTPException(status_code=422, detail="记录ID格式无效")
        return {"_id": ObjectId(object_id), "user_id": user_id}
    if record_id.startswith("string:"):
        legacy_id = record_id[len("string:"):]
        if not legacy_id:
            raise HTTPException(status_code=422, detail="记录ID格式无效")
        return {"_id": legacy_id, "user_id": user_id}
    if not ObjectId.is_valid(record_id):
        raise HTTPException(status_code=422, detail="记录ID格式无效")
    # 兼容旧客户端的无类型 ID；冲突时拒绝，不任选一个历史记录。
    try:
        matches = await db[DAILY_RECORDS_COLLECTION].find({
            "_id": {"$in": [ObjectId(record_id), record_id]}, "user_id": user_id,
        }, {"_id": 1}).to_list(length=2)
    except PyMongoError:
        raise HTTPException(status_code=503, detail="读取记录失败，请稍后重试")
    if len(matches) > 1:
        raise HTTPException(status_code=409, detail="历史记录ID存在类型冲突，请刷新列表后重试")
    exact_id = matches[0]["_id"] if matches else ObjectId(record_id)
    return {"_id": exact_id, "user_id": user_id}


@router.get("/daily-records", response_model=List[dict])
async def get_daily_records(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """只读获取本人记录；日期筛选包含起止日，兼容历史 ISO 日期。"""
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="权限不足")
    try:
        start = _record_day(start_date) if start_date else None
        end = _record_day(end_date) if end_date else None
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="日期格式无效")
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")
    try:
        records = await db[DAILY_RECORDS_COLLECTION].find(
            {"user_id": str(current_user.id)}
        ).to_list(length=None)
    except PyMongoError:
        raise HTTPException(status_code=503, detail="读取记录失败，请稍后重试")
    result = []
    for record in records:
        response = _daily_record_response(record)
        try:
            day = _record_day(response.get("date"))
        except (ValueError, TypeError):
            # 无效历史日期仍在无筛选列表中显示，不能静默丢弃或伪造日期。
            if start or end:
                continue
        else:
            if (start and day < start) or (end and day > end):
                continue
        result.append(response)
    return sorted(result, key=lambda item: (str(item.get("date", "")), item["id"]), reverse=True)


@router.post("/daily-records", status_code=status.HTTP_201_CREATED, response_model=dict)
async def create_daily_record(
    record_data: DailyRecordCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="权限不足")
    record = record_data.model_dump()
    record["user_id"] = str(current_user.id)
    record["created_at"] = datetime.now(timezone.utc)
    try:
        result = await db[DAILY_RECORDS_COLLECTION].insert_one(record)
    except PyMongoError:
        raise HTTPException(status_code=503, detail="创建记录失败，请稍后重试")
    record["_id"] = result.inserted_id
    return _daily_record_response(record)


@router.put("/daily-records/{record_id}", response_model=dict)
async def update_daily_record(
    record_id: str,
    record_data: DailyRecordCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="权限不足")
    query = await _daily_record_query(db, record_id, str(current_user.id))
    changes = record_data.model_dump()
    changes["updated_at"] = datetime.now(timezone.utc)
    try:
        from pymongo import ReturnDocument
        record = await db[DAILY_RECORDS_COLLECTION].find_one_and_update(
            query, {"$set": changes}, return_document=ReturnDocument.AFTER,
        )
    except PyMongoError:
        raise HTTPException(status_code=503, detail="更新记录失败，请稍后重试")
    if record is None:
        raise HTTPException(status_code=404, detail="未找到记录或无权修改")
    return _daily_record_response(record)


@router.delete("/daily-records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_daily_record(
    record_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="权限不足")
    query = await _daily_record_query(db, record_id, str(current_user.id))
    # 按确切 BSON 类型定位，不能因历史字符串 ID 冲突而误删。
    try:
        result = await db[DAILY_RECORDS_COLLECTION].delete_one(query)
    except PyMongoError:
        raise HTTPException(status_code=503, detail="删除记录失败，请稍后重试")
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="未找到记录或无权删除")
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