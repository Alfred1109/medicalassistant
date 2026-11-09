"""REH01 康复方案域结构收敛 schema：方案版本、处方项、执行事件与四类干预字段位。

仅建立结构契约与字段位；所有临床语义（四类干预规则值、阈值、禁忌内容、
适用条件取值、医护审核口径）一律留空（None），显式标注"待定 D05"，
不编造任何临床数据。字段结构可建，规则值由 D05 决策后填充。
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class InterventionType(str, Enum):
    """四类干预：饮食 / 运动 / 用药 / 心理（REH01 结构枚举，非临床规则）。"""
    DIET = "diet"
    EXERCISE = "exercise"
    MEDICATION = "medication"
    PSYCHOLOGY = "psychology"


# ── 四类干预结构化字段位（值全部待定 D05）────────────────────────────────

class DietInterventionFields(BaseModel):
    """饮食干预结构化字段位。

    所有字段为结构占位，具体营养目标、膳食结构规则值待定 D05，一律不预填。
    """
    model_config = ConfigDict(extra="forbid")
    # 膳食结构引用（结构位；引用的权威膳食方案待定 D05）
    meal_structure_ref: Optional[str] = None
    # 能量目标（结构位；数值待定 D05）
    energy_target: Optional[Dict[str, Any]] = None
    # 营养素目标（结构位；数值与口径待定 D05）
    nutrient_targets: Optional[Dict[str, Any]] = None
    # 食物限制（结构位；禁忌内容待定 D05，绝不预填）
    food_restrictions: Optional[List[str]] = None


class MedicationInterventionFields(BaseModel):
    """用药干预结构化字段位。

    药品引用、剂量、监测要求等具体值待定 D05；本模型不表达任何用药建议。
    """
    model_config = ConfigDict(extra="forbid")
    # 药品引用（结构位；权威药品字典待定 D05）
    drug_ref: Optional[str] = None
    # 剂量（结构位；数值待定 D05）
    dosage: Optional[Dict[str, Any]] = None
    # 用药频次（结构位；口径待定 D05）
    frequency: Optional[str] = None
    # 给药途径（结构位；取值待定 D05）
    route: Optional[str] = None
    # 监测要求（结构位；指标与阈值待定 D05）
    monitoring: Optional[Dict[str, Any]] = None


class PsychologyInterventionFields(BaseModel):
    """心理干预结构化字段位。

    干预形式、量表引用与会话安排的具体值待定 D05；本模型不表达心理处方。
    """
    model_config = ConfigDict(extra="forbid")
    # 干预形式引用（结构位；权威形式清单待定 D05）
    modality_ref: Optional[str] = None
    # 会话安排（结构位；频次与时长口径待定 D05）
    session_plan: Optional[Dict[str, Any]] = None
    # 量表引用（结构位；量表版本以 113.44 正式版本为准，见核查文档 §5）
    instrument_refs: Optional[List[str]] = None


class PrescriptionSchedule(BaseModel):
    """处方项执行安排的结构化字段（结构位，具体取值由医护审核时填写）。"""
    model_config = ConfigDict(extra="forbid")
    days_per_week: Optional[int] = None
    sets: Optional[int] = None
    reps: Optional[int] = None
    # 兼容既有 add_exercises_to_plan 写入的 repetitions 命名
    repetitions: Optional[int] = None
    duration_minutes: Optional[int] = None
    frequency: Optional[str] = None
    time_of_day: Optional[str] = None


# ── 处方项（稳定 item_id）────────────────────────────────────────────────

class PrescriptionItemBase(BaseModel):
    """处方项：方案内容的最小可执行单元，拥有独立稳定 item_id。

    适用条件 / 禁忌 / 来源 / 医护审核要求仅保留字段位，内容待定 D05。
    """
    model_config = ConfigDict(extra="forbid")
    intervention_type: InterventionType = InterventionType.EXERCISE
    # 运动库引用（intervention_type=exercise 时指向 exercises 集合）
    exercise_id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    schedule: Optional[PrescriptionSchedule] = None
    order: Optional[int] = None
    notes: Optional[str] = None
    # 发布时快照字段位（快照内容在发布动作中填充，REH02 承接）
    snapshot: Optional[Dict[str, Any]] = None
    # 来源字段位（来源规则与引用格式待定 D05/CLIN01）
    source_ref: Optional[Dict[str, Any]] = None
    # 适用条件字段位（取值待定 D05，一律留空）
    applicability_conditions: Optional[List[str]] = None
    # 禁忌字段位（禁忌内容待定 D05，绝不预填）
    contraindications: Optional[List[str]] = None
    # 医护审核要求字段位（审核口径待定 REH02/D05）
    review_requirements: Optional[Dict[str, Any]] = None
    # 四类干预各自的结构化字段位（值待定 D05）
    diet_fields: Optional[DietInterventionFields] = None
    medication_fields: Optional[MedicationInterventionFields] = None
    psychology_fields: Optional[PsychologyInterventionFields] = None


class PrescriptionItemCreate(PrescriptionItemBase):
    """创建处方项入参；item_id 由服务端分配，客户端不可指定。"""
    pass


class PrescriptionItemEdit(PrescriptionItemBase):
    """审核页对处方项的可修改字段白名单（extra=forbid，_id 等身份字段被拒绝）。

    用于 GeneratedPlanEdits.exercises：替代原先的裸字典，阻止 `_id`、
    patient_id、status 等身份/状态字段经嵌套结构进入 `$set`。
    """
    pass


# ── 方案版本 ─────────────────────────────────────────────────────────────

class PlanVersionCreate(BaseModel):
    """创建方案版本入参；版本号由服务端递增分配。"""
    model_config = ConfigDict(extra="forbid")
    note: Optional[str] = None


# ── 每次执行事件（幂等）──────────────────────────────────────────────────

class ExecutionEventCreate(BaseModel):
    """记录一次训练执行事件；event_id 由客户端提供，重复提交幂等。

    事件粒度为"某次计划训练的执行"，与"训练处方项"分离（核查文档 §1
    进度语义行）；完成率/依从性统计口径待定（REH03），本模型只承载记录。
    """
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(..., min_length=1, description="幂等键，客户端生成，服务端按 (plan_id, event_id) 去重")
    performed_at: Optional[datetime] = None
    # 单次执行结果类别；枚举口径与统计语义待定 REH03，不做默认完成推断
    status: Optional[str] = None
    pain_level: Optional[int] = None
    difficulty_rating: Optional[int] = None
    notes: Optional[str] = None
