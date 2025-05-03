"""
康复计划数据模型
定义康复计划和锻炼
"""
from datetime import datetime
from bson import ObjectId
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

class Exercise:
    """锻炼/康复动作模型"""
    collection_name = "exercises"
    
    def __init__(
        self,
        name: str,
        description: str,
        body_part: str,
        difficulty: str,  # Easy, Medium, Hard
        duration_minutes: int,
        repetitions: int = None,
        sets: int = None,
        instructions: List[str] = None,
        contraindications: List[str] = None,
        benefits: List[str] = None,
        video_url: str = None,
        image_url: str = None,
        created_by: str = None,
        tags: List[str] = None,
        created_at: datetime = None,
        updated_at: datetime = None,
        _id: str = None,
        metadata: Dict[str, Any] = None
    ):
        self.name = name
        self.description = description
        self.body_part = body_part
        self.difficulty = difficulty
        self.duration_minutes = duration_minutes
        self.repetitions = repetitions
        self.sets = sets
        self.instructions = instructions or []
        self.contraindications = contraindications or []
        self.benefits = benefits or []
        self.video_url = video_url
        self.image_url = image_url
        self.created_by = created_by
        self.tags = tags or []
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self._id = _id or str(ObjectId())
        self.metadata = metadata or {}
    
    @classmethod
    def from_mongo(cls, mongo_doc):
        """从MongoDB文档创建锻炼对象"""
        if not mongo_doc:
            return None
            
        exercise_data = mongo_doc.copy()
        exercise_data["_id"] = str(exercise_data["_id"])
        
        return cls(**exercise_data)
    
    def to_mongo(self):
        """将锻炼对象转换为MongoDB文档"""
        doc = self.__dict__.copy()
        if doc.get("_id") and isinstance(doc["_id"], str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc
    
    def to_dict(self):
        """将锻炼对象转换为字典，用于API响应"""
        return self.__dict__.copy()


class RehabilitationPlan:
    """康复计划模型"""
    collection_name = "rehabilitation_plans"
    
    def __init__(
        self,
        name: str,
        description: str,
        patient_id: str,
        practitioner_id: str = None,
        start_date: datetime = None,
        end_date: datetime = None,
        condition: str = None,
        goal: str = None,
        frequency: str = None,
        exercises: List[Dict[str, Any]] = None,  # 包含锻炼ID、计划和进度
        notes: str = None,
        status: str = "active",  # active, completed, cancelled
        health_manager_id: str = None,
        created_at: datetime = None,
        updated_at: datetime = None,
        _id: str = None,
        metadata: Dict[str, Any] = None
    ):
        self.name = name
        self.description = description
        self.patient_id = patient_id
        self.practitioner_id = practitioner_id
        self.start_date = start_date or datetime.utcnow()
        self.end_date = end_date
        self.condition = condition or ""
        self.goal = goal or ""
        self.frequency = frequency or "daily"
        self.exercises = exercises or []
        self.notes = notes or ""
        self.status = status
        self.health_manager_id = health_manager_id
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self._id = _id or str(ObjectId())
        self.metadata = metadata or {}
    
    @classmethod
    def from_mongo(cls, mongo_doc):
        """从MongoDB文档创建康复计划对象"""
        if not mongo_doc:
            return None
            
        plan_data = mongo_doc.copy()
        plan_data["_id"] = str(plan_data["_id"])
        
        return cls(**plan_data)
    
    def to_mongo(self):
        """将康复计划对象转换为MongoDB文档"""
        doc = self.__dict__.copy()
        if doc.get("_id") and isinstance(doc["_id"], str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc
    
    def to_dict(self):
        """将康复计划对象转换为字典，用于API响应"""
        return self.__dict__.copy()
    
    def add_exercise(self, exercise_id: str, schedule: Dict[str, Any] = None):
        """添加锻炼到康复计划"""
        exercise_entry = {
            "exercise_id": exercise_id,
            "schedule": schedule or {"frequency": "daily", "time_of_day": "morning"},
            "progress": [],
            "added_at": datetime.utcnow()
        }
        self.exercises.append(exercise_entry)
        self.updated_at = datetime.utcnow()
        
    def update_exercise_schedule(self, exercise_id: str, schedule: Dict[str, Any]):
        """更新锻炼计划"""
        for exercise in self.exercises:
            if exercise["exercise_id"] == exercise_id:
                exercise["schedule"] = schedule
                exercise["updated_at"] = datetime.utcnow()
                self.updated_at = datetime.utcnow()
                break
    
    def record_progress(self, exercise_id: str, completed: bool, date: datetime = None, 
                      pain_level: int = None, difficulty_level: int = None, notes: str = None):
        """记录锻炼进度"""
        progress_entry = {
            "date": date or datetime.utcnow(),
            "completed": completed,
            "pain_level": pain_level,
            "difficulty_level": difficulty_level,
            "notes": notes
        }
        
        for exercise in self.exercises:
            if exercise["exercise_id"] == exercise_id:
                exercise["progress"].append(progress_entry)
                self.updated_at = datetime.utcnow()
                break
    
    def complete_plan(self, notes: str = None):
        """完成康复计划"""
        self.status = "completed"
        if notes:
            self.notes = f"{self.notes}\nCompletion notes: {notes}"
        self.updated_at = datetime.utcnow()
    
    def cancel_plan(self, reason: str = None):
        """取消康复计划"""
        self.status = "cancelled"
        if reason:
            self.notes = f"{self.notes}\nCancellation reason: {reason}"
        self.updated_at = datetime.utcnow()


class ProgressRecord:
    """进度记录模型，用于跟踪康复计划的进度"""
    collection_name = "progress_records"
    
    def __init__(
        self,
        plan_id: str,
        exercise_id: str,
        patient_id: str,
        date: datetime = None,
        completed: bool = False,
        pain_level: int = None,
        difficulty_level: int = None,
        notes: str = None,
        recorded_by: str = None,  # 可以是患者自己或医疗人员
        created_at: datetime = None,
        _id: str = None
    ):
        self.plan_id = plan_id
        self.exercise_id = exercise_id
        self.patient_id = patient_id
        self.date = date or datetime.utcnow()
        self.completed = completed
        self.pain_level = pain_level
        self.difficulty_level = difficulty_level
        self.notes = notes or ""
        self.recorded_by = recorded_by
        self.created_at = created_at or datetime.utcnow()
        self._id = _id or str(ObjectId())
    
    @classmethod
    def from_mongo(cls, mongo_doc):
        """从MongoDB文档创建进度记录对象"""
        if not mongo_doc:
            return None
            
        record_data = mongo_doc.copy()
        record_data["_id"] = str(record_data["_id"])
        
        return cls(**record_data)
    
    def to_mongo(self):
        """将进度记录对象转换为MongoDB文档"""
        doc = self.__dict__.copy()
        if doc.get("_id") and isinstance(doc["_id"], str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc
    
    def to_dict(self):
        """将进度记录对象转换为字典，用于API响应"""
        return self.__dict__.copy()


# 康复进度模型
class RehabProgress(BaseModel):
    id: str = Field(default_factory=lambda: str(ObjectId()))
    plan: str  # 康复计划名称
    progress: int  # 进度百分比 0-100
    next_session: str  # 下次康复时间描述
    user_id: str  # 患者ID
    doctor_id: Optional[str] = None  # 医生ID
    exercises: List[Dict[str, Any]]  # 训练项目列表
    timestamp: datetime = Field(default_factory=datetime.now)
    
    class Config:
        schema_extra = {
            "example": {
                "id": "60d21b4967d0d8992e610c85",
                "plan": "下肢功能恢复计划",
                "progress": 65,
                "next_session": "明天 15:00",
                "user_id": "60d21b4967d0d8992e610c83",
                "doctor_id": "60d21b4967d0d8992e610c82",
                "exercises": [
                    { "name": "下肢伸展", "completed": True },
                    { "name": "平衡训练", "completed": True },
                    { "name": "步态训练", "completed": False },
                    { "name": "力量训练", "completed": False }
                ],
                "timestamp": "2023-08-15T14:30:00.000Z"
            }
        } 