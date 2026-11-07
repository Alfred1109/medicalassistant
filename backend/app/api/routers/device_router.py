"""
设备路由器
处理设备管理相关API请求
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any, Dict, List, Optional
from datetime import datetime
from bson import ObjectId
from pydantic import BaseModel, Field

from ...services.device_service import device_service
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


def _ensure_device_access(device: Dict, current_user: Any, roles: List[str]) -> None:
    """对象级粗判：属主或指定授权角色之外一律 403。"""
    if not _is_device_owner(device, current_user.id) and current_user.role not in roles:
        raise HTTPException(status_code=403, detail="无权访问此设备")


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
    devices = await device_service.get_user_devices(current_user.id)
    return [_to_device_response(device) for device in devices]


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: str,
    current_user: Any = Depends(get_current_active_user)
):
    """获取设备详情"""
    # 检查权限（存在性 + 属主/角色粗判）
    device = await _get_device_or_404(device_id)
    _ensure_device_access(device, current_user, ["doctor", "health_manager", "admin"])
    return _to_device_response(device)


@router.post("/bind", response_model=DeviceResponse)
async def bind_device(
    device: DeviceCreate,
    current_user: Any = Depends(get_current_active_user)
):
    """绑定新设备到当前用户"""
    result = await device_service.bind_device(current_user.id, device.dict())
    return _to_device_response(result)


@router.delete("/{device_id}/unbind")
async def unbind_device(
    device_id: str,
    current_user: Any = Depends(get_current_active_user)
):
    """解绑用户设备"""
    device = await _get_device_or_404(device_id)

    # 检查权限（解绑仅限属主或管理员）
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
    current_user: Any = Depends(get_current_active_user)
):
    """获取设备数据"""
    # 检查权限（存在性 + 属主/角色粗判）
    device = await _get_device_or_404(device_id)
    # TODO(AUTH01): 对象级授权待收敛（仅属主/角色粗判，未校验医患关系）
    _ensure_device_access(device, current_user, ["doctor", "health_manager", "admin"])
    
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
    current_user: Any = Depends(get_current_active_user)
):
    """
    同步设备数据
    """
    # 检查权限（存在性 + 属主/角色粗判）
    device = await _get_device_or_404(device_id)
    # TODO(AUTH01): 对象级授权待收敛（仅属主/角色粗判，未校验医患关系）
    _ensure_device_access(device, current_user, ["doctor", "health_manager", "admin"])

    return await device_service.sync_device_data(device_id)


@router.post("/{device_id}/repair", response_model=dict)
async def repair_device(
    device_id: str,
    current_user: Any = Depends(get_current_active_user)
):
    """
    自动修复设备异常状态
    """
    # 存在性校验：畸形 ID 与不存在的设备语义一致（404）
    await _get_device_or_404(device_id)

    # TODO(AUTH01): 对象级授权待收敛（仅角色粗判，未校验医患关系）
    if current_user.role not in ["doctor", "admin"]:
        raise HTTPException(
            status_code=403,
            detail="权限不足，只有医生或管理员可以执行设备修复操作"
        )

    # 调用设备修复服务
    repair_result = await device_service.auto_repair_device(device_id)
    return repair_result


@router.get("/{device_id}/status", response_model=DeviceStatusResponse)
async def get_device_status(
    device_id: str,
    current_user: Any = Depends(get_current_active_user)
):
    """获取设备状态"""
    # 检查权限（存在性 + 属主/角色粗判）
    device = await _get_device_or_404(device_id)
    # TODO(AUTH01): 对象级授权待收敛（仅属主/角色粗判，未校验医患关系）
    _ensure_device_access(device, current_user, ["doctor", "health_manager", "admin"])

    status = await device_service.get_device_status(device_id)
    return status


@router.put("/{device_id}/config", response_model=DeviceConfigResponse)
async def configure_device(
    device_id: str,
    config: DeviceConfigUpdate,
    current_user: Any = Depends(get_current_active_user)
):
    """配置设备"""
    # 检查权限（存在性 + 属主/角色粗判）
    device = await _get_device_or_404(device_id)
    # TODO(AUTH01): 对象级授权待收敛（仅属主/角色粗判，未校验医患关系）
    _ensure_device_access(device, current_user, ["doctor", "health_manager", "admin"])
    
    result = await device_service.configure_device(device_id, config.dict(exclude_unset=True))
    return result 