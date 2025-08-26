"""
用户数据模型
定义所有与用户相关的MongoDB数据模型
"""
from datetime import datetime
from bson import ObjectId
from typing import Dict, List, Optional, Any

class User:
    """
    基础用户模型
    所有类型的用户都继承自此基类
    """
    collection_name = "users"
    
    def __init__(
        self,
        email: str,
        name: str,
        password_hash: str,
        role: str = "patient",
        permissions: List[str] = None,
        is_active: bool = True,
        last_login: Optional[datetime] = None,
        created_at: datetime = None,
        updated_at: datetime = None,
        _id: str = None,
        metadata: Dict[str, Any] = None
    ):
        self.email = email
        self.name = name
        self.password_hash = password_hash
        self.role = role
        self.permissions = permissions or []
        self.is_active = is_active
        self.last_login = last_login
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self._id = _id or str(ObjectId())
        self.metadata = metadata or {}
    
    @classmethod
    def from_mongo(cls, mongo_doc):
        """
        从MongoDB文档创建用户对象
        """
        if not mongo_doc:
            return None
            
        user_data = mongo_doc.copy()
        user_data["_id"] = str(user_data["_id"])
        
        role = user_data.get("role", "patient")
        
        # 根据角色创建相应的用户类型
        if role == "doctor":
            return Doctor.from_mongo(mongo_doc)
        elif role == "patient":
            return Patient.from_mongo(mongo_doc)
        elif role == "health_manager":
            return HealthManager.from_mongo(mongo_doc)
        elif role == "admin":
            return SystemAdmin.from_mongo(mongo_doc)
        else:
            return cls(**user_data)
    
    def to_mongo(self):
        """
        将用户对象转换为MongoDB文档
        """
        doc = self.__dict__.copy()
        if doc.get("_id") and isinstance(doc["_id"], str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc
    
    def to_dict(self):
        """
        将用户对象转换为字典，用于API响应
        """
        user_dict = self.__dict__.copy()
        # 删除不应在API响应中显示的字段
        user_dict.pop("password_hash", None)
        return user_dict


class Patient(User):
    """患者用户模型"""
    
    def __init__(
        self,
        email: str,
        name: str,
        password_hash: str,
        medical_info: Dict[str, Any] = None,
        practitioners: List[str] = None,
        health_managers: List[str] = None,
        rehabilitation_plans: List[str] = None,
        devices: List[str] = None,
        emergency_contact: Dict[str, str] = None,
        demographic_info: Dict[str, Any] = None,
        permissions: List[str] = None,
        is_active: bool = True,
        **kwargs
    ):
        super().__init__(
            email, 
            name, 
            password_hash, 
            role="patient", 
            permissions=permissions, 
            is_active=is_active, 
            **kwargs
        )
        self.medical_info = medical_info or {}
        self.practitioners = practitioners or []
        self.health_managers = health_managers or []
        self.rehabilitation_plans = rehabilitation_plans or []
        self.devices = devices or []
        self.emergency_contact = emergency_contact or {}
        self.demographic_info = demographic_info or {}
    
    @classmethod
    def from_mongo(cls, mongo_doc):
        if not mongo_doc:
            return None
            
        user_data = mongo_doc.copy()
        user_data["_id"] = str(user_data["_id"])
        
        return cls(**user_data)


class Doctor(User):
    """医生用户模型"""
    
    def __init__(
        self,
        email: str,
        name: str,
        password_hash: str,
        specialty: str = None,
        license_number: str = None,
        patients: List[str] = None,
        organization_id: str = None,
        schedules: List[Dict[str, Any]] = None,
        permissions: List[str] = None,
        is_active: bool = True,
        professional_title: str = None,
        department: str = None,
        **kwargs
    ):
        super().__init__(
            email, 
            name, 
            password_hash, 
            role="doctor", 
            permissions=permissions, 
            is_active=is_active, 
            **kwargs
        )
        self.specialty = specialty
        self.license_number = license_number
        self.patients = patients or []
        self.organization_id = organization_id
        self.schedules = schedules or []
        self.professional_title = professional_title
        self.department = department
    
    @classmethod
    def from_mongo(cls, mongo_doc):
        if not mongo_doc:
            return None
            
        user_data = mongo_doc.copy()
        user_data["_id"] = str(user_data["_id"])
        
        return cls(**user_data)


class HealthManager(User):
    """健康管理师用户模型"""
    
    def __init__(
        self,
        email: str,
        name: str,
        password_hash: str,
        certification: str = None,
        patients: List[str] = None,
        organization_id: str = None,
        schedules: List[Dict[str, Any]] = None,
        permissions: List[str] = None,
        is_active: bool = True,
        specialty_areas: List[str] = None,
        education: Dict[str, str] = None,
        **kwargs
    ):
        super().__init__(
            email, 
            name, 
            password_hash, 
            role="health_manager", 
            permissions=permissions, 
            is_active=is_active, 
            **kwargs
        )
        self.certification = certification
        self.patients = patients or []
        self.organization_id = organization_id
        self.schedules = schedules or []
        self.specialty_areas = specialty_areas or []
        self.education = education or {}
    
    @classmethod
    def from_mongo(cls, mongo_doc):
        if not mongo_doc:
            return None
            
        user_data = mongo_doc.copy()
        user_data["_id"] = str(user_data["_id"])
        
        return cls(**user_data)


class SystemAdmin(User):
    """系统管理员用户模型"""
    
    def __init__(
        self,
        email: str,
        name: str,
        password_hash: str,
        permissions: List[str] = None,
        is_active: bool = True,
        admin_level: str = "regular",  # regular, super
        managed_organizations: List[str] = None,
        **kwargs
    ):
        # 管理员默认拥有系统管理权限
        admin_permissions = permissions or ["users", "organizations", "tags", "devices", "system"]
        super().__init__(
            email, 
            name, 
            password_hash, 
            role="admin", 
            permissions=admin_permissions, 
            is_active=is_active, 
            **kwargs
        )
        self.admin_level = admin_level
        self.managed_organizations = managed_organizations or []
    
    @classmethod
    def from_mongo(cls, mongo_doc):
        if not mongo_doc:
            return None
            
        user_data = mongo_doc.copy()
        user_data["_id"] = str(user_data["_id"])
        
        return cls(**user_data) 