"""
健康数据阈值和预警的Schema定义
"""

from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

from app.schemas.base import PyObjectId, TimestampModel, PydanticConfig


class AlertLevel(str, Enum):
    """预警级别枚举"""
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    """预警状态枚举"""
    ACTIVE = "active"
    RESOLVED = "resolved"
    IGNORED = "ignored"


# 基础阈值模型
class ThresholdBase(BaseModel):
    """阈值基础模型"""
    name: str
    data_type: str
    vital_type: Optional[str] = None
    test_name: Optional[str] = None
    normal_range: Dict[str, Any] = {}
    warning_range: Dict[str, Any] = {}
    critical_range: Dict[str, Any] = {}
    unit: Optional[str] = None
    description: Optional[str] = None
    applies_to: Dict[str, Any] = {}
    is_active: bool = True
    is_default: bool = False
    metadata: Dict[str, Any] = {}


# 阈值创建请求
class ThresholdCreate(ThresholdBase):
    """创建阈值请求"""
    created_by: Optional[str] = None


# 阈值更新请求
class ThresholdUpdate(BaseModel):
    """更新阈值请求"""
    name: Optional[str] = None
    normal_range: Optional[Dict[str, Any]] = None
    warning_range: Optional[Dict[str, Any]] = None
    critical_range: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    applies_to: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None
    updated_by: Optional[str] = None


# 阈值响应模型
class ThresholdResponse(ThresholdBase, TimestampModel):
    """阈值响应模型"""
    id: str
    created_by: Optional[str] = None
    updated_by: Optional[str] = None

    class Config(PydanticConfig):
        pass


# 预警基础模型
class AlertBase(BaseModel):
    """预警基础模型"""
    health_data_id: str
    patient_id: str
    data_type: str
    vital_type: Optional[str] = None
    test_name: Optional[str] = None
    value: Union[float, Dict[str, float]]
    unit: Optional[str] = None
    threshold_id: Optional[str] = None
    alert_level: AlertLevel
    status: AlertStatus = AlertStatus.ACTIVE
    recorded_at: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = {}


# 预警创建请求
class AlertCreate(AlertBase):
    """创建预警请求"""
    pass


# 预警更新请求
class AlertUpdate(BaseModel):
    """更新预警请求"""
    status: Optional[AlertStatus] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_notes: Optional[str] = None


# 预警响应模型
class AlertResponse(AlertBase, TimestampModel):
    """预警响应模型"""
    id: str
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_notes: Optional[str] = None

    class Config(PydanticConfig):
        pass


# 血压阈值创建模型
class BloodPressureThresholdCreate(BaseModel):
    """血压阈值创建模型"""
    name: str
    normal_systolic: Dict[str, float]  # {"min": 90, "max": 120}
    normal_diastolic: Dict[str, float]  # {"min": 60, "max": 80}
    warning_systolic: Optional[Dict[str, float]] = None
    warning_diastolic: Optional[Dict[str, float]] = None
    critical_systolic: Optional[Dict[str, float]] = None
    critical_diastolic: Optional[Dict[str, float]] = None
    applies_to: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    created_by: Optional[str] = None
    is_default: bool = False


# 单一值阈值创建模型
class SingleValueThresholdCreate(BaseModel):
    """单一值阈值创建模型"""
    name: str
    vital_type: str  # heart_rate, blood_glucose等
    normal_range: Dict[str, float]  # {"min": 60, "max": 100}
    warning_range: Optional[Dict[str, float]] = None
    critical_range: Optional[Dict[str, float]] = None
    unit: Optional[str] = None
    applies_to: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    created_by: Optional[str] = None
    is_default: bool = False


# 预警统计模型
class AlertStatistics(BaseModel):
    """预警统计"""
    total: int = 0
    active: int = 0
    resolved: int = 0
    ignored: int = 0
    critical: int = 0
    warning: int = 0
    by_type: Dict[str, int] = {}
    by_patient: Dict[str, int] = {} 