from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class ExerciseBase(BaseModel):
    name: str
    description: str
    body_part: str
    difficulty: str = Field(..., description="Easy, Medium, Hard")
    duration_minutes: int
    repetitions: Optional[int] = None
    sets: Optional[int] = None
    instructions: List[str]
    contraindications: Optional[List[str]] = []
    benefits: Optional[List[str]] = []
    video_url: Optional[str] = None
    image_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}
    
class ExerciseCreate(ExerciseBase):
    pass
    
class ExerciseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    body_part: Optional[str] = None
    difficulty: Optional[str] = None
    duration_minutes: Optional[int] = None
    repetitions: Optional[int] = None
    sets: Optional[int] = None
    instructions: Optional[List[str]] = None
    contraindications: Optional[List[str]] = None
    benefits: Optional[List[str]] = None
    video_url: Optional[str] = None
    image_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
class ExerciseResponse(ExerciseBase):
    id: str = Field(..., alias="_id")
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        
class RehabPlanBase(BaseModel):
    name: str
    description: str
    patient_id: str
    practitioner_id: Optional[str] = None
    start_date: datetime
    end_date: Optional[datetime] = None
    condition: Optional[str] = None
    goal: str
    frequency: Optional[str] = None
    exercises: List[Dict[str, Any]] = []  # Contains exercise_id, schedule, and progress
    notes: Optional[str] = None
    status: str = Field(default="active", description="active, completed, cancelled")
    metadata: Optional[Dict[str, Any]] = {}
    
class RehabPlanCreate(RehabPlanBase):
    pass
    
class RehabPlanUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    practitioner_id: Optional[str] = None
    end_date: Optional[datetime] = None
    condition: Optional[str] = None
    goal: Optional[str] = None
    frequency: Optional[str] = None
    exercises: Optional[List[Dict[str, Any]]] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
class RehabPlanResponse(RehabPlanBase):
    id: str = Field(..., alias="_id")
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        
class ProgressUpdate(BaseModel):
    plan_id: str
    exercise_id: str
    date: datetime
    completed: bool
    pain_level: Optional[int] = None
    difficulty_level: Optional[int] = None
    notes: Optional[str] = None
    
class ProgressResponse(ProgressUpdate):
    id: str = Field(..., alias="_id")
    patient_id: str
    
    class Config:
        orm_mode = True
        allow_population_by_field_name = True

# 新增康复评估相关模型
class RangeOfMotion(BaseModel):
    """关节活动度数据，使用0-100的标准化范围"""
    # 每个字段代表一个关节的活动度百分比
    # 例如：shoulder_flexion: 80 表示肩关节屈曲达到正常范围的80%
    shoulder_flexion: Optional[float] = None
    shoulder_extension: Optional[float] = None
    shoulder_abduction: Optional[float] = None
    elbow_flexion: Optional[float] = None
    elbow_extension: Optional[float] = None
    wrist_flexion: Optional[float] = None
    wrist_extension: Optional[float] = None
    hip_flexion: Optional[float] = None
    hip_extension: Optional[float] = None
    knee_flexion: Optional[float] = None
    knee_extension: Optional[float] = None
    ankle_dorsiflexion: Optional[float] = None
    ankle_plantarflexion: Optional[float] = None
    # 允许其他关节的自定义字段
    additionals: Optional[Dict[str, float]] = Field(default_factory=dict)
    
class MuscleStrength(BaseModel):
    """肌肉力量数据，使用医学常用的0-5量表"""
    # 0: 无肌肉收缩, 1: 轻微收缩但无运动, 2: 去重力位可运动,
    # 3: 对抗重力可运动, 4: 对抗阻力可运动, 5: 正常力量
    shoulder_flexors: Optional[float] = None
    shoulder_extensors: Optional[float] = None
    shoulder_abductors: Optional[float] = None
    elbow_flexors: Optional[float] = None
    elbow_extensors: Optional[float] = None
    wrist_flexors: Optional[float] = None
    wrist_extensors: Optional[float] = None
    hip_flexors: Optional[float] = None
    hip_extensors: Optional[float] = None
    knee_flexors: Optional[float] = None
    knee_extensors: Optional[float] = None
    ankle_dorsiflexors: Optional[float] = None
    ankle_plantarflexors: Optional[float] = None
    additionals: Optional[Dict[str, float]] = Field(default_factory=dict)
    
class PainLevel(BaseModel):
    """疼痛水平数据，使用0-10量表"""
    # 0: 无痛, 10: 极度疼痛
    head: Optional[int] = None
    neck: Optional[int] = None
    shoulder_left: Optional[int] = None
    shoulder_right: Optional[int] = None
    arm_left: Optional[int] = None
    arm_right: Optional[int] = None
    elbow_left: Optional[int] = None
    elbow_right: Optional[int] = None
    wrist_left: Optional[int] = None
    wrist_right: Optional[int] = None
    hand_left: Optional[int] = None
    hand_right: Optional[int] = None
    back_upper: Optional[int] = None
    back_lower: Optional[int] = None
    hip_left: Optional[int] = None
    hip_right: Optional[int] = None
    knee_left: Optional[int] = None
    knee_right: Optional[int] = None
    ankle_left: Optional[int] = None
    ankle_right: Optional[int] = None
    foot_left: Optional[int] = None
    foot_right: Optional[int] = None
    additionals: Optional[Dict[str, int]] = Field(default_factory=dict)
    
class FunctionalStatus(BaseModel):
    """功能状态评估，使用0-100量表"""
    # 每个字段代表一个功能活动的完成情况
    # 0: 完全无法完成, 100: 完全正常完成
    walking: Optional[float] = None
    stair_climbing: Optional[float] = None
    sitting_to_standing: Optional[float] = None
    standing_balance: Optional[float] = None
    reaching_overhead: Optional[float] = None
    grasping: Optional[float] = None
    fine_motor_control: Optional[float] = None
    bed_mobility: Optional[float] = None
    transfers: Optional[float] = None
    self_care: Optional[float] = None
    daily_activities: Optional[float] = None
    additionals: Optional[Dict[str, float]] = Field(default_factory=dict)
    
class AssessmentBase(BaseModel):
    """康复评估基础模型"""
    patient_id: str
    plan_id: Optional[str] = None
    practitioner_id: Optional[str] = None
    assessment_type: str = Field(..., description="initial, follow_up, discharge")
    range_of_motion: Optional[Dict[str, float]] = Field(default_factory=dict)
    muscle_strength: Optional[Dict[str, float]] = Field(default_factory=dict)
    pain_level: Optional[Dict[str, int]] = Field(default_factory=dict)
    functional_status: Optional[Dict[str, float]] = Field(default_factory=dict)
    notes: Optional[str] = None
    
class AssessmentCreate(AssessmentBase):
    """创建新的康复评估"""
    pass
    
class AssessmentUpdate(BaseModel):
    """更新康复评估信息"""
    practitioner_id: Optional[str] = None
    assessment_type: Optional[str] = None
    range_of_motion: Optional[Dict[str, float]] = None
    muscle_strength: Optional[Dict[str, float]] = None
    pain_level: Optional[Dict[str, int]] = None
    functional_status: Optional[Dict[str, float]] = None
    notes: Optional[str] = None
    
class AssessmentResponse(AssessmentBase):
    """康复评估响应模型"""
    id: str = Field(..., alias="_id")
    created_at: datetime
    updated_at: datetime
    scores: Dict[str, float]  # 自动计算的评估得分
    ai_analysis: Optional[Dict[str, Any]] = None  # AI生成的评估分析
    
    class Config:
        orm_mode = True
        allow_population_by_field_name = True 