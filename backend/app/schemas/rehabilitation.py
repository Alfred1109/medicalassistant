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