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
        # T74：设备接入网关侧凭证（设备采集端 → 系统上报时使用；
        # 由 PUT /devices/{id}/gateway-credential 生成/轮换，硬件侧保存。
        # 厂商协议未到位前的过渡凭证机制，与用户账号体系无关。）
        device_key: str = None,
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
        self.device_key = device_key
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
        # T74：自动采集入库路径新增——质量事件标记（out_of_range:<metric> /
        # out_of_order / unregistered_metric / ...）与分析侧过滤可见；
        # 手工登记路径不写该字段（None）。
        quality_flags: List[str] = None,
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
        self.quality_flags = quality_flags
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

class DeviceCollectionSession:
    """设备采集会话模型（T74 自动采集接入）

    collection_name = "device_collection_sessions"

    会话 = 一次有边界的自动采集窗口：设备 → 网关上报 → 质量管道 →
    device_data。关联患者与（可选）康复方案执行项；会话期间设备以
    active_session_id 标注在线采集状态（真实性由心跳/上报维持，
    不凭会话存在虚构连接）。
    """

    collection_name = "device_collection_sessions"

    # 方案执行关联状态：
    # - linked：plan_id + exercise_id 均在 rehab_plans 中核实存在；
    # - registered：提供了 plan/exercise 但未能核实（登记待人工关联）；
    # - none：未提供。
    LINKAGE_LINKED = "linked"
    LINKAGE_REGISTERED = "registered"
    LINKAGE_NONE = "none"

    def __init__(
        self,
        device_id: str,  # 设备 Mongo 主键（str(_id)，与 device_data.device_id 口径一致）
        patient_id: str,  # 会话所属患者
        device_sn: str = None,  # 设备序列号（devices.device_id）
        status: str = "active",  # active / ended / cancelled
        plan_id: str = None,  # 关联康复方案（可选）
        exercise_id: str = None,  # 关联方案内运动项（可选）
        linkage_status: str = LINKAGE_NONE,  # 方案执行关联状态
        started_at: datetime = None,
        ended_at: datetime = None,
        summary: Dict[str, Any] = None,  # 会话摘要（读数计数/质量统计，结束时写入）
        notes: str = None,
        created_at: datetime = None,
        updated_at: datetime = None,
        _id: str = None,
        metadata: Dict[str, Any] = None,
    ):
        self.device_id = device_id
        self.patient_id = patient_id
        self.device_sn = device_sn
        self.status = status
        self.plan_id = plan_id
        self.exercise_id = exercise_id
        self.linkage_status = linkage_status
        self.started_at = started_at or datetime.utcnow()
        self.ended_at = ended_at
        self.summary = summary or {}
        self.notes = notes
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self._id = _id or str(ObjectId())

    @classmethod
    def from_mongo(cls, mongo_doc):
        if not mongo_doc:
            return None
        data = mongo_doc.copy()
        data["_id"] = str(data["_id"])
        return cls(**data)

    def to_mongo(self):
        doc = self.__dict__.copy()
        if doc.get("_id") and isinstance(doc["_id"], str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc

    def to_dict(self):
        return self.__dict__.copy()
