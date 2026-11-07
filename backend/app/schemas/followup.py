"""
随访（FU01 领域）schema 定义

S1 切片（docs/wp3-fu01-domain-design-draft-2026-11-07.md §五 S1、§2.4）：
以第二代骨架（原 schemas/health_record.py:465-555 的运行时生效定义）为唯一契约
拆出本文件，pydantic v2 风格改写；第一代同名定义已从 health_record.py 删除。
schemas/health_record.py 保留本模块符号的转发导入，兼容既有
`from app.schemas.health_record import FollowUpXxx` 引用（路由层 S2 收敛）。
"""
from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum

from .base import PyObjectId, TimestampModel


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
# S1 扩展（设计稿 §2.2 节点状态机）：pending_schedule / awaiting_fill / in_review /
# overdue / lost 仅为后续切片预留，本轮服务层不产生新状态流转；
# missed 与 overdue 的拆分口径待 FU03 确认后收敛。
class FollowUpStatus(str, Enum):
    PENDING_SCHEDULE = "pending_schedule"     # 创建未分配（预留）
    SCHEDULED = "scheduled"                   # 已计划
    AWAITING_FILL = "awaiting_fill"           # 待填写（预留）
    IN_REVIEW = "in_review"                   # 待医护审阅（预留）
    COMPLETED = "completed"                   # 已完成
    CANCELED = "canceled"                     # 已取消（拼写沿用现有 canceled）
    MISSED = "missed"                         # 已错过（FU03 口径确认前保留）
    OVERDUE = "overdue"                       # 超窗口未填（FU03 预留）
    LOST = "lost"                             # 失访认定（FU03 预留）
    RESCHEDULED = "rescheduled"               # 已重新安排


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
    """数据库中的随访记录模型（followup_records 集合文档形状）

    S1 起扩展数据正式落顶层：provider_id / template_id / reminder_before /
    completion_data / cancellation_data / next_follow_up_id 全部 Optional，
    存量文档缺省免回填（读取侧按「正式字段优先、metadata.* 回退」兼容，
    见 health_record_service._followup_from_mongo）。
    """
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    # 覆盖 FollowUpBase 必填声明：存量文档无顶层 provider_id / description
    # （存储字段为 notes），DB 模型须能直接校验存量文档
    provider_id: Optional[str] = None
    description: Optional[str] = None
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

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )
