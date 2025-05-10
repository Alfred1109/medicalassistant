"""
设备数据验证服务
负责验证和转换设备数据，确保符合数据标准
"""
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

from ..models.device_data_standard import (
    DeviceDataValidator, 
    DeviceType,
    DEVICE_DATA_TYPES,
    FIRMWARE_VERSION_REGEX
)
import re

class DeviceDataValidatorService:
    """设备数据验证服务"""
    
    def validate_device_data(self, data: Dict, device_type: str) -> Tuple[bool, Optional[str]]:
        """
        验证设备数据是否符合标准
        
        参数:
        - data: 设备数据字典
        - device_type: 设备类型
        
        返回:
        - 验证结果元组 (是否有效, 错误消息)
        """
        if "data_type" not in data:
            return False, "缺少数据类型(data_type)字段"
            
        if "value" not in data:
            return False, "缺少数据值(value)字段"
        
        data_type_key = data["data_type"]
        value = data["value"]
        
        # 使用标准模型进行验证
        if not DeviceDataValidator.validate_device_data(data_type_key, value, device_type):
            return False, f"数据值不符合{data_type_key}类型的标准规范"
        
        # 检查元数据字段
        data_type_def = DeviceDataValidator.get_data_type_definition(data_type_key)
        if data_type_def and data_type_def.metadata_fields:
            metadata = data.get("metadata", {})
            if not isinstance(metadata, dict):
                return False, "元数据(metadata)字段应为对象类型"
                
            # 检查必要的元数据字段
            for field in data_type_def.metadata_fields:
                if field not in metadata:
                    return False, f"元数据中缺少必要字段: {field}"
        
        return True, None
    
    def format_device_data(self, data: Dict) -> Dict:
        """
        格式化设备数据，确保符合标准格式
        
        参数:
        - data: 设备数据字典
        
        返回:
        - 格式化后的数据字典
        """
        if "data_type" not in data or "value" not in data:
            return data
            
        data_type_key = data["data_type"]
        value = data["value"]
        
        # 使用标准模型进行格式化
        formatted_value = DeviceDataValidator.format_device_data(data_type_key, value)
        data["value"] = formatted_value
        
        # 确保时间戳格式正确
        if "timestamp" in data and isinstance(data["timestamp"], str):
            try:
                data["timestamp"] = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
            except ValueError:
                pass
        
        return data
    
    def batch_validate_device_data(self, data_list: List[Dict], device_type: str) -> Dict:
        """
        批量验证设备数据，返回有效和无效数据
        
        参数:
        - data_list: 设备数据列表
        - device_type: 设备类型
        
        返回:
        - 验证结果字典 {"valid": [...], "invalid": [...]}
        """
        valid_data = []
        invalid_data = []
        
        for data in data_list:
            is_valid, error_msg = self.validate_device_data(data, device_type)
            if is_valid:
                valid_data.append(self.format_device_data(data))
            else:
                invalid_data.append({
                    "data": data,
                    "error": error_msg
                })
        
        return {
            "valid": valid_data,
            "invalid": invalid_data
        }
    
    def validate_device_firmware(self, firmware_version: str) -> bool:
        """
        验证设备固件版本格式是否正确
        
        参数:
        - firmware_version: 固件版本字符串
        
        返回:
        - 是否有效
        """
        if not firmware_version:
            return False
            
        return bool(re.match(FIRMWARE_VERSION_REGEX, firmware_version))
    
    def get_supported_data_types_for_device(self, device_type: str) -> List[Dict]:
        """
        获取特定设备类型支持的所有数据类型
        
        参数:
        - device_type: 设备类型
        
        返回:
        - 数据类型定义列表
        """
        try:
            device_enum = DeviceType(device_type)
            supported_types = []
            
            for data_type in DEVICE_DATA_TYPES:
                if device_enum in data_type.device_types:
                    supported_types.append({
                        "name": data_type.name,
                        "key": data_type.key,
                        "unit": data_type.unit,
                        "description": data_type.description
                    })
            
            return supported_types
        except ValueError:
            # 设备类型不存在
            return []
    
    def get_data_type_details(self, data_type_key: str) -> Optional[Dict]:
        """
        获取数据类型的详细信息
        
        参数:
        - data_type_key: 数据类型键名
        
        返回:
        - 数据类型详情字典
        """
        data_type_def = DeviceDataValidator.get_data_type_definition(data_type_key)
        if not data_type_def:
            return None
            
        return data_type_def.dict()
    
    def validate_complex_device_data(self, data: Dict, device_type: str, strict_mode: bool = False) -> Dict:
        """
        对复杂设备数据进行高级验证
        
        参数:
        - data: 设备数据字典
        - device_type: 设备类型
        - strict_mode: 严格模式，如果为True则所有字段必须完全符合标准
        
        返回:
        - 验证结果 {"valid": bool, "errors": [], "warnings": []}
        """
        result = {
            "valid": True,
            "errors": [],
            "warnings": []
        }
        
        # 先进行基本验证
        is_valid, error_msg = self.validate_device_data(data, device_type)
        if not is_valid:
            result["valid"] = False
            result["errors"].append(error_msg)
            return result
        
        # 对特定设备类型进行高级验证
        data_type_key = data["data_type"]
        data_type_def = DeviceDataValidator.get_data_type_definition(data_type_key)
        
        if not data_type_def:
            result["valid"] = False
            result["errors"].append(f"未知的数据类型: {data_type_key}")
            return result
        
        # 检查单位是否一致
        if "unit" in data and data["unit"] != data_type_def.unit:
            msg = f"单位不匹配: 提供的是'{data['unit']}'，标准单位是'{data_type_def.unit}'"
            if strict_mode:
                result["valid"] = False
                result["errors"].append(msg)
            else:
                result["warnings"].append(msg)
        
        # 检查精度是否符合要求
        if data_type_def.precision is not None and isinstance(data["value"], (int, float)):
            current_precision = self._get_decimal_places(data["value"])
            if current_precision > data_type_def.precision:
                msg = f"数值精度过高: 提供了{current_precision}位小数，标准精度为{data_type_def.precision}位小数"
                if strict_mode:
                    result["valid"] = False
                    result["errors"].append(msg)
                else:
                    result["warnings"].append(msg)
        
        # 验证元数据的有效性（扩展验证）
        if "metadata" in data and data_type_def.metadata_fields:
            for field, value in data["metadata"].items():
                if field not in data_type_def.metadata_fields:
                    msg = f"未知的元数据字段: {field}"
                    if strict_mode:
                        result["valid"] = False
                        result["errors"].append(msg)
                    else:
                        result["warnings"].append(msg)
        
        return result
    
    def _get_decimal_places(self, value: float) -> int:
        """获取浮点数的小数位数"""
        str_value = str(value)
        if '.' in str_value:
            return len(str_value.split('.')[1])
        return 0
    
    def normalize_device_data(self, data: Dict, device_type: str) -> Dict:
        """
        标准化设备数据，确保符合标准并进行必要的转换
        
        参数:
        - data: 设备数据字典
        - device_type: 设备类型
        
        返回:
        - 标准化后的数据字典
        """
        # 先进行格式化
        result = self.format_device_data(data.copy())
        
        # 获取数据类型定义
        if "data_type" in result:
            data_type_def = DeviceDataValidator.get_data_type_definition(result["data_type"])
            
            if data_type_def:
                # 确保使用正确的单位
                result["unit"] = data_type_def.unit
                
                # 确保精度符合要求
                if data_type_def.precision is not None and isinstance(result["value"], (int, float)):
                    result["value"] = round(result["value"], data_type_def.precision)
                
                # 确保元数据字段完整
                if data_type_def.metadata_fields:
                    metadata = result.get("metadata", {})
                    for field in data_type_def.metadata_fields:
                        if field not in metadata:
                            metadata[field] = "未指定"
                    result["metadata"] = metadata
        
        return result

device_data_validator_service = DeviceDataValidatorService() 