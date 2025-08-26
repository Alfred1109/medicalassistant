"""
设备数据标准化定义
定义各类康复设备的数据格式、单位和验证规则
"""
from enum import Enum
from typing import Dict, List, Optional, Union, Any
from pydantic import BaseModel, Field, validator
import re
from datetime import datetime

# 设备类型枚举
class DeviceType(str, Enum):
    BLOOD_PRESSURE = "血压计"
    GLUCOSE_METER = "血糖仪"
    THERMOMETER = "体温计"
    ECG = "心电图"
    SCALE = "体重秤"
    WEARABLE = "手环"
    GENERIC = "其他"

# 设备连接类型枚举
class ConnectionType(str, Enum):
    BLUETOOTH = "bluetooth"
    WIFI = "wifi"
    USB = "usb"
    CELLULAR = "cellular"
    OTHER = "other"

# 设备状态枚举
class DeviceStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"
    SYNCING = "syncing"
    IDLE = "idle"

# 数据类型定义
class DataTypeDefinition(BaseModel):
    """数据类型定义模型"""
    name: str = Field(..., description="数据类型名称")
    key: str = Field(..., description="数据类型键名")
    unit: str = Field(..., description="数据单位")
    min_value: Optional[float] = Field(None, description="最小有效值")
    max_value: Optional[float] = Field(None, description="最大有效值")
    precision: Optional[int] = Field(None, description="精度(小数位数)")
    format: Optional[str] = Field(None, description="格式化规则")
    validation_regex: Optional[str] = Field(None, description="验证正则表达式")
    device_types: List[DeviceType] = Field(..., description="适用的设备类型")
    metadata_fields: Optional[List[str]] = Field(None, description="元数据字段")
    description: str = Field(..., description="数据类型描述")

    def validate_value(self, value: Any) -> bool:
        """验证数据值是否有效"""
        # 检查数值范围
        if isinstance(value, (int, float)):
            if self.min_value is not None and value < self.min_value:
                return False
            if self.max_value is not None and value > self.max_value:
                return False
            return True
        
        # 检查字符串格式
        if isinstance(value, str) and self.validation_regex:
            return bool(re.match(self.validation_regex, value))
        
        # 复杂类型
        if isinstance(value, dict):
            # 根据数据类型特定的验证逻辑
            if self.key == "sleep":
                return "total_minutes" in value
            if self.key == "ecg_waveform":
                return "waveform_sample" in value
            
        return True

    def format_value(self, value: Any) -> Any:
        """根据定义格式化数据值"""
        if self.precision is not None and isinstance(value, (int, float)):
            return round(value, self.precision)
        return value

# 定义各种设备的数据类型
DEVICE_DATA_TYPES = [
    # 血压计数据类型
    DataTypeDefinition(
        name="收缩压",
        key="blood_pressure_systolic",
        unit="mmHg",
        min_value=60,
        max_value=250,
        precision=0,
        device_types=[DeviceType.BLOOD_PRESSURE],
        metadata_fields=["measurement_position", "measurement_state"],
        description="血压计测量的收缩压(高压)值"
    ),
    DataTypeDefinition(
        name="舒张压",
        key="blood_pressure_diastolic",
        unit="mmHg",
        min_value=30,
        max_value=150,
        precision=0,
        device_types=[DeviceType.BLOOD_PRESSURE],
        metadata_fields=["measurement_position", "measurement_state"],
        description="血压计测量的舒张压(低压)值"
    ),
    DataTypeDefinition(
        name="脉搏",
        key="pulse",
        unit="bpm",
        min_value=30,
        max_value=200,
        precision=0,
        device_types=[DeviceType.BLOOD_PRESSURE, DeviceType.ECG, DeviceType.WEARABLE],
        metadata_fields=["measurement_method"],
        description="心跳脉搏频率"
    ),
    
    # 血糖仪数据类型
    DataTypeDefinition(
        name="血糖",
        key="blood_glucose",
        unit="mmol/L",
        min_value=1.0,
        max_value=33.3,
        precision=1,
        device_types=[DeviceType.GLUCOSE_METER],
        metadata_fields=["measurement_time", "meal_relation"],
        description="血糖仪测量的血糖值"
    ),
    
    # 体温计数据类型
    DataTypeDefinition(
        name="体温",
        key="body_temperature",
        unit="°C",
        min_value=35.0,
        max_value=42.0,
        precision=1,
        device_types=[DeviceType.THERMOMETER, DeviceType.WEARABLE],
        metadata_fields=["measurement_method"],
        description="体温计测量的体温值"
    ),
    
    # 心电图数据类型
    DataTypeDefinition(
        name="心电图波形",
        key="ecg_waveform",
        unit="mV",
        device_types=[DeviceType.ECG],
        metadata_fields=["device_mode", "lead_type", "filtering"],
        description="心电图设备记录的心电波形数据"
    ),
    DataTypeDefinition(
        name="心率",
        key="heart_rate",
        unit="bpm",
        min_value=30,
        max_value=220,
        precision=0,
        device_types=[DeviceType.ECG, DeviceType.WEARABLE],
        metadata_fields=["measurement_method"],
        description="心率值"
    ),
    
    # 体重秤数据类型
    DataTypeDefinition(
        name="体重",
        key="weight",
        unit="kg",
        min_value=0.5,
        max_value=300.0,
        precision=1,
        device_types=[DeviceType.SCALE],
        description="体重秤测量的体重值"
    ),
    DataTypeDefinition(
        name="体脂率",
        key="body_fat_percentage",
        unit="%",
        min_value=3.0,
        max_value=70.0,
        precision=1,
        device_types=[DeviceType.SCALE],
        description="体重秤测量的体脂率"
    ),
    DataTypeDefinition(
        name="肌肉量",
        key="muscle_mass",
        unit="kg",
        min_value=0.5,
        max_value=100.0,
        precision=1,
        device_types=[DeviceType.SCALE],
        description="体重秤测量的肌肉量"
    ),
    DataTypeDefinition(
        name="水分率",
        key="water_percentage",
        unit="%",
        min_value=20.0,
        max_value=80.0,
        precision=1,
        device_types=[DeviceType.SCALE],
        description="体重秤测量的体内水分率"
    ),
    
    # 可穿戴设备数据类型
    DataTypeDefinition(
        name="步数",
        key="steps",
        unit="steps",
        min_value=0,
        max_value=1000000,
        precision=0,
        device_types=[DeviceType.WEARABLE],
        metadata_fields=["duration"],
        description="可穿戴设备记录的步数"
    ),
    DataTypeDefinition(
        name="睡眠",
        key="sleep",
        unit="minutes",
        device_types=[DeviceType.WEARABLE],
        metadata_fields=["sleep_start", "sleep_end"],
        description="可穿戴设备记录的睡眠数据"
    ),
    DataTypeDefinition(
        name="血氧饱和度",
        key="oxygen_saturation",
        unit="%",
        min_value=70.0,
        max_value=100.0,
        precision=1,
        device_types=[DeviceType.WEARABLE],
        metadata_fields=["measurement_method"],
        description="可穿戴设备测量的血氧饱和度"
    ),
    DataTypeDefinition(
        name="活动量",
        key="activity",
        unit="kcal",
        min_value=0,
        max_value=10000,
        precision=0,
        device_types=[DeviceType.WEARABLE],
        metadata_fields=["activity_type", "duration"],
        description="可穿戴设备记录的活动消耗"
    )
]

