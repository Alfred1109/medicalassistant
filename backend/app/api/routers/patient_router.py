from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import List, Optional, Dict, Any
from app.schemas.user import UserResponse
from app.schemas.health_record import HealthRecordResponse
from app.core.dependencies import (
    get_current_user, get_database, get_health_record_service,
)
from app.core.patient_access import ensure_patient_access
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.services.dashboard_service import DashboardService
from app.services.device_service import device_service
from app.services.communication_service import CommunicationService
from app.services.health_record_service import HealthRecordService
from app.models.user import User
from datetime import date, datetime, timedelta, timezone
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator
from pymongo.errors import PyMongoError
import json
from bson import ObjectId

router = APIRouter()

# 患者功能路由


# ── 对象级授权（患者本人语义 / 医护归属语义分离，AUTH01 共享实现） ─────────
_PATIENT_SCOPED_ROLES = ("patient", "doctor", "health_manager", "admin")


async def _resolve_scoped_patient_id(db: AsyncIOMotorDatabase, current_user, patient_id: Optional[str]) -> str:
    """解析本次查询的目标患者 ID，两种授权语义分开：

    - patient（本人语义）：仅限查自己；显式指定他人 patient_id → 403，
      不暴露他人数据存在性；
    - doctor / health_manager（归属语义）：指定 patient_id 后经共享
      ensure_patient_access 校验（患者不存在 → 404 PATIENT_NOT_FOUND，
      非归属医护 → 403 PATIENT_NOT_ASSIGNED）；
    - admin：豁免归属校验，可指定任意 patient_id；
    - 未指定 patient_id 时回落操作者本人（含 admin，如实返回其名下数据）。
    """
    uid = str(current_user.id)
    if not patient_id or patient_id == uid:
        return uid
    if current_user.role == "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问其他患者的数据")
    if current_user.role not in _PATIENT_SCOPED_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    await ensure_patient_access(db, patient_id, uid, current_user.role)
    return patient_id


# 健康档案
@router.get("/health-records", response_model=List[HealthRecordResponse])
async def get_health_record(
    patient_id: Optional[str] = None,
    record_type: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    health_record_service: HealthRecordService = Depends(get_health_record_service),
):
    """列出健康档案（2026-11-08 替换存根空对象）

    复用 HealthRecordService.list_health_records（health_records 集合，
    deleted!=True），无数据时如实返回空列表，不做伪造填充：
    - patient：本人档案；显式指定他人 patient_id → 403；
    - doctor / health_manager：指定 patient_id 且经归属校验（无归属 403）；
    - admin：豁免归属校验；
    - 支持 skip/limit 分页与 record_type 过滤（service 层真实过滤）。
    """
    if current_user.role not in _PATIENT_SCOPED_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    target_patient_id = await _resolve_scoped_patient_id(db, current_user, patient_id)
    try:
        records = await health_record_service.list_health_records(
            patient_id=target_patient_id,
            record_type=record_type,
            skip=skip,
            limit=limit,
        )
    except PyMongoError:
        raise HTTPException(status_code=503, detail="读取健康档案失败，请稍后重试")
    return records

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
def _normalize_device(device: Dict[str, Any]) -> Dict[str, Any]:
    """device_service 返回原始文档：_id 已为 str 但无 id 字段，
    patient_id 可能以 ObjectId 形态存储；统一规范化后输出。"""
    normalized = dict(device)
    if "_id" in normalized:
        normalized["id"] = str(normalized["_id"])
    if normalized.get("patient_id") is not None:
        normalized["patient_id"] = str(normalized["patient_id"])
    return normalized


