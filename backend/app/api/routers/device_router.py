"""
设备路由器
处理设备管理相关API请求
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any, Dict, List, Optional
from datetime import datetime
from bson import ObjectId
from pydantic import BaseModel, Field

from motor.motor_asyncio import AsyncIOMotorDatabase

from ...db.mongodb import get_database
from ...core.patient_access import ensure_patient_access
from ...services.device_service import (
    device_service,
    DEVICE_READ_ROLES,
    DEVICE_MUTATE_ROLES,
)
from ...core.auth import get_current_active_user


def _is_device_owner(device: Dict, user_id: str) -> bool:
    """判断当前用户是否为设备属主。

    device_service.get_device 返回原始文档，patient_id 可能以 ObjectId
    形态存储，统一转 str 后比较。
    """
    return str(device.get("patient_id")) == str(user_id)


async def _get_device_or_404(device_id: str) -> Dict:
    """获取设备或抛 404：畸形 ID 与不存在的设备语义一致（404）。"""
    if not ObjectId.is_valid(device_id):
        raise HTTPException(status_code=404, detail="设备不存在")
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    return device


async def _ensure_device_access(
    device: Dict,
    current_user: Any,
    db: AsyncIOMotorDatabase,
    roles: List[str],
    detail: str = "无权访问此设备",
) -> None:
    """AUTH01 对象级授权第二层（按 device_id 寻址，复用 7c5d690 两层模式）。

    调用前设备文档已加载（设备不存在 → 404 先于本判断）。语义分层：
    - admin 豁免（全局设备管理职责）；
    - 患者本人访问自己名下设备走属主判断（属主语义，不走医护归属，
      不把患者当"无归属医护"错拒）；
    - 其他用户须具备授权角色，且与设备所属患者存在归属关系
      （共享 ensure_patient_access：患者不存在 → 404 PATIENT_NOT_FOUND，
      非归属医护 → 403 PATIENT_NOT_ASSIGNED）；
    - 设备文档缺失 patient_id 的畸形数据按 404 处置（不暴露存在性）。
    """
    if current_user.role == "admin" or _is_device_owner(device, current_user.id):
        return
    patient_id = device.get("patient_id")
    if not patient_id:
        raise HTTPException(status_code=404, detail="设备不存在")
    if current_user.role not in roles:
        raise HTTPException(status_code=403, detail=detail)
    await ensure_patient_access(db, str(patient_id),
                                str(current_user.id), current_user.role)


def _to_device_response(device: Any) -> Any:
    """service 文档以 _id 存储主键、patient_id 可能以 ObjectId 存储，
    而 DeviceResponse/DeviceDataResponse 以 id/patient_id: str 声明；
    返回前规范字段名与形态，否则响应校验必然失败。"""
    if isinstance(device, dict):
        normalized = dict(device)
        if "_id" in normalized and "id" not in normalized:
            normalized["id"] = str(normalized["_id"])
        if normalized.get("patient_id") is not None:
            normalized["patient_id"] = str(normalized["patient_id"])
        return normalized
    return device

router = APIRouter(prefix="/devices", tags=["devices"])


# 设备请求/响应模型
class DeviceBase(BaseModel):
    device_type: str = Field(..., description="设备类型，如'血压计'、'血糖仪'等")
    name: str = Field(..., description="设备名称")
    manufacturer: Optional[str] = Field(None, description="制造商")
    model: Optional[str] = Field(None, description="型号")
    connection_type: Optional[str] = Field(None, description="连接类型，如'bluetooth'、'wifi'等")
    firmware_version: Optional[str] = Field(None, description="固件版本")
    settings: Optional[Dict] = Field(None, description="设备设置")


class DeviceCreate(DeviceBase):
    pass


class DeviceResponse(DeviceBase):
    id: str = Field(..., description="设备ID")
    patient_id: Optional[str] = Field(None, description="患者ID")
    status: str = Field(..., description="设备状态")
    last_connected: Optional[datetime] = Field(None, description="最后连接时间")
    battery_level: Optional[float] = Field(None, description="电池电量")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    class Config:
        orm_mode = True


class DeviceStatusResponse(BaseModel):
    status: str = Field(..., description="设备状态")
    battery_level: int = Field(..., description="电池电量")
    signal_strength: int = Field(..., description="信号强度")
    last_sync_time: Optional[datetime] = Field(None, description="最后同步时间")
    message: Optional[str] = Field(None, description="状态消息")


class DeviceDataBase(BaseModel):
    timestamp: datetime = Field(..., description="数据时间戳")
    data_type: str = Field(..., description="数据类型")
    value: Any = Field(..., description="数据值")
    unit: str = Field(..., description="单位")
    metadata: Optional[Dict] = Field(None, description="元数据")


class DeviceDataResponse(DeviceDataBase):
    id: str = Field(..., description="数据ID")
    device_id: str = Field(..., description="设备ID")
    created_at: datetime = Field(..., description="创建时间")

    class Config:
        orm_mode = True


class DeviceSyncResponse(BaseModel):
    success: bool = Field(..., description="同步是否成功")
    message: str = Field(..., description="消息")
    new_data: Optional[List[DeviceDataBase]] = Field(None, description="新同步的数据")


class DeviceConfigUpdate(BaseModel):
    sync_frequency: Optional[str] = Field(None, description="同步频率")
    notifications_enabled: Optional[bool] = Field(None, description="是否启用通知")
    custom_name: Optional[str] = Field(None, description="自定义名称")
    alarm_settings: Optional[Dict] = Field(None, description="警报设置")


class DeviceConfigResponse(BaseModel):
    success: bool = Field(..., description="配置是否成功")
    message: str = Field(..., description="消息")


# API路由定义
@router.get("/", response_model=List[DeviceResponse])
async def get_user_devices(
    current_user: Any = Depends(get_current_active_user)
):
    """获取当前用户绑定的设备列表"""
    # 无需对象级归属校验：查询对象即操作者本人（按 current_user.id 过滤），
    # 不存在跨患者访问面。
    devices = await device_service.get_user_devices(current_user.id)
    return [_to_device_response(device) for device in devices]


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: str,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """获取设备详情"""
    # AUTH01：存在性校验（404 先行）+ 对象级归属校验
    device = await _get_device_or_404(device_id)
    await _ensure_device_access(device, current_user, db, list(DEVICE_READ_ROLES))
    return _to_device_response(device)


@router.post("/bind", response_model=DeviceResponse)
async def bind_device(
    device: DeviceCreate,
    current_user: Any = Depends(get_current_active_user)
):
    """绑定新设备到当前用户"""
    # 无需对象级归属校验：设备绑定目标即操作者本人（current_user.id），
    # 创建路径不触及他人对象。
    result = await device_service.bind_device(current_user.id, device.dict())
    return _to_device_response(result)


@router.delete("/{device_id}/unbind")
async def unbind_device(
    device_id: str,
    current_user: Any = Depends(get_current_active_user)
):
    """解绑用户设备"""
    device = await _get_device_or_404(device_id)

    # 无需医患归属校验：解绑属变更操作且仅限属主本人或管理员，
    # 授权规则本身即对象级（非属主医护一律排除，无归属关系可回旋）。
    if not _is_device_owner(device, current_user.id) and current_user.role not in ["admin"]:
        raise HTTPException(status_code=403, detail="无权解绑此设备")

    result = await device_service.unbind_device(current_user.id, device_id)
    if result:
        return {"message": "设备已解绑"}
    else:
        raise HTTPException(status_code=400, detail="解绑设备失败")


@router.get("/{device_id}/data", response_model=List[DeviceDataResponse])
async def get_device_data(
    device_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    data_type: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """获取设备数据"""
    # AUTH01：存在性校验（404 先行）+ 对象级归属校验
    device = await _get_device_or_404(device_id)
    await _ensure_device_access(device, current_user, db, list(DEVICE_READ_ROLES))

    data = await device_service.get_device_data(
        device_id,
        start_date=start_date,
        end_date=end_date,
        data_type=data_type,
        limit=limit
    )
    return [_to_device_response(item) for item in data]


@router.post("/{device_id}/sync", response_model=dict)
async def sync_device_data(
    device_id: str,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    同步设备数据
    """
    # AUTH01：存在性校验（404 先行）+ 对象级归属校验（沿用只读角色语义）
    device = await _get_device_or_404(device_id)
    await _ensure_device_access(device, current_user, db, list(DEVICE_READ_ROLES))

    return await device_service.sync_device_data(device_id)


