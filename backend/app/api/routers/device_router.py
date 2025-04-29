"""
设备路由器
处理设备管理相关API请求
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from ...services.device_service import device_service
from ...services.user_service import user_service
from ...auth.jwt_auth import get_current_user

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
    value: any = Field(..., description="数据值")
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
    user=Depends(get_current_user)
):
    """获取当前用户绑定的设备列表"""
    devices = await device_service.get_user_devices(user["_id"])
    return devices


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: str,
    user=Depends(get_current_user)
):
    """获取设备详情"""
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    # 检查权限
    if device.get("patient_id") != user["_id"] and user.get("role") not in ["doctor", "health_manager", "admin"]:
        raise HTTPException(status_code=403, detail="无权访问此设备")
    
    return device


@router.post("/bind", response_model=DeviceResponse)
async def bind_device(
    device: DeviceCreate,
    user=Depends(get_current_user)
):
    """绑定新设备到当前用户"""
    result = await device_service.bind_device(user["_id"], device.dict())
    return result


@router.delete("/{device_id}/unbind")
async def unbind_device(
    device_id: str,
    user=Depends(get_current_user)
):
    """解绑用户设备"""
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    # 检查权限
    if device.get("patient_id") != user["_id"] and user.get("role") not in ["admin"]:
        raise HTTPException(status_code=403, detail="无权解绑此设备")
    
    result = await device_service.unbind_device(user["_id"], device_id)
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
    user=Depends(get_current_user)
):
    """获取设备数据"""
    # 检查权限
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    if device.get("patient_id") != user["_id"] and user.get("role") not in ["doctor", "health_manager", "admin"]:
        raise HTTPException(status_code=403, detail="无权访问此设备数据")
    
    data = await device_service.get_device_data(
        device_id, 
        start_date=start_date,
        end_date=end_date,
        data_type=data_type,
        limit=limit
    )
    return data


@router.post("/{device_id}/sync", response_model=DeviceSyncResponse)
async def sync_device_data(
    device_id: str,
    user=Depends(get_current_user)
):
    """同步设备数据"""
    # 检查权限
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    if device.get("patient_id") != user["_id"] and user.get("role") not in ["doctor", "health_manager", "admin"]:
        raise HTTPException(status_code=403, detail="无权同步此设备数据")
    
    result = await device_service.sync_device_data(device_id)
    return result


@router.get("/{device_id}/status", response_model=DeviceStatusResponse)
async def get_device_status(
    device_id: str,
    user=Depends(get_current_user)
):
    """获取设备状态"""
    # 检查权限
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    if device.get("patient_id") != user["_id"] and user.get("role") not in ["doctor", "health_manager", "admin"]:
        raise HTTPException(status_code=403, detail="无权访问此设备状态")
    
    status = await device_service.get_device_status(device_id)
    return status


@router.put("/{device_id}/config", response_model=DeviceConfigResponse)
async def configure_device(
    device_id: str,
    config: DeviceConfigUpdate,
    user=Depends(get_current_user)
):
    """配置设备"""
    # 检查权限
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    if device.get("patient_id") != user["_id"] and user.get("role") not in ["doctor", "health_manager", "admin"]:
        raise HTTPException(status_code=403, detail="无权配置此设备")
    
    result = await device_service.configure_device(device_id, config.dict(exclude_unset=True))
    return result 