class PatientDeviceBind(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_type: str
    name: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    connection_type: Optional[str] = None
    firmware_version: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


@router.get("/devices", response_model=List[dict])
async def get_bound_devices(
    patient_id: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """获取设备列表（2026-11-08 替换存根空列表）

    复用 device_service.get_user_devices（devices 集合 patient_id 字段，
    排除 deleted），无设备时如实返回空列表：
    - patient：本人设备；显式指定他人 patient_id → 403；
    - doctor / health_manager：指定 patient_id 且经归属校验（无归属 403）；
    - admin：豁免归属校验。
    """
    if current_user.role not in _PATIENT_SCOPED_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    target_patient_id = await _resolve_scoped_patient_id(db, current_user, patient_id)
    try:
        devices = await device_service.get_user_devices(target_patient_id)
    except PyMongoError:
        raise HTTPException(status_code=503, detail="读取设备列表失败，请稍后重试")
    return [_normalize_device(device) for device in devices]


@router.post("/devices", status_code=status.HTTP_201_CREATED, response_model=dict)
async def bind_device(
    device_data: PatientDeviceBind,
    current_user: UserResponse = Depends(get_current_user)
):
    """绑定新设备到本人（2026-11-08 替换存根假 ID）

    复用 device_service.bind_device（设备类型/固件版本真实校验，
    patient_id 即操作者本人，创建路径不触及他人对象）。
    """
    if current_user.role != "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    try:
        result = await device_service.bind_device(
            str(current_user.id), device_data.model_dump())
    except PyMongoError:
        raise HTTPException(status_code=503, detail="绑定设备失败，请稍后重试")
    if isinstance(result, dict) and result.get("error"):
        # service 层设备类型/固件版本校验失败，如实返回 400
        raise HTTPException(status_code=400, detail=result["error"])
    return _normalize_device(result)


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unbind_device(
    device_id: str,
    current_user: UserResponse = Depends(get_current_user)
):
    """解绑本人设备（2026-11-08 替换存根）

    复用 device_service.unbind_device：查询条件含 patient_id=操作者本人，
    属主语义对象级隔离（他人设备/不存在/畸形 ID 一律 False → 404）。
    """
    if current_user.role != "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    try:
        result = await device_service.unbind_device(str(current_user.id), device_id)
    except PyMongoError:
        raise HTTPException(status_code=503, detail="解绑设备失败，请稍后重试")
    if not result:
        raise HTTPException(status_code=404, detail="设备不存在或无权解绑")
    return None

# 医患沟通
class PatientMessageSend(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: str
    content: str = Field(min_length=1)
    message_type: str = "text"
    attachments: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None
    client_message_id: Optional[str] = None


@router.get("/communications", response_model=List[dict])
async def get_communications(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """本人会话列表（2026-11-08 替换存根空列表）

    复用 CommunicationService.get_conversations（conversations 集合，
    participant1/2_id 任一匹配本人），含真实未读计数与对方用户信息；
    无会话时如实返回空列表。
    """
    if current_user.role != "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    try:
        conversations = await CommunicationService.get_conversations(
            db, str(current_user.id), limit=limit, skip=skip)
    except PyMongoError:
        raise HTTPException(status_code=503, detail="读取沟通记录失败，请稍后重试")
    return conversations


@router.post("/communications", status_code=status.HTTP_201_CREATED, response_model=dict)
async def create_communication(
    message_data: PatientMessageSend,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """向本人参与的会话发送消息（2026-11-08 替换存根假 ID）

    复用 CommunicationService.send_message —— 与 /api/communications 写路径
    共用唯一消息服务实现（幂等键、会话摘要更新、WS 推送均由 service 承担），
    不另起第二条写路径。会话不存在 → 404，非会话参与者 → 403。
    """
    if current_user.role != "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    uid = str(current_user.id)
    conversation_id = message_data.conversation_id
    if not ObjectId.is_valid(conversation_id):
        raise HTTPException(status_code=422, detail="会话ID格式无效")
    try:
        conversation = await db.conversations.find_one({"_id": ObjectId(conversation_id)})
    except PyMongoError:
        raise HTTPException(status_code=503, detail="发送消息失败，请稍后重试")
    if not conversation:
        raise HTTPException(status_code=404, detail="会话不存在")
    if not await CommunicationService.is_conversation_participant(db, conversation_id, uid):
        raise HTTPException(status_code=403, detail="无权向该会话发送消息")
    try:
        message = await CommunicationService.send_message(
            db, conversation_id, uid, message_data.content,
            message_type=message_data.message_type,
            attachments=message_data.attachments,
            metadata=message_data.metadata,
            client_message_id=message_data.client_message_id,
        )
    except ValueError:
        # service 层参与者校验兜底（与前置校验同一判定来源）
        raise HTTPException(status_code=403, detail="无权向该会话发送消息")
    except PyMongoError:
        raise HTTPException(status_code=503, detail="发送消息失败，请稍后重试")
    return message

# 数据统计
@router.get("/statistics", response_model=dict)
async def get_patient_statistics(
    time_range: Optional[str] = "month",
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """获取患者健康数据统计（真实聚合，2026-11-08 替换存根空对象）

    字段语义（均来自真实集合，无数据时如实为 0）：
    - rehabPlans: 本人康复计划总数/进行中/已完成（rehab_plans.patient_id）
    - progress:   本人训练进度记录数/已完成数/完成率
                  （rehab_progress，completed 字段；完成率 = 已完成/总数*100，
                  无记录时为 0。该集合当前无写入方，通常为 0 —— 真实空数据而非存根）
    - implemented: 显式标记端点已实现真实聚合
    """
    if current_user.role != "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    try:
        user_id = str(current_user.id)
        plans_collection = db["rehab_plans"]
        total_plans = await plans_collection.count_documents({"patient_id": user_id})
        active_plans = await plans_collection.count_documents(
            {"patient_id": user_id, "status": "active"})
        completed_plans = await plans_collection.count_documents(
            {"patient_id": user_id, "status": "completed"})

        progress_collection = db["rehab_progress"]
        total_records = await progress_collection.count_documents({"patient_id": user_id})
        completed_records = await progress_collection.count_documents(
            {"patient_id": user_id, "completed": True})
        completion_rate = (completed_records / total_records * 100) if total_records > 0 else 0

        return {
            "implemented": True,
            "timeRange": time_range,
            "rehabPlans": {
                "total": total_plans,
                "active": active_plans,
                "completed": completed_plans,
            },
            "progress": {
                "totalRecords": total_records,
                "completedRecords": completed_records,
                "completionRate": round(completion_rate, 1),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"获取患者统计数据时出错: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取患者统计数据失败，请稍后重试"
        )

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
