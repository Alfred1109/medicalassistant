"""
健康档案数据模型
定义患者健康档案、随访记录和健康数据
增强版本：支持档案版本控制和健康数据聚合
"""
from datetime import datetime
from bson import ObjectId
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field

class HealthRecord:
    """患者健康档案模型"""
    collection_name = "health_records"
    
    def __init__(
        self,
        patient_id: str,
        record_type: str = "general",  # general, diagnostic, treatment, etc.
        title: str = None,
        content: Dict[str, Any] = None,
        created_by: str = None,  # 记录创建者（医生、健康管理师等）ID
        organization_id: str = None,
        attachments: List[Dict[str, Any]] = None,
        tags: List[str] = None,
        visibility: str = "all",  # all, doctor_only, patient_only, medical_staff
        versions: List[Dict[str, Any]] = None,  # 版本历史
        current_version: int = 1,  # 当前版本号
        created_at: datetime = None,
        updated_at: datetime = None,
        _id: str = None,
        metadata: Dict[str, Any] = None
    ):
        self.patient_id = patient_id
        self.record_type = record_type
        self.title = title or f"{record_type.capitalize()} Record"
        self.content = content or {}
        self.created_by = created_by
        self.organization_id = organization_id
        self.attachments = attachments or []
        self.tags = tags or []
        self.visibility = visibility
        # 版本控制
        self.versions = versions or []
        self.current_version = current_version
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self._id = _id or str(ObjectId())
        self.metadata = metadata or {}
    
    @classmethod
    def from_mongo(cls, mongo_doc):
        """从MongoDB文档创建健康档案对象"""
        if not mongo_doc:
            return None
            
        record_data = mongo_doc.copy()
        record_data["_id"] = str(record_data["_id"])
        
        return cls(**record_data)
    
    def to_mongo(self):
        """将健康档案对象转换为MongoDB文档"""
        doc = self.__dict__.copy()
        if doc.get("_id") and isinstance(doc["_id"], str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc
    
    def to_dict(self):
        """将健康档案对象转换为字典，用于API响应"""
        return self.__dict__.copy()
    
    def add_attachment(self, file_name: str, file_type: str, file_url: str, description: str = None, file_size: int = None):
        """添加附件"""
        attachment = {
            "file_name": file_name,
            "file_type": file_type,
            "file_url": file_url,
            "file_size": file_size,
            "description": description,
            "uploaded_at": datetime.utcnow()
        }
        self.attachments.append(attachment)
        self.updated_at = datetime.utcnow()
    
    def update_content(self, content: Dict[str, Any], updated_by: str, change_description: str = None):
        """
        更新记录内容，并创建新版本
        保存前一个版本的内容到版本历史
        """
        # 保存当前版本到版本历史
        current_version_record = {
            "version_number": self.current_version,
            "content": self.content.copy(),
            "created_by": self.created_by if self.current_version == 1 else updated_by,
            "created_at": self.created_at if self.current_version == 1 else self.updated_at,
            "change_description": None if self.current_version == 1 else change_description
        }
        self.versions.append(current_version_record)
        
        # 更新内容
        self.content.update(content)
        self.current_version += 1
        self.updated_at = datetime.utcnow()
    
    def get_version(self, version_number: int) -> Optional[Dict[str, Any]]:
        """获取特定版本的内容"""
        if version_number == self.current_version:
            return {
                "version_number": self.current_version,
                "content": self.content,
                "created_by": self.created_by,
                "created_at": self.created_at,
                "change_description": None
            }
            
        for version in self.versions:
            if version["version_number"] == version_number:
                return version
                
        return None


class FollowUpRecord:
    """随访记录模型"""
    collection_name = "followup_records"
    
    def __init__(
        self,
        patient_id: str,
        created_by: str,  # 随访人员（医生、健康管理师等）ID
        follow_up_type: str = "general",  # general, phone, in_person, video, etc.
        scheduled_date: datetime = None,
        actual_date: datetime = None,
        status: str = "scheduled",  # scheduled, completed, cancelled, missed, rescheduled
        notes: str = None,
        questions: List[Dict[str, Any]] = None,
        answers: List[Dict[str, Any]] = None,
        attachments: List[Dict[str, Any]] = None,
        health_record_ids: List[str] = None,  # 关联的健康档案ID
        reminder_sent: bool = False,  # 是否已发送提醒
        reminder_settings: Dict[str, Any] = None,  # 提醒设置
        created_at: datetime = None,
        updated_at: datetime = None,
        _id: str = None,
        metadata: Dict[str, Any] = None
    ):
        self.patient_id = patient_id
        self.created_by = created_by
        self.follow_up_type = follow_up_type
        self.scheduled_date = scheduled_date
        self.actual_date = actual_date
        self.status = status
        self.notes = notes or ""
        self.questions = questions or []
        self.answers = answers or []
        self.attachments = attachments or []
        self.health_record_ids = health_record_ids or []
        self.reminder_sent = reminder_sent
        self.reminder_settings = reminder_settings or {
            "enabled": True,
            "days_before": 1,
            "notify_patient": True,
            "notify_doctor": True
        }
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self._id = _id or str(ObjectId())
        self.metadata = metadata or {}
    
    @classmethod
    def from_mongo(cls, mongo_doc):
        """从MongoDB文档创建随访记录对象"""
        if not mongo_doc:
            return None
            
        record_data = mongo_doc.copy()
        record_data["_id"] = str(record_data["_id"])
        
        return cls(**record_data)
    
    def to_mongo(self):
        """将随访记录对象转换为MongoDB文档"""
        doc = self.__dict__.copy()
        if doc.get("_id") and isinstance(doc["_id"], str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc
    
    def to_dict(self):
        """将随访记录对象转换为字典，用于API响应"""
        return self.__dict__.copy()
    
    def complete_followup(self, actual_date: datetime = None, notes: str = None, answers: List[Dict[str, Any]] = None, attachments: List[Dict[str, Any]] = None):
        """完成随访"""
        self.status = "completed"
        self.actual_date = actual_date or datetime.utcnow()
        if notes:
            self.notes = notes
        if answers:
            self.answers = answers
        if attachments:
            self.attachments.extend(attachments)
        self.updated_at = datetime.utcnow()
    
    def cancel_followup(self, reason: str = None, reschedule_date: datetime = None):
        """取消随访"""
        self.status = "cancelled"
        if reason:
            self.notes = f"已取消: {reason}"
        
        # 如果提供了重新安排日期，则创建新的随访
        if reschedule_date:
            self.notes += f"\n已重新安排到: {reschedule_date.strftime('%Y-%m-%d %H:%M')}"
            self.status = "rescheduled"
            
        self.updated_at = datetime.utcnow()
    
    def reschedule(self, new_date: datetime, reason: str = None):
        """重新安排随访时间"""
        self.scheduled_date = new_date
        self.status = "rescheduled"
        if reason:
            self.notes = f"{self.notes}\n重新安排原因: {reason}"
        self.updated_at = datetime.utcnow()
    
    def add_health_record(self, health_record_id: str):
        """关联健康档案"""
        if health_record_id not in self.health_record_ids:
            self.health_record_ids.append(health_record_id)
            self.updated_at = datetime.utcnow()


class HealthData:
    """健康数据模型，用于存储各类健康指标数据"""
    collection_name = "health_data"
    
    def __init__(
        self,
        patient_id: str,
        data_type: str,  # vital_sign, lab_result, activity, etc.
        data: Dict[str, Any],  # 具体数据，根据data_type有不同结构
        source: str = "manual",  # manual, device, imported
        device_id: str = None,  # 数据来源设备ID
        recorded_by: str = None,  # 记录人（医生、病人等）ID
        recorded_at: datetime = None,  # 记录时间
        created_at: datetime = None,
        updated_at: datetime = None,
        _id: str = None,
        metadata: Dict[str, Any] = None
    ):
        self.patient_id = patient_id
        self.data_type = data_type
        self.data = data
        self.source = source
        self.device_id = device_id
        self.recorded_by = recorded_by
        self.recorded_at = recorded_at or datetime.utcnow()
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self._id = _id or str(ObjectId())
        self.metadata = metadata or {}
    
    @classmethod
    def from_mongo(cls, mongo_doc):
        """从MongoDB文档创建健康数据对象"""
        if not mongo_doc:
            return None
            
        data = mongo_doc.copy()
        data["_id"] = str(data["_id"])
        
        return cls(**data)
    
    def to_mongo(self):
        """将健康数据对象转换为MongoDB文档"""
        doc = self.__dict__.copy()
        if doc.get("_id") and isinstance(doc["_id"], str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc
    
    def to_dict(self):
        """将健康数据对象转换为字典，用于API响应"""
        return self.__dict__.copy()
    
    @staticmethod
    def create_vital_sign(
        patient_id: str,
        vital_type: str,  # heart_rate, blood_pressure, temperature, etc.
        value: Union[float, str, Dict[str, float]],
        unit: str = None,
        measured_at: datetime = None,
        measured_by: str = None,
        device_id: str = None,
        notes: str = None
    ) -> 'HealthData':
        """创建生命体征记录"""
        data = {
            "type": vital_type,
            "value": value,
            "unit": unit,
            "notes": notes
        }
        
        return HealthData(
            patient_id=patient_id,
            data_type="vital_sign",
            data=data,
            source="device" if device_id else "manual",
            device_id=device_id,
            recorded_by=measured_by,
            recorded_at=measured_at or datetime.utcnow()
        )
    
    @staticmethod
    def create_lab_result(
        patient_id: str,
        test_name: str,
        result_value: Union[float, str, Dict[str, Any]],
        reference_range: str = None,
        unit: str = None,
        test_date: datetime = None,
        ordering_provider: str = None,
        performing_lab: str = None,
        interpretation: str = None,  # normal, abnormal, critical
        notes: str = None
    ) -> 'HealthData':
        """创建实验室检查结果记录"""
        data = {
            "test_name": test_name,
            "result_value": result_value,
            "reference_range": reference_range,
            "unit": unit,
            "interpretation": interpretation,
            "performing_lab": performing_lab,
            "notes": notes
        }
        
        return HealthData(
            patient_id=patient_id,
            data_type="lab_result",
            data=data,
            source="imported",
            recorded_by=ordering_provider,
            recorded_at=test_date or datetime.utcnow()
        )


class MedicalTimeline:
    """医疗时间线模型，为患者健康记录提供时间线视图"""
    collection_name = "medical_timelines"
    
    def __init__(
        self,
        patient_id: str,
        item_type: str,  # health_record, follow_up, medication, vital_sign, etc.
        title: str,
        description: str = None,
        occurred_at: datetime = None,
        created_by: str = None,
        related_ids: List[str] = None,  # 相关记录ID
        created_at: datetime = None,
        _id: str = None,
        metadata: Dict[str, Any] = None
    ):
        self.patient_id = patient_id
        self.item_type = item_type
        self.title = title
        self.description = description or ""
        self.occurred_at = occurred_at or datetime.utcnow()
        self.created_by = created_by
        self.related_ids = related_ids or []
        self.created_at = created_at or datetime.utcnow()
        self._id = _id or str(ObjectId())
        self.metadata = metadata or {}
    
    @classmethod
    def from_mongo(cls, mongo_doc):
        """从MongoDB文档创建时间线项目对象"""
        if not mongo_doc:
            return None
            
        item_data = mongo_doc.copy()
        item_data["_id"] = str(item_data["_id"])
        
        return cls(**item_data)
    
    def to_mongo(self):
        """将时间线项目对象转换为MongoDB文档"""
        doc = self.__dict__.copy()
        if doc.get("_id") and isinstance(doc["_id"], str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc
    
    def to_dict(self):
        """将时间线项目对象转换为字典，用于API响应"""
        return self.__dict__.copy()
    
    @staticmethod
    def from_health_record(health_record: HealthRecord) -> 'MedicalTimeline':
        """从健康档案创建时间线项目"""
        return MedicalTimeline(
            patient_id=health_record.patient_id,
            item_type="health_record",
            title=health_record.title,
            description=f"{health_record.record_type.capitalize()} 记录",
            occurred_at=health_record.created_at,
            created_by=health_record.created_by,
            related_ids=[health_record._id],
            metadata={"record_type": health_record.record_type}
        )
    
    @staticmethod
    def from_follow_up(follow_up: FollowUpRecord) -> 'MedicalTimeline':
        """从随访记录创建时间线项目"""
        occurred_at = follow_up.actual_date if follow_up.actual_date else follow_up.scheduled_date
        status_desc = {
            "scheduled": "已安排",
            "completed": "已完成",
            "cancelled": "已取消",
            "missed": "已错过",
            "rescheduled": "已重新安排"
        }
        
        return MedicalTimeline(
            patient_id=follow_up.patient_id,
            item_type="follow_up",
            title=f"{follow_up.follow_up_type.capitalize()} 随访",
            description=f"随访状态: {status_desc.get(follow_up.status, follow_up.status)}",
            occurred_at=occurred_at,
            created_by=follow_up.created_by,
            related_ids=[follow_up._id] + follow_up.health_record_ids,
            metadata={"status": follow_up.status, "type": follow_up.follow_up_type}
        )
    
    @staticmethod
    def from_health_data(health_data: HealthData) -> 'MedicalTimeline':
        """从健康数据创建时间线项目"""
        title_map = {
            "vital_sign": "生命体征",
            "lab_result": "实验室检查",
            "medication": "用药记录",
            "activity": "活动记录",
            "sleep": "睡眠记录",
            "diet": "饮食记录"
        }
        
        title = title_map.get(health_data.data_type, health_data.data_type.capitalize())
        
        description = ""
        if health_data.data_type == "vital_sign":
            vital_type = health_data.data.get("type", "")
            value = health_data.data.get("value", "")
            unit = health_data.data.get("unit", "")
            description = f"{vital_type}: {value} {unit}"
        elif health_data.data_type == "lab_result":
            test_name = health_data.data.get("test_name", "")
            result = health_data.data.get("result_value", "")
            unit = health_data.data.get("unit", "")
            description = f"{test_name}: {result} {unit}"
        
        return MedicalTimeline(
            patient_id=health_data.patient_id,
            item_type=f"health_data_{health_data.data_type}",
            title=title,
            description=description,
            occurred_at=health_data.recorded_at,
            created_by=health_data.recorded_by,
            related_ids=[health_data._id],
            metadata={"data_type": health_data.data_type, "source": health_data.source}
        )

# 健康指标模型
class HealthMetric(BaseModel):
    id: str = Field(default_factory=lambda: str(ObjectId()))
    name: str  # 指标名称，如心率、血压等
    value: str  # 当前值
    unit: str  # 单位，如次/分、mmHg等
    status: str = "normal"  # normal, good, warning, danger
    trend: str = "+0%"  # 趋势百分比，如+2%，-1%等
    timestamp: datetime = Field(default_factory=datetime.now)
    user_id: str  # 用户ID
    
    class Config:
        schema_extra = {
            "example": {
                "id": "60d21b4967d0d8992e610c85",
                "name": "心率",
                "value": "75",
                "unit": "次/分",
                "status": "normal",
                "trend": "+2%",
                "timestamp": "2023-08-15T14:30:00.000Z",
                "user_id": "60d21b4967d0d8992e610c83"
            }
        }

# 待办事项模型
class TodoItem(BaseModel):
    id: str = Field(default_factory=lambda: str(ObjectId()))
    title: str  # 待办事项标题
    description: str  # 描述
    due: str  # 到期时间描述，如"今天"，"12:30"等
    completed: bool = False  # 是否已完成
    important: bool = False  # 是否重要
    user_id: str  # 用户ID
    timestamp: datetime = Field(default_factory=datetime.now)
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "60d21b4967d0d8992e610c85",
                "title": "血压记录",
                "description": "请完成今日的血压测量记录", 
                "due": "今天", 
                "completed": False, 
                "important": True,
                "user_id": "60d21b4967d0d8992e610c83",
                "timestamp": "2023-08-15T14:30:00.000Z"
            }
        } 