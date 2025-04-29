"""
设备数据模型
定义设备和设备数据
"""
from datetime import datetime
from bson import ObjectId
from typing import Dict, List, Optional, Any

class Device:
    """设备模型"""
    collection_name = "devices"
    
    def __init__(
        self,
        device_id: str,  # 设备唯一ID/序列号
        device_type: str,  # 设备类型
        name: str,  # 设备名称
        manufacturer: str = None,  # 制造商
        model: str = None,  # 型号
        patient_id: str = None,  # 患者ID（如已绑定）
        status: str = "active",  # active, inactive, maintenance
        firmware_version: str = None,  # 固件版本
        connection_type: str = None,  # 连接类型（蓝牙、Wi-Fi等）
        last_connected: datetime = None,  # 最后连接时间
        battery_level: float = None,  # 电池电量
        location: Dict[str, Any] = None,  # 设备位置
        settings: Dict[str, Any] = None,  # 设备设置
        tags: List[str] = None,  # 标签
        created_at: datetime = None,
        updated_at: datetime = None,
        _id: str = None,
        metadata: Dict[str, Any] = None
    ):
        self.device_id = device_id
        self.device_type = device_type
        self.name = name
        self.manufacturer = manufacturer
        self.model = model
        self.patient_id = patient_id
        self.status = status
        self.firmware_version = firmware_version
        self.connection_type = connection_type
        self.last_connected = last_connected
        self.battery_level = battery_level
        self.location = location or {}
        self.settings = settings or {}
        self.tags = tags or []
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self._id = _id or str(ObjectId())
        self.metadata = metadata or {}
    
    @classmethod
    def from_mongo(cls, mongo_doc):
        """从MongoDB文档创建设备对象"""
        if not mongo_doc:
            return None
            
        device_data = mongo_doc.copy()
        device_data["_id"] = str(device_data["_id"])
        
        return cls(**device_data)
    
    def to_mongo(self):
        """将设备对象转换为MongoDB文档"""
        doc = self.__dict__.copy()
        if doc.get("_id") and isinstance(doc["_id"], str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc
    
    def to_dict(self):
        """将设备对象转换为字典，用于API响应"""
        return self.__dict__.copy()
    
    def bind_patient(self, patient_id: str):
        """绑定患者"""
        self.patient_id = patient_id
        self.updated_at = datetime.utcnow()
    
    def unbind_patient(self):
        """解绑患者"""
        self.patient_id = None
        self.updated_at = datetime.utcnow()
    
    def update_status(self, status: str):
        """更新设备状态"""
        self.status = status
        self.updated_at = datetime.utcnow()
    
    def update_battery(self, battery_level: float):
        """更新电池电量"""
        self.battery_level = battery_level
        self.updated_at = datetime.utcnow()
    
    def update_firmware(self, firmware_version: str):
        """更新固件版本"""
        self.firmware_version = firmware_version
        self.updated_at = datetime.utcnow()


class DeviceData:
    """设备数据模型"""
    collection_name = "device_data"
    
    def __init__(
        self,
        device_id: str,  # 设备ID
        patient_id: str,  # 患者ID
        data_type: str,  # 数据类型（心率、步数、体温等）
        value: Any,  # 数据值
        unit: str = None,  # 单位
        timestamp: datetime = None,  # 数据时间戳
        location: Dict[str, Any] = None,  # 数据采集位置
        data_quality: float = None,  # 数据质量/可信度（0-1）
        session_id: str = None,  # 会话ID（如适用）
        activity_type: str = None,  # 活动类型（如适用）
        created_at: datetime = None,
        _id: str = None,
        metadata: Dict[str, Any] = None
    ):
        self.device_id = device_id
        self.patient_id = patient_id
        self.data_type = data_type
        self.value = value
        self.unit = unit
        self.timestamp = timestamp or datetime.utcnow()
        self.location = location
        self.data_quality = data_quality
        self.session_id = session_id
        self.activity_type = activity_type
        self.created_at = created_at or datetime.utcnow()
        self._id = _id or str(ObjectId())
        self.metadata = metadata or {}
    
    @classmethod
    def from_mongo(cls, mongo_doc):
        """从MongoDB文档创建设备数据对象"""
        if not mongo_doc:
            return None
            
        data = mongo_doc.copy()
        data["_id"] = str(data["_id"])
        
        return cls(**data)
    
    def to_mongo(self):
        """将设备数据对象转换为MongoDB文档"""
        doc = self.__dict__.copy()
        if doc.get("_id") and isinstance(doc["_id"], str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc
    
    def to_dict(self):
        """将设备数据对象转换为字典，用于API响应"""
        return self.__dict__.copy()


class DeviceCalibration:
    """设备校准记录模型"""
    collection_name = "device_calibrations"
    
    def __init__(
        self,
        device_id: str,  # 设备ID
        calibration_type: str,  # 校准类型
        performed_by: str = None,  # 执行校准的人员ID
        calibration_date: datetime = None,  # 校准日期
        next_calibration_date: datetime = None,  # 下次校准日期
        results: Dict[str, Any] = None,  # 校准结果
        is_successful: bool = True,  # 校准是否成功
        notes: str = None,  # 备注
        created_at: datetime = None,
        _id: str = None
    ):
        self.device_id = device_id
        self.calibration_type = calibration_type
        self.performed_by = performed_by
        self.calibration_date = calibration_date or datetime.utcnow()
        self.next_calibration_date = next_calibration_date
        self.results = results or {}
        self.is_successful = is_successful
        self.notes = notes or ""
        self.created_at = created_at or datetime.utcnow()
        self._id = _id or str(ObjectId())
    
    @classmethod
    def from_mongo(cls, mongo_doc):
        """从MongoDB文档创建校准记录对象"""
        if not mongo_doc:
            return None
            
        data = mongo_doc.copy()
        data["_id"] = str(data["_id"])
        
        return cls(**data)
    
    def to_mongo(self):
        """将校准记录对象转换为MongoDB文档"""
        doc = self.__dict__.copy()
        if doc.get("_id") and isinstance(doc["_id"], str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc
    
    def to_dict(self):
        """将校准记录对象转换为字典，用于API响应"""
        return self.__dict__.copy() 