@router.post("/{device_id}/repair", response_model=dict)
async def repair_device(
    device_id: str,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    自动修复设备异常状态
    """
    # 存在性校验：畸形 ID 与不存在的设备语义一致（404）
    device = await _get_device_or_404(device_id)

    # AUTH01 对象级授权（变更守卫）：属主患者可维修自己名下设备（此前属主
    # 患者被"只有医生或管理员"一刀切 403，即患者角色错配缺陷）；
    # 健康管理师只读，不可执行维修等变更操作；非属主医生须与设备所属患者
    # 存在归属关系（ensure_patient_access）。
    await _ensure_device_access(
        device, current_user, db, list(DEVICE_MUTATE_ROLES),
        detail="无权修复此设备：仅设备属主、医生或管理员可执行维修操作")

    # 调用设备修复服务
    repair_result = await device_service.auto_repair_device(device_id)
    return repair_result


@router.get("/{device_id}/status", response_model=DeviceStatusResponse)
async def get_device_status(
    device_id: str,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """获取设备状态"""
    # AUTH01：存在性校验（404 先行）+ 对象级归属校验
    device = await _get_device_or_404(device_id)
    await _ensure_device_access(device, current_user, db, list(DEVICE_READ_ROLES))

    status = await device_service.get_device_status(device_id)
    return status


@router.put("/{device_id}/config", response_model=DeviceConfigResponse)
async def configure_device(
    device_id: str,
    config: DeviceConfigUpdate,
    current_user: Any = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """配置设备"""
    # AUTH01 对象级授权（变更守卫）：配置属变更操作，健康管理师只读不可
    # 变更（缺陷 B 统一）；属主患者可配置自己名下设备；非属主医生须与
    # 设备所属患者存在归属关系（ensure_patient_access）。
    device = await _get_device_or_404(device_id)
    await _ensure_device_access(device, current_user, db, list(DEVICE_MUTATE_ROLES))

    result = await device_service.configure_device(device_id, config.dict(exclude_unset=True))
    return result
