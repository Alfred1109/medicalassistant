from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime

# 基础用户模型
class UserBase(BaseModel):
    email: EmailStr
    name: str
    role: str = "patient"  # 默认角色为病人
    permissions: Optional[List[str]] = None
    is_active: bool = True

# 用户创建模型
class UserCreate(UserBase):
    password: str
    # 医生特有字段
    specialty: Optional[str] = None
    license_number: Optional[str] = None
    professional_title: Optional[str] = None
    department: Optional[str] = None
    # 健康管理师特有字段
    certification: Optional[str] = None
    specialty_areas: Optional[List[str]] = None
    education: Optional[Dict[str, str]] = None
    # 患者特有字段
    medical_info: Optional[Dict[str, Any]] = None
    emergency_contact: Optional[Dict[str, str]] = None
    demographic_info: Optional[Dict[str, Any]] = None
    
    @validator('role')
    def validate_role(cls, v):
        if v not in ["patient", "doctor", "health_manager", "admin"]:
            raise ValueError('Role must be one of: patient, doctor, health_manager, admin')
        return v

# 用户更新模型
class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    permissions: Optional[List[str]] = None
    is_active: Optional[bool] = None
    
    @validator('role')
    def validate_role(cls, v):
        if v is not None and v not in ["patient", "doctor", "health_manager", "admin"]:
            raise ValueError('Role must be one of: patient, doctor, health_manager, admin')
        return v

# 用户响应模型
class UserResponse(UserBase):
    id: str
    createdAt: datetime
    updatedAt: datetime
    last_login: Optional[datetime] = None
    
    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }

# 权限赋予模型
class PermissionAssignment(BaseModel):
    user_id: str
    permissions: List[str]
    
# 登录请求模型
class UserLogin(BaseModel):
    email: EmailStr
    password: str

# Token数据模型
class TokenData(BaseModel):
    user_id: str
    
# Token负载模型
class TokenPayload(BaseModel):
    sub: Optional[str] = None
    exp: Optional[int] = None
    email: Optional[str] = None
    role: Optional[str] = None
    permissions: Optional[List[str]] = None
    
# Token响应模型
class Token(BaseModel):
    access_token: str
    token_type: str
    user: Optional[UserResponse] = None

# 扩展的Token响应模型，包含refresh token
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    user: Optional[UserResponse] = None
    expires_in: int
    
# 刷新Token请求模型
class RefreshTokenRequest(BaseModel):
    refresh_token: str

# 特定角色用户数据
# 医生响应
class DoctorResponse(UserResponse):
    specialty: Optional[str] = None
    license_number: Optional[str] = None
    patients: Optional[List[str]] = []
    organization_id: Optional[str] = None
    schedules: Optional[List[Dict[str, Any]]] = []
    professional_title: Optional[str] = None
    department: Optional[str] = None

# 健康管理师响应
class HealthManagerResponse(UserResponse):
    certification: Optional[str] = None
    patients: Optional[List[str]] = []
    organization_id: Optional[str] = None
    schedules: Optional[List[Dict[str, Any]]] = []
    specialty_areas: Optional[List[str]] = []
    education: Optional[Dict[str, str]] = {}

# 患者响应
class PatientResponse(UserResponse):
    medical_info: Optional[Dict[str, Any]] = {}
    practitioners: Optional[List[str]] = []
    health_managers: Optional[List[str]] = []
    rehabilitation_plans: Optional[List[str]] = []
    devices: Optional[List[str]] = []
    emergency_contact: Optional[Dict[str, str]] = {}
    demographic_info: Optional[Dict[str, Any]] = {}

# 管理员响应
class AdminResponse(UserResponse):
    admin_level: str = "regular"
    managed_organizations: Optional[List[str]] = []

# 用户医疗信息
class UserMedicalInfo(BaseModel):
    height: Optional[float] = None
    weight: Optional[float] = None
    medical_conditions: Optional[List[str]] = None
    allergies: Optional[List[str]] = None
    medications: Optional[List[dict]] = None
    blood_type: Optional[str] = None
    chronic_diseases: Optional[List[str]] = None
    surgery_history: Optional[List[Dict[str, Any]]] = None
    family_history: Optional[Dict[str, List[str]]] = None

# 应用于用户的组织关系
class UserOrganizationRelation(BaseModel):
    user_id: str
    organization_id: str
    role: str  # 在组织中的角色
    department: Optional[str] = None
    joined_at: datetime = Field(default_factory=datetime.utcnow)
    
# 用户会话信息
class UserSession(BaseModel):
    user_id: str
    session_id: str
    ip_address: str
    user_agent: str
    login_time: datetime
    expires_at: datetime
    is_active: bool = True 