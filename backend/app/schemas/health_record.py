"""
健康档案相关的schema定义
包括健康档案、随访记录、健康数据等
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum

from .base import TimestampModel, PyObjectId


# 记录类型枚举
class RecordType(str, Enum):
    MEDICAL_RECORD = "medical_record"          # 门诊病历
    ADMISSION_RECORD = "admission_record"      # 入院记录
    DISCHARGE_SUMMARY = "discharge_summary"    # 出院小结
    SURGERY_RECORD = "surgery_record"          # 手术记录
    EXAMINATION_REPORT = "examination_report"  # 检查报告
    PROGRESS_NOTE = "progress_note"            # 病程记录
    CONSULTATION = "consultation"              # 会诊意见
    PRESCRIPTION = "prescription"              # 处方
    NURSING_RECORD = "nursing_record"          # 护理记录
    OTHER = "other"                           # 其他


# 随访类型枚举
class FollowUpType(str, Enum):
    PHONE = "phone"                           # 电话随访
    ONLINE = "online"                         # 线上随访
    ONSITE = "onsite"                         # 门诊随访
    HOME_VISIT = "home_visit"                 # 家庭访视
    REMOTE_MONITORING = "remote_monitoring"   # 远程监测
    GROUP = "group"                           # 小组随访
    OTHER = "other"                           # 其他


# 随访状态枚举
class FollowUpStatus(str, Enum):
    SCHEDULED = "scheduled"                   # 已计划
    COMPLETED = "completed"                   # 已完成
    CANCELED = "canceled"                     # 已取消
    MISSED = "missed"                         # 已错过
    RESCHEDULED = "rescheduled"               # 已重新安排


# 健康档案可见性枚举
class RecordVisibility(str, Enum):
    ALL = "all"
    DOCTOR_ONLY = "doctor_only"
    PATIENT_ONLY = "patient_only"
    MEDICAL_STAFF = "medical_staff"


# ------------ 基础模型 ------------

# 附件模型
class Attachment(BaseModel):
    file_name: str
    file_type: str
    file_url: str
    file_size: Optional[int] = None
    description: Optional[str] = None
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


# 生命体征模型
class VitalSign(BaseModel):
    type: str  # heart_rate, blood_pressure, temperature, etc.
    value: Union[float, str, Dict[str, float]]
    unit: Optional[str] = None
    measured_at: datetime = Field(default_factory=datetime.utcnow)
    measured_by: Optional[str] = None
    device_id: Optional[str] = None
    notes: Optional[str] = None


# 用药记录模型
class Medication(BaseModel):
    name: str
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    route: Optional[str] = None  # oral, injection, etc.
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    prescribed_by: Optional[str] = None
    purpose: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool = True


# 实验室检查结果模型
class LabResult(BaseModel):
    test_name: str
    result_value: Union[float, str, Dict[str, Any]]
    reference_range: Optional[str] = None
    unit: Optional[str] = None
    test_date: datetime = Field(default_factory=datetime.utcnow)
    ordering_provider: Optional[str] = None
    performing_lab: Optional[str] = None
    interpretation: Optional[str] = None  # normal, abnormal, critical
    notes: Optional[str] = None


# 诊断信息模型
class Diagnosis(BaseModel):
    condition: str
    icd_code: Optional[str] = None
    diagnosed_date: Optional[datetime] = None
    diagnosed_by: Optional[str] = None
    status: str = "active"  # active, resolved, recurrence
    notes: Optional[str] = None
    severity: Optional[str] = None
    body_site: Optional[str] = None


# 问答模型
class QuestionAnswer(BaseModel):
    question_id: Optional[str] = None
    question: str
    answer: Optional[str] = None
    answer_type: str = "text"  # text, number, option, boolean
    options: Optional[List[str]] = None
    required: bool = False
    answered_at: Optional[datetime] = None


# 患者病史模型
class MedicalHistory(BaseModel):
    past_medical_history: Optional[List[Dict[str, Any]]] = None
    family_history: Optional[List[Dict[str, Any]]] = None
    social_history: Optional[Dict[str, Any]] = None
    surgical_history: Optional[List[Dict[str, Any]]] = None
    allergies: Optional[List[Dict[str, Any]]] = None
    immunizations: Optional[List[Dict[str, Any]]] = None
    current_medications: Optional[List[Medication]] = None


# 健康档案版本模型
class RecordVersion(BaseModel):
    version_number: int
    content: Dict[str, Any]
    created_by: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    change_description: Optional[str] = None


# ------------ 请求响应模型 ------------

# 健康档案创建请求模型
class HealthRecordCreate(BaseModel):
    patient_id: str
    record_type: RecordType
    title: Optional[str] = None
    content: Dict[str, Any]
    created_by: str
    organization_id: Optional[str] = None
    attachments: Optional[List[Attachment]] = None
    tags: Optional[List[str]] = None
    visibility: RecordVisibility = RecordVisibility.ALL
    metadata: Optional[Dict[str, Any]] = None

    @validator('title', always=True)
    def set_default_title(cls, v, values):
        if not v and 'record_type' in values:
            return f"{values['record_type'].capitalize()} Record"
        return v


# 健康档案更新请求模型
class HealthRecordUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[Dict[str, Any]] = None
    attachments: Optional[List[Attachment]] = None
    tags: Optional[List[str]] = None
    visibility: Optional[RecordVisibility] = None
    metadata: Optional[Dict[str, Any]] = None


# 健康档案响应模型
class HealthRecordResponse(BaseModel):
    id: str
    patient_id: str
    record_type: str
    title: str
    content: Dict[str, Any]
    created_by: str
    organization_id: Optional[str] = None
    attachments: List[Attachment] = []
    tags: List[str] = []
    visibility: str
    created_at: datetime
    updated_at: datetime
    versions: Optional[List[RecordVersion]] = None
    metadata: Dict[str, Any] = {}

    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }


# 随访记录创建请求模型
class FollowUpRecordCreate(BaseModel):
    patient_id: str
    created_by: str
    follow_up_type: FollowUpType
    scheduled_date: datetime
    notes: Optional[str] = None
    questions: Optional[List[QuestionAnswer]] = None
    health_record_ids: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


# 随访记录更新请求模型
class FollowUpRecordUpdate(BaseModel):
    follow_up_type: Optional[FollowUpType] = None
    scheduled_date: Optional[datetime] = None
    actual_date: Optional[datetime] = None
    status: Optional[FollowUpStatus] = None
    notes: Optional[str] = None
    questions: Optional[List[QuestionAnswer]] = None
    answers: Optional[List[QuestionAnswer]] = None
    attachments: Optional[List[Attachment]] = None
    health_record_ids: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


# 随访记录响应模型
class FollowUpRecordResponse(BaseModel):
    id: str
    patient_id: str
    created_by: str
    follow_up_type: str
    scheduled_date: datetime
    actual_date: Optional[datetime] = None
    status: str
    notes: str = ""
    questions: List[QuestionAnswer] = []
    answers: List[QuestionAnswer] = []
    attachments: List[Attachment] = []
    health_record_ids: List[str] = []
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = {}

    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }


# 完成随访请求模型
class CompleteFollowUpRequest(BaseModel):
    actual_date: Optional[datetime] = None
    notes: Optional[str] = None
    answers: List[QuestionAnswer]
    attachments: Optional[List[Attachment]] = None


# 取消随访请求模型
class CancelFollowUpRequest(BaseModel):
    reason: str
    reschedule_date: Optional[datetime] = None


# 重新安排随访请求模型
class RescheduleFollowUpRequest(BaseModel):
    new_date: datetime
    reason: Optional[str] = None


# 健康数据创建请求模型
class HealthDataCreate(BaseModel):
    patient_id: str
    data_type: str  # vital_sign, lab_result, etc.
    data: Dict[str, Any]
    source: Optional[str] = None  # device, manual, imported
    device_id: Optional[str] = None
    recorded_by: Optional[str] = None
    recorded_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


# 健康数据响应模型
class HealthDataResponse(BaseModel):
    id: str
    patient_id: str
    data_type: str
    data: Dict[str, Any]
    source: Optional[str] = None
    device_id: Optional[str] = None
    recorded_by: Optional[str] = None
    recorded_at: datetime
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = {}

    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }


# 健康档案统计响应模型
class HealthRecordStats(BaseModel):
    total_records: int
    record_types: Dict[str, int]
    recent_updates: List[datetime]
    upcoming_followups: Optional[List[Dict[str, Any]]] = None
    pending_actions: Optional[List[Dict[str, Any]]] = None

    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }


# 健康时间线项目模型
class HealthTimelineItem(BaseModel):
    id: str
    patient_id: str
    item_type: str  # health_record, follow_up, medication, vital_sign, etc.
    title: str
    description: Optional[str] = None
    occurred_at: datetime
    created_by: Optional[str] = None
    related_ids: Optional[List[str]] = None
    metadata: Dict[str, Any] = {}

    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }


# 健康档案相关模型定义
class HealthRecordAttachment(BaseModel):
    """健康档案附件"""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    filename: str
    file_type: str
    file_size: int
    file_url: str
    upload_time: datetime = Field(default_factory=datetime.now)
    uploaded_by: str


class HealthRecordVersion(BaseModel):
    """健康档案版本"""
    version_number: int
    content: str
    updated_at: datetime = Field(default_factory=datetime.now)
    updated_by: str
    change_description: Optional[str] = None


class RelatedItem(BaseModel):
    """关联项目"""
    item_id: str
    item_type: str
    title: str
    relation_type: str = "related"  # 关联类型：related(相关)、referenced(引用)、parent(父项)、child(子项)


class HealthRecordBase(BaseModel):
    """健康档案基础模型"""
    patient_id: str
    record_type: str = Field(..., description="健康档案类型")
    title: str
    content: str
    created_by: str
    tags: List[str] = []
    metadata: Dict[str, Any] = {}


class HealthRecordCreate(HealthRecordBase):
    """创建健康档案请求"""
    attachments: List[HealthRecordAttachment] = []
    related_items: List[RelatedItem] = []
    related_follow_ups: List[str] = []


class HealthRecordUpdate(BaseModel):
    """更新健康档案请求"""
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[List[str]] = None
    attachments: Optional[List[HealthRecordAttachment]] = None
    metadata: Optional[Dict[str, Any]] = None
    record_type: Optional[str] = None
    related_items: Optional[List[RelatedItem]] = None
    related_follow_ups: Optional[List[str]] = None
    change_description: Optional[str] = None


class HealthRecordDB(HealthRecordBase, TimestampModel):
    """数据库中的健康档案模型"""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    attachments: List[HealthRecordAttachment] = []
    versions: List[HealthRecordVersion] = []
    related_items: List[RelatedItem] = []
    related_follow_ups: List[str] = []
    updated_by: Optional[str] = None
    deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None


class HealthRecordResponse(HealthRecordBase, TimestampModel):
    """健康档案响应模型"""
    id: str
    attachments: List[HealthRecordAttachment] = []
    current_version: int
    related_items: List[RelatedItem] = []
    related_follow_ups: List[str] = []
    updated_by: Optional[str] = None

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }


class HealthRecordStats(BaseModel):
    """健康档案统计信息"""
    total_records: int
    record_type_counts: Dict[str, int]
    latest_record: Optional[HealthRecordResponse] = None
    upcoming_followups: int
    recent_activity: List[Dict[str, Any]]
    completion_percentage: float
    total_attachments: int


# 随访记录相关模型定义
class FollowUpQuestion(BaseModel):
    """随访问题"""
    question_id: str
    question_text: str
    question_type: str  # text, number, choice, multiple_choice, scale
    options: Optional[List[Dict[str, str]]] = None
    required: bool = False
    order: int


class FollowUpAnswer(BaseModel):
    """随访回答"""
    question_id: str
    answer_value: Any
    answer_text: Optional[str] = None
    answered_at: datetime = Field(default_factory=datetime.now)


class FollowUpTemplate(BaseModel):
    """随访模板"""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str
    description: Optional[str] = None
    follow_up_type: str
    questions: List[FollowUpQuestion] = []
    created_by: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    active: bool = True


class FollowUpBase(BaseModel):
    """随访记录基础模型"""
    patient_id: str
    follow_up_type: str
    scheduled_date: datetime
    provider_id: str
    description: str
    questions: List[FollowUpQuestion] = []
    related_records: List[str] = []
    metadata: Dict[str, Any] = {}


class FollowUpRecordCreate(FollowUpBase):
    """创建随访记录请求"""
    template_id: Optional[str] = None
    created_by: Optional[str] = None
    reminder_before: Optional[int] = None  # 提前多少分钟提醒


class FollowUpRecordUpdate(BaseModel):
    """更新随访记录请求"""
    follow_up_type: Optional[str] = None
    scheduled_date: Optional[datetime] = None
    provider_id: Optional[str] = None
    description: Optional[str] = None
    questions: Optional[List[FollowUpQuestion]] = None
    related_records: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    status: Optional[FollowUpStatus] = None
    reminder_before: Optional[int] = None


class CompleteFollowUpRequest(BaseModel):
    """完成随访请求"""
    actual_date: datetime = Field(default_factory=datetime.now)
    answers: List[FollowUpAnswer] = []
    notes: Optional[str] = None
    follow_up_result: str = "completed"
    next_follow_up_date: Optional[datetime] = None


class CancelFollowUpRequest(BaseModel):
    """取消随访请求"""
    cancel_reason: str
    canceled_by: Optional[str] = None
    reschedule_date: Optional[datetime] = None


class RescheduleFollowUpRequest(BaseModel):
    """重新安排随访请求"""
    new_date: datetime
    reason: str
    provider_id: Optional[str] = None


class FollowUpRecordDB(FollowUpBase, TimestampModel):
    """数据库中的随访记录模型"""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    created_by: str
    status: FollowUpStatus = FollowUpStatus.SCHEDULED
    actual_date: Optional[datetime] = None
    answers: List[FollowUpAnswer] = []
    notes: Optional[str] = None
    follow_up_result: Optional[str] = None
    next_follow_up_id: Optional[str] = None
    template_id: Optional[str] = None
    reminder_before: Optional[int] = None
    completion_data: Optional[Dict[str, Any]] = None
    cancellation_data: Optional[Dict[str, Any]] = None
    deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None


class FollowUpRecordResponse(FollowUpBase, TimestampModel):
    """随访记录响应模型"""
    id: str
    created_by: str
    status: FollowUpStatus
    actual_date: Optional[datetime] = None
    answers: List[FollowUpAnswer] = []
    notes: Optional[str] = None
    follow_up_result: Optional[str] = None
    next_follow_up_id: Optional[str] = None
    template_id: Optional[str] = None
    reminder_before: Optional[int] = None
    completion_data: Optional[Dict[str, Any]] = None
    cancellation_data: Optional[Dict[str, Any]] = None

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }


# 健康数据相关模型定义
class HealthDataBase(BaseModel):
    """健康数据基础模型"""
    patient_id: str
    data_type: str
    data_content: Dict[str, Any]
    recorded_at: datetime = Field(default_factory=datetime.now)
    recorded_by: Optional[str] = None
    source: Optional[str] = None  # 数据来源：manual(手动录入)、device(设备)、app(应用程序)、integration(外部系统)


class HealthDataCreate(HealthDataBase):
    """创建健康数据请求"""
    pass


class HealthDataDB(HealthDataBase, TimestampModel):
    """数据库中的健康数据模型"""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    metadata: Dict[str, Any] = {}
    deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None


class HealthDataResponse(HealthDataBase, TimestampModel):
    """健康数据响应模型"""
    id: str
    metadata: Dict[str, Any] = {}

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }


class VitalSignData(BaseModel):
    """生命体征数据内容"""
    vital_type: str  # 生命体征类型：blood_pressure, heart_rate, body_temperature, respiratory_rate, blood_oxygen, weight
    value: float  # 测量值
    unit: Optional[str] = None  # 单位
    measured_at: datetime = Field(default_factory=datetime.now)  # 测量时间
    measured_by: Optional[str] = None  # 测量人
    device_id: Optional[str] = None  # 设备ID
    notes: Optional[str] = None  # 备注


class LabResultData(BaseModel):
    """实验室检查结果数据内容"""
    test_name: str  # 检测名称
    result_value: str  # 结果值
    reference_range: Optional[str] = None  # 参考范围
    unit: Optional[str] = None  # 单位
    test_date: datetime = Field(default_factory=datetime.now)  # 检测日期
    ordering_provider: Optional[str] = None  # 开单医生
    performing_lab: Optional[str] = None  # 执行实验室
    interpretation: Optional[str] = None  # 结果解释：normal, abnormal, critical
    notes: Optional[str] = None  # 备注


# 时间线相关模型定义
class TimelineItemType(str, Enum):
    """时间线项目类型"""
    HEALTH_RECORD = "health_record"  # 健康档案
    FOLLOW_UP = "follow_up"  # 随访记录
    VITAL_SIGN = "vital_sign"  # 生命体征
    LAB_RESULT = "lab_result"  # 实验室检查结果
    MEDICATION = "medication"  # 用药记录
    REHABILITATION = "rehabilitation"  # 康复计划
    EXERCISE = "exercise"  # 康复练习


class HealthTimelineItem(BaseModel):
    """健康时间线项目"""
    id: str
    patient_id: str
    item_type: TimelineItemType
    title: str
    description: Optional[str] = None
    timestamp: datetime
    data: Dict[str, Any] = {}
    icon: Optional[str] = None
    color: Optional[str] = None
    importance: int = 0  # 重要性：0(普通)、1(重要)、2(非常重要)

    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        } 