# 设备数据验证器
class DeviceDataValidator:
    """设备数据验证器，用于验证设备数据是否符合标准"""
    
    @staticmethod
    def get_data_type_definition(data_type_key: str) -> Optional[DataTypeDefinition]:
        """根据数据类型键名获取数据类型定义"""
        for data_type in DEVICE_DATA_TYPES:
            if data_type.key == data_type_key:
                return data_type
        return None
    
    @staticmethod
    def validate_device_data(data_type_key: str, value: Any, device_type: str) -> bool:
        """
        验证设备数据是否符合标准
        
        参数:
        - data_type_key: 数据类型键名
        - value: 数据值
        - device_type: 设备类型
        
        返回:
        - 是否有效
        """
        data_type_def = DeviceDataValidator.get_data_type_definition(data_type_key)
        if not data_type_def:
            return False
            
        # 检查设备类型是否支持此数据类型
        if DeviceType(device_type) not in data_type_def.device_types:
            return False
            
        # 验证数据值
        return data_type_def.validate_value(value)
    
    @staticmethod
    def format_device_data(data_type_key: str, value: Any) -> Any:
        """
        格式化设备数据
        
        参数:
        - data_type_key: 数据类型键名
        - value: 数据值
        
        返回:
        - 格式化后的数据值
        """
        data_type_def = DeviceDataValidator.get_data_type_definition(data_type_key)
        if not data_type_def:
            return value
            
        return data_type_def.format_value(value)

# 元数据字段说明
METADATA_FIELDS = {
    "measurement_position": "测量位置，如'left_arm'(左臂)、'right_arm'(右臂)",
    "measurement_state": "测量状态，如'sitting'(坐姿)、'lying'(卧姿)",
    "measurement_method": "测量方法，如'optical'(光学)、'oscillometric'(示波法)",
    "measurement_time": "测量时间，如'fasting'(空腹)、'postprandial'(餐后)",
    "meal_relation": "与餐食的关系，如'before_meal'(餐前)、'after_meal'(餐后)",
    "device_mode": "设备模式，如'continuous'(连续)、'single'(单次)",
    "lead_type": "导联类型，如'single_lead'(单导联)、'multi_lead'(多导联)",
    "filtering": "信号过滤方式，如'bandpass'(带通滤波)、'notch'(陷波滤波)",
    "activity_type": "活动类型，如'walking'(步行)、'running'(跑步)、'cycling'(骑行)",
    "duration": "持续时间，如'daily'(全天)、'hourly'(小时)",
    "sleep_start": "睡眠开始时间",
    "sleep_end": "睡眠结束时间"
}

# 设备固件版本格式正则表达式
FIRMWARE_VERSION_REGEX = r'^(\d+)\.(\d+)\.(\d+)$'

# 设备数据标准版本
DEVICE_DATA_STANDARD_VERSION = "1.0.0" 