from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from pydantic import BaseModel
from app.schemas.user import (
    UserResponse, DoctorCreate, PatientCreate, HealthManagerCreate,
)
from app.core.auth import get_current_user
from app.services.user_service import UserService
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.dependencies import get_database
from bson import ObjectId
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter()

# 系统管理员功能路由
# 角色守卫与 user_router 的管理员判断保持一致（current_user.role != "admin" -> 403）。
# 用户读/写能力复用 user_service 既有实现，不在本路由建立第二套写路径。

async def _require_admin(current_user: UserResponse) -> None:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")


def _created_at_date(doc: dict) -> str:
    created = doc.get("created_at")
    if isinstance(created, datetime):
        return created.strftime("%Y-%m-%d")
    return ""


# 医生管理
@router.get("/doctors", response_model=List[dict])
async def get_doctors(
    doctor_status: Optional[str] = Query(None, alias="status"),
    department: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """获取医生列表（真实数据，来自 users 集合 role=doctor；空库返回 []，不再回退模拟数据）"""
    await _require_admin(current_user)

    try:
        user_service = UserService(db)
        return await user_service.get_doctors(
            status=doctor_status, department=department, skip=skip, limit=limit
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取医生列表失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取医生列表失败: {e}"
        )


@router.post("/doctors", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
async def create_doctor(
    doctor_data: DoctorCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """创建新医生账号（走 user_service.create_user，含密码哈希，真实落库 users 集合）"""
    await _require_admin(current_user)

    try:
        user_service = UserService(db)
        return await user_service.create_user(doctor_data)
    except ValueError as e:
        # 邮箱重复等业务约束冲突
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建医生账号失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建医生账号失败: {e}"
        )


# 患者管理
@router.get("/patients", response_model=List[dict])
async def get_patients(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """获取患者列表（真实数据，来自 users 集合 role=patient；关键词搜索由前端客户端过滤）"""
    await _require_admin(current_user)

    try:
        docs = await db.users.find({"role": "patient"}).skip(skip).limit(limit).to_list(length=limit)
    except Exception as e:
        logger.error(f"查询患者列表失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询患者列表失败: {e}"
        )

    # 解析主治医生姓名：患者的 practitioners 存医生 ID，按页批量查一次
    practitioner_ids = []
    for doc in docs:
        practitioner_ids.extend(doc.get("practitioners", []) or [])
    id_to_name = await _resolve_user_names(db, practitioner_ids)

    patients = []
    for doc in docs:
        demographic = doc.get("demographic_info") or {}
        medical_info = doc.get("medical_info") or {}
        practitioner_names = [
            id_to_name[pid] for pid in (doc.get("practitioners") or []) if pid in id_to_name
        ]
        patients.append({
            "id": str(doc["_id"]),
            "name": doc.get("name", ""),
            "age": demographic.get("age"),
            "gender": demographic.get("gender", ""),
            "contact_number": demographic.get("contact_number", ""),
            "email": doc.get("email", ""),
            "address": demographic.get("address", ""),
            "diagnosis": medical_info.get("diagnosis", ""),
            "doctor_assigned": "、".join(practitioner_names),
            # users 集合无治疗方案/入院日期数据源，如实留空，不发明数据
            "treatment_plan": "",
            "admission_date": "",
            "status": "正常" if doc.get("is_active", True) else "停用",
        })
    return patients


async def _resolve_user_names(db: AsyncIOMotorDatabase, user_ids: List[str]) -> dict:
    """按 ID 批量解析用户姓名，非法/不存在 ID 静默跳过（不阻断列表返回）"""
    valid_ids = [ObjectId(uid) for uid in user_ids if ObjectId.is_valid(uid)]
    if not valid_ids:
        return {}
    try:
        docs = await db.users.find({"_id": {"$in": valid_ids}}).to_list(length=len(valid_ids))
    except Exception as e:
        logger.warning(f"解析用户姓名失败，主治医生列将留空: {e}")
        return {}
    return {str(doc["_id"]): doc.get("name", "") for doc in docs}


@router.post("/patients", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
async def create_patient(
    patient_data: PatientCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """创建新患者账号（走 user_service.create_user，含密码哈希，真实落库 users 集合）"""
    await _require_admin(current_user)

    try:
        user_service = UserService(db)
        return await user_service.create_user(patient_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建患者账号失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建患者账号失败: {e}"
        )


# 健康管理师管理
@router.get("/health-managers", response_model=List[dict])
async def get_health_managers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """获取健康管理师列表（真实数据，来自 users 集合 role=health_manager）"""
    await _require_admin(current_user)

    try:
        docs = await db.users.find({"role": "health_manager"}).skip(skip).limit(limit).to_list(length=limit)
    except Exception as e:
        logger.error(f"查询健康管理师列表失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询健康管理师列表失败: {e}"
        )

    managers = []
    for doc in docs:
        metadata = doc.get("metadata") or {}
        specialty_areas = doc.get("specialty_areas") or []
        managers.append({
            "id": str(doc["_id"]),
            "name": doc.get("name", ""),
            "department": doc.get("department", ""),
            "title": doc.get("certification", ""),
            "specialty": "、".join(specialty_areas) if specialty_areas else doc.get("specialty", ""),
            "email": doc.get("email", ""),
            "phone": metadata.get("phone", ""),
            "patients": len(doc.get("patients") or []),
            "status": "在职" if doc.get("is_active", True) else "停用",
            "join_date": _created_at_date(doc),
        })
    return managers


@router.post("/health-managers", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
async def create_health_manager(
    manager_data: HealthManagerCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """创建新健康管理师账号（走 user_service.create_user，含密码哈希，真实落库 users 集合）"""
    await _require_admin(current_user)

    try:
        user_service = UserService(db)
        return await user_service.create_user(manager_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建健康管理师账号失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建健康管理师账号失败: {e}"
        )


# 组织机构
def _flatten_address(address) -> str:
    """组织地址在前端按字符串渲染；模型中为结构化 dict，此处平铺为可读字符串"""
    if not address:
        return ""
    if isinstance(address, str):
        return address
    if isinstance(address, dict):
        if address.get("detail"):
            return str(address["detail"])
        return " ".join(str(v) for v in address.values() if v)
    return str(address)


def _org_to_row(doc: dict) -> dict:
    contact_info = doc.get("contact_info") or {}
    return {
        "id": str(doc["_id"]),
        "name": doc.get("name", ""),
        "type": doc.get("type", ""),
        "address": _flatten_address(doc.get("address")),
        "contact_person": contact_info.get("person") or contact_info.get("name", ""),
        "contact_phone": contact_info.get("phone", ""),
        "status": "active" if doc.get("active", True) else "inactive",
    }


@router.get("/organizations", response_model=List[dict])
async def get_organizations(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """获取组织机构列表（真实数据，来自 organizations 集合；空库返回 []）"""
    await _require_admin(current_user)

    try:
        docs = await db.organizations.find({}).to_list(length=1000)
    except Exception as e:
        logger.error(f"查询组织机构列表失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询组织机构列表失败: {e}"
        )
    return [_org_to_row(doc) for doc in docs]


class OrganizationCreate(BaseModel):
    name: str
    description: Optional[str] = None
    type: str = "hospital"
    address: Optional[dict] = None
    contact_info: Optional[dict] = None
    parent_id: Optional[str] = None


@router.post("/organizations", status_code=status.HTTP_201_CREATED)
async def create_organization(
    org_data: OrganizationCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """创建新组织机构（真实落库 organizations 集合）"""
    await _require_admin(current_user)

    doc = {
        "name": org_data.name,
        "description": org_data.description or "",
        "type": org_data.type,
        "address": org_data.address or {},
        "contact_info": org_data.contact_info or {},
        "parent_id": org_data.parent_id,
        "admin_ids": [],
        "tags": [],
        "active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    try:
        result = await db.organizations.insert_one(doc)
    except Exception as e:
        logger.error(f"创建组织机构失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建组织机构失败: {e}"
        )
    doc["_id"] = result.inserted_id
    return _org_to_row(doc)


# 标签管理
# 说明：标签域当前没有数据模型与集合（app/models/ 无 tag 模型，后端无任何集合读写 tags）。
# 按约定不发明集合：GET 如实返回真实空列表，POST 如实返回 501，待标签域建模后再实现。
@router.get("/tags", response_model=List[dict])
async def get_tags(
    category: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user)
):
    """获取标签列表（标签域尚无数据模型/集合，真实空态，非桩数据）"""
    await _require_admin(current_user)
    return []


@router.post("/tags", status_code=status.HTTP_201_CREATED)
async def create_tag(
    tag_data: dict,
    current_user: UserResponse = Depends(get_current_user)
):
    """创建新标签（未实现：标签域尚无数据模型/集合，不落库故返回 501）"""
    await _require_admin(current_user)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="标签域尚无数据模型与持久化集合，创建接口未实现"
    )


# 设备查看
@router.get("/devices", response_model=List[dict])
async def get_devices(
    device_status: Optional[str] = Query(None, alias="status"),
    device_type: Optional[str] = Query(None, alias="type"),
    current_user: UserResponse = Depends(get_current_user)
):
    """获取设备列表

    桩端点（恒 []）：前端管理端页面未调用此接口，设备域实现归属 device 域
    （/api/devices，device_router）。待设备域提供管理端查询能力后再接线。
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    return []


# 数据可视化
@router.get("/visualization/overview", response_model=dict)
async def get_visualization_overview(current_user: UserResponse = Depends(get_current_user)):
    """获取系统概览数据可视化

    桩端点（恒 {}）：前端未调用；系统概览统计已由 analytics 域真实实现，
    待前端接线后应改为复用 analytics_service 聚合，而非在本路由重复实现。
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    return {}


@router.get("/visualization/user-activities", response_model=dict)
async def get_user_activities(
    time_range: Optional[str] = "month",
    current_user: UserResponse = Depends(get_current_user)
):
    """获取用户活动数据可视化

    桩端点（恒 {}）：前端未调用；用户活动统计可由 audit_log/analytics 域聚合，
    待前端接线后再实现，不在本路由重复造轮子。
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    return {}
