"""
健康数据阈值模型
用于定义健康数据的正常范围和异常阈值
"""
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
from bson import ObjectId

class HealthDataThreshold:
    """健康数据阈值模型，用于设置和管理各类健康指标的正常范围和预警阈值"""
    collection_name = "health_data_thresholds"
    
    def __init__(
        self,
        name: str,  # 阈值配置名称（如"高血压成人标准"）
        data_type: str,  # vital_sign, lab_result 等
        vital_type: Optional[str] = None,  # 适用于vital_sign，如blood_pressure, heart_rate等
        test_name: Optional[str] = None,  # 适用于lab_result，如blood_glucose, cholesterol等
        normal_range: Dict[str, Any] = None,  # 正常范围，如{"min": 60, "max": 100}
        warning_range: Dict[str, Any] = None,  # 预警范围
        critical_range: Dict[str, Any] = None,  # 严重异常范围
        unit: str = None,  # 单位
        description: str = None,  # 描述
        applies_to: Dict[str, Any] = None,  # 适用条件，如{"age": {"min": 18, "max": 65}, "gender": "male"}
        created_by: str = None,  # 创建人
        updated_by: str = None,  # 更新人
        created_at: datetime = None,
        updated_at: datetime = None,
        _id: str = None,
        is_active: bool = True,  # 是否启用
        is_default: bool = False,  # 是否为默认配置
        metadata: Dict[str, Any] = None
    ):
        self.name = name
        self.data_type = data_type
        self.vital_type = vital_type
        self.test_name = test_name
        self.normal_range = normal_range or {}
        self.warning_range = warning_range or {}
        self.critical_range = critical_range or {}
        self.unit = unit
        self.description = description
        self.applies_to = applies_to or {}
        self.created_by = created_by
        self.updated_by = updated_by
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self._id = _id or str(ObjectId())
        self.is_active = is_active
        self.is_default = is_default
        self.metadata = metadata or {}
    
    @classmethod
    def from_mongo(cls, mongo_doc):
        """从MongoDB文档创建阈值对象"""
        if not mongo_doc:
            return None
            
        data = mongo_doc.copy()
        data["_id"] = str(data["_id"])
        
        return cls(**data)
    
    def to_mongo(self):
        """将阈值对象转换为MongoDB文档"""
        doc = self.__dict__.copy()
        if doc.get("_id") and isinstance(doc["_id"], str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc
    
    def to_dict(self):
        """将阈值对象转换为字典，用于API响应"""
        return self.__dict__.copy()
    
    @staticmethod
    def create_blood_pressure_threshold(
        name: str,
        normal_systolic: Dict[str, float],  # {"min": 90, "max": 120}
        normal_diastolic: Dict[str, float],  # {"min": 60, "max": 80}
        warning_systolic: Dict[str, float] = None,  # {"min": 120, "max": 140}
        warning_diastolic: Dict[str, float] = None,  # {"min": 80, "max": 90}
        critical_systolic: Dict[str, float] = None,  # {"min": 140, "max": 1000}
        critical_diastolic: Dict[str, float] = None,  # {"min": 90, "max": 1000}
        applies_to: Dict[str, Any] = None,
        description: str = None,
        created_by: str = None,
        is_default: bool = False
    ) -> 'HealthDataThreshold':
        """创建血压阈值配置"""
        return HealthDataThreshold(
            name=name,
            data_type="vital_sign",
            vital_type="blood_pressure",
            normal_range={
                "systolic": normal_systolic,
                "diastolic": normal_diastolic
            },
            warning_range={
                "systolic": warning_systolic or {},
                "diastolic": warning_diastolic or {}
            },
            critical_range={
                "systolic": critical_systolic or {},
                "diastolic": critical_diastolic or {}
            },
            unit="mmHg",
            description=description,
            applies_to=applies_to or {},
            created_by=created_by,
            is_default=is_default
        )
    
    @staticmethod
    def create_heart_rate_threshold(
        name: str,
        normal_range: Dict[str, float],  # {"min": 60, "max": 100}
        warning_range: Dict[str, float] = None,  # {"min": 40, "max": 120}
        critical_range: Dict[str, float] = None,  # {"min": 0, "max": 40}, {"min": 120, "max": 300}
        applies_to: Dict[str, Any] = None,
        description: str = None,
        created_by: str = None,
        is_default: bool = False
    ) -> 'HealthDataThreshold':
        """创建心率阈值配置"""
        return HealthDataThreshold(
            name=name,
            data_type="vital_sign",
            vital_type="heart_rate",
            normal_range=normal_range,
            warning_range=warning_range or {},
            critical_range=critical_range or {},
            unit="bpm",
            description=description,
            applies_to=applies_to or {},
            created_by=created_by,
            is_default=is_default
        )
    
    @staticmethod
    def create_blood_glucose_threshold(
        name: str,
        normal_range: Dict[str, float],  # {"min": 3.9, "max": 6.1}
        warning_range: Dict[str, float] = None,  # {"min": 3.0, "max": 7.0}
        critical_range: Dict[str, float] = None,  # {"min": 0, "max": 3.0}, {"min": 7.0, "max": 100}
        timing: str = "fasting",  # fasting, after_meal, random
        applies_to: Dict[str, Any] = None,
        description: str = None,
        created_by: str = None,
        is_default: bool = False
    ) -> 'HealthDataThreshold':
        """创建血糖阈值配置"""
        return HealthDataThreshold(
            name=name,
            data_type="vital_sign",
            vital_type="blood_glucose",
            normal_range=normal_range,
            warning_range=warning_range or {},
            critical_range=critical_range or {},
            unit="mmol/L",
            description=description,
            applies_to=applies_to or {"timing": timing},
            created_by=created_by,
            is_default=is_default
        )
    
    @staticmethod
    def create_body_temperature_threshold(
        name: str,
        normal_range: Dict[str, float],  # {"min": 36.1, "max": 37.2}
        warning_range: Dict[str, float] = None,  # {"min": 35.0, "max": 38.0}
        critical_range: Dict[str, float] = None,  # {"min": 0, "max": 35.0}, {"min": 38.0, "max": 45}
        applies_to: Dict[str, Any] = None,
        description: str = None,
        created_by: str = None,
        is_default: bool = False
    ) -> 'HealthDataThreshold':
        """创建体温阈值配置"""
        return HealthDataThreshold(
            name=name,
            data_type="vital_sign",
            vital_type="body_temperature",
            normal_range=normal_range,
            warning_range=warning_range or {},
            critical_range=critical_range or {},
            unit="°C",
            description=description,
            applies_to=applies_to or {},
            created_by=created_by,
            is_default=is_default
        )
    
    @staticmethod
    def create_respiratory_rate_threshold(
        name: str,
        normal_range: Dict[str, float],  # {"min": 12, "max": 20}
        warning_range: Dict[str, float] = None,  # {"min": 8, "max": 25}
        critical_range: Dict[str, float] = None,  # {"min": 0, "max": 8}, {"min": 25, "max": 100}
        applies_to: Dict[str, Any] = None,
        description: str = None,
        created_by: str = None,
        is_default: bool = False
    ) -> 'HealthDataThreshold':
        """创建呼吸频率阈值配置"""
        return HealthDataThreshold(
            name=name,
            data_type="vital_sign",
            vital_type="respiratory_rate",
            normal_range=normal_range,
            warning_range=warning_range or {},
            critical_range=critical_range or {},
            unit="次/分",
            description=description,
            applies_to=applies_to or {},
            created_by=created_by,
            is_default=is_default
        )
    
    @staticmethod
    def create_oxygen_saturation_threshold(
        name: str,
        normal_range: Dict[str, float],  # {"min": 95, "max": 100}
        warning_range: Dict[str, float] = None,  # {"min": 90, "max": 95}
        critical_range: Dict[str, float] = None,  # {"min": 0, "max": 90}
        applies_to: Dict[str, Any] = None,
        description: str = None,
        created_by: str = None,
        is_default: bool = False
    ) -> 'HealthDataThreshold':
        """创建血氧饱和度阈值配置"""
        return HealthDataThreshold(
            name=name,
            data_type="vital_sign",
            vital_type="oxygen_saturation",
            normal_range=normal_range,
            warning_range=warning_range or {},
            critical_range=critical_range or {},
            unit="%",
            description=description,
            applies_to=applies_to or {},
            created_by=created_by,
            is_default=is_default
        )
    
    def check_value(self, value: Union[float, Dict[str, float]]) -> Dict[str, Any]:
        """
        检查值是否在阈值范围内
        
        Args:
            value: 要检查的值，可以是单个浮点数或具有多个组件的字典（如血压）
            
        Returns:
            Dict: 包含状态和消息的字典，如{"status": "normal", "message": "血压正常"}
        """
        # 对于血压等有多个组件的指标
        if isinstance(value, dict) and self.vital_type == "blood_pressure":
            systolic = value.get("systolic")
            diastolic = value.get("diastolic")
            
            if systolic is None or diastolic is None:
                return {"status": "unknown", "message": "血压数据不完整"}
            
            # 检查收缩压
            systolic_status = self._check_single_value(
                systolic, 
                self.normal_range.get("systolic", {}), 
                self.warning_range.get("systolic", {}), 
                self.critical_range.get("systolic", {})
            )
            
            # 检查舒张压
            diastolic_status = self._check_single_value(
                diastolic, 
                self.normal_range.get("diastolic", {}), 
                self.warning_range.get("diastolic", {}), 
                self.critical_range.get("diastolic", {})
            )
            
            # 取较严重的状态
            if systolic_status["status"] == "critical" or diastolic_status["status"] == "critical":
                status = "critical"
                message = f"血压严重异常: 收缩压{systolic}/{self.unit}, 舒张压{diastolic}/{self.unit}"
            elif systolic_status["status"] == "warning" or diastolic_status["status"] == "warning":
                status = "warning"
                message = f"血压警告: 收缩压{systolic}/{self.unit}, 舒张压{diastolic}/{self.unit}"
            else:
                status = "normal"
                message = f"血压正常: 收缩压{systolic}/{self.unit}, 舒张压{diastolic}/{self.unit}"
            
            return {
                "status": status,
                "message": message,
                "components": {
                    "systolic": systolic_status,
                    "diastolic": diastolic_status
                }
            }
        
        # 对于单值指标
        else:
            numeric_value = float(value) if isinstance(value, (int, str)) else value
            result = self._check_single_value(
                numeric_value, 
                self.normal_range, 
                self.warning_range, 
                self.critical_range
            )
            
            # 添加单位到消息中
            type_name = self.vital_type or self.test_name or self.data_type
            if result["status"] == "critical":
                result["message"] = f"{type_name}严重异常: {numeric_value}{self.unit or ''}"
            elif result["status"] == "warning":
                result["message"] = f"{type_name}警告: {numeric_value}{self.unit or ''}"
            else:
                result["message"] = f"{type_name}正常: {numeric_value}{self.unit or ''}"
            
            return result
    
    def _check_single_value(self, value: float, normal: Dict[str, float], warning: Dict[str, float], critical: Dict[str, float]) -> Dict[str, Any]:
        """检查单个数值是否在范围内"""
        # 检查是否在危险范围内
        if critical:
            crit_min = critical.get("min")
            crit_max = critical.get("max")
            if (crit_min is not None and value < crit_min) or (crit_max is not None and value > crit_max):
                return {"status": "critical", "value": value}
        
        # 检查是否在警告范围内
        if warning:
            warn_min = warning.get("min")
            warn_max = warning.get("max")
            if (warn_min is not None and value < warn_min) or (warn_max is not None and value > warn_max):
                return {"status": "warning", "value": value}
        
        # 检查是否在正常范围内
        if normal:
            norm_min = normal.get("min")
            norm_max = normal.get("max")
            if (norm_min is not None and value >= norm_min) and (norm_max is not None and value <= norm_max):
                return {"status": "normal", "value": value}
            else:
                # 如果不在正常范围但也不在警告或危险范围，则为警告
                return {"status": "warning", "value": value}
        
        # 如果没有定义任何范围
        return {"status": "unknown", "value": value}


class HealthDataAlert:
    """健康数据预警模型，记录超出阈值的健康数据"""
    collection_name = "health_data_alerts"
    
    def __init__(
        self,
        health_data_id: str,  # 关联的健康数据ID
        patient_id: str,  # 患者ID
        data_type: str,  # 数据类型
        value: Union[float, Dict[str, float]],  # 数据值
        vital_type: Optional[str] = None,  # 生命体征类型
        test_name: Optional[str] = None,  # 实验室检查名称
        unit: Optional[str] = None,  # 单位
        threshold_id: Optional[str] = None,  # 阈值配置ID
        alert_level: str = "warning",  # 预警级别：warning, critical
        status: str = "active",  # 状态：active, resolved, ignored
        recorded_at: datetime = None,  # 数据记录时间
        created_at: datetime = None,
        updated_at: datetime = None,
        resolved_at: Optional[datetime] = None,  # 解决时间
        resolved_by: Optional[str] = None,  # 解决人
        resolution_notes: Optional[str] = None,  # 解决备注
        _id: str = None,
        metadata: Dict[str, Any] = None
    ):
        self.health_data_id = health_data_id
        self.patient_id = patient_id
        self.data_type = data_type
        self.vital_type = vital_type
        self.test_name = test_name
        self.value = value
        self.unit = unit
        self.threshold_id = threshold_id
        self.alert_level = alert_level
        self.status = status
        self.recorded_at = recorded_at or datetime.utcnow()
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self.resolved_at = resolved_at
        self.resolved_by = resolved_by
        self.resolution_notes = resolution_notes
        self._id = _id or str(ObjectId())
        self.metadata = metadata or {}
    
    @classmethod
    def from_mongo(cls, mongo_doc):
        """从MongoDB文档创建预警对象"""
        if not mongo_doc:
            return None
            
        data = mongo_doc.copy()
        data["_id"] = str(data["_id"])
        
        return cls(**data)
    
    def to_mongo(self):
        """将预警对象转换为MongoDB文档"""
        doc = self.__dict__.copy()
        if doc.get("_id") and isinstance(doc["_id"], str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc
    
    def to_dict(self):
        """将预警对象转换为字典，用于API响应"""
        return self.__dict__.copy()
    
    @staticmethod
    def create_from_health_data(
        health_data_id: str,
        patient_id: str,
        data_type: str,
        value: Union[float, Dict[str, float]],
        check_result: Dict[str, Any],
        vital_type: Optional[str] = None,
        unit: Optional[str] = None,
        threshold_id: Optional[str] = None,
        recorded_at: Optional[datetime] = None
    ) -> Optional['HealthDataAlert']:
        """根据健康数据和检查结果创建预警"""
        if check_result["status"] not in ["warning", "critical"]:
            return None
            
        return HealthDataAlert(
            health_data_id=health_data_id,
            patient_id=patient_id,
            data_type=data_type,
            value=value,
            vital_type=vital_type,
            unit=unit,
            threshold_id=threshold_id,
            alert_level=check_result["status"],
            recorded_at=recorded_at,
            metadata={"message": check_result.get("message")}
        ) 