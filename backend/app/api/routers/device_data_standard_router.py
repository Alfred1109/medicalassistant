"""
设备数据标准路由器
提供设备数据标准的查询和管理API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from ...models.device_data_standard import DeviceType, DEVICE_DATA_TYPES, METADATA_FIELDS, DEVICE_DATA_STANDARD_VERSION
from ...services.device_data_validator_service import device_data_validator_service
from ...services.device_service import device_service
from ...core.dependencies import get_current_user

router = APIRouter(prefix="/device-standards", tags=["device-standards"])

@router.get("/data-types", response_model=List[Dict])
async def get_supported_data_types(
    device_type: Optional[str] = None,
    current_user: Dict = Depends(get_current_user)
):
    """
    获取支持的数据类型列表
    
    参数:
    - device_type: 可选的设备类型，如果提供则只返回该设备类型支持的数据类型
    
    返回:
    - 数据类型列表
    """
    return await device_service.get_supported_data_types(device_type)

@router.get("/device-types", response_model=List[Dict])
async def get_device_types():
    """
    获取支持的设备类型列表
    
    返回:
    - 设备类型列表
    """
    return [{"value": device_type.value, "name": device_type.value} for device_type in DeviceType]

@router.get("/metadata-fields", response_model=Dict)
async def get_metadata_fields():
    """
    获取元数据字段说明
    
    返回:
    - 元数据字段说明字典
    """
    return METADATA_FIELDS

@router.get("/data-type/{data_type_key}", response_model=Dict)
async def get_data_type_details(data_type_key: str):
    """
    获取数据类型详情
    
    参数:
    - data_type_key: 数据类型键名
    
    返回:
    - 数据类型详情
    """
    data_type_details = device_data_validator_service.get_data_type_details(data_type_key)
    if not data_type_details:
        raise HTTPException(status_code=404, detail=f"数据类型 '{data_type_key}' 不存在")
    return data_type_details

@router.get("/version", response_model=Dict)
async def get_standard_version():
    """
    获取数据标准版本
    
    返回:
    - 版本信息
    """
    return {
        "version": DEVICE_DATA_STANDARD_VERSION,
        "release_date": "2023-06-01",
        "status": "active"
    }

@router.post("/validate", response_model=Dict)
async def validate_device_data(
    data: Dict,
    device_type: str,
    current_user: Dict = Depends(get_current_user)
):
    """
    验证设备数据是否符合标准
    
    参数:
    - data: 设备数据
    - device_type: 设备类型
    
    返回:
    - 验证结果
    """
    is_valid, error_msg = device_data_validator_service.validate_device_data(data, device_type)
    return {
        "valid": is_valid,
        "error_message": error_msg
    }

@router.post("/batch-validate", response_model=Dict)
async def batch_validate_device_data(
    data_list: List[Dict],
    device_type: str,
    current_user: Dict = Depends(get_current_user)
):
    """
    批量验证设备数据
    
    参数:
    - data_list: 设备数据列表
    - device_type: 设备类型
    
    返回:
    - 验证结果，包含有效和无效数据
    """
    validation_result = device_data_validator_service.batch_validate_device_data(data_list, device_type)
    return {
        "valid_count": len(validation_result["valid"]),
        "invalid_count": len(validation_result["invalid"]),
        "invalid_data": validation_result["invalid"]
    } 