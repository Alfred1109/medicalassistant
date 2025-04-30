from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timedelta
from passlib.context import CryptContext
from jose import jwt
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson.objectid import ObjectId
import bcrypt
import logging
from fastapi import HTTPException, status, Request

from app.core.config import settings
from app.schemas.user import UserCreate, UserUpdate, UserResponse, Token, PermissionAssignment
from app.core.permissions import ROLE_PERMISSIONS, Permission
from app.db.mongodb import get_database
from app.services.audit_log_service import AuditLogService

logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class UserService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.users
        self.audit_service = AuditLogService(db)
        # 初始化时不能在同步函数中调用异步方法，需要在外部调用
        
    async def initialize(self):
        """初始化用户服务，创建默认账户"""
        await self._ensure_default_users()
        return self
        
    async def _ensure_default_users(self):
        """确保默认管理员用户存在"""
        default_admin = await self.get_user_by_email("admin@example.com")
        if not default_admin:
            logger.info("Creating default admin user")
            admin_data = UserCreate(
                name="System Admin",
                email="admin@example.com",
                password="admin123",
                role="admin"
            )
            await self.create_user(admin_data)
            
        # 添加默认测试用户
        test_user = await self.get_user_by_email("test@example.com")
        if not test_user:
            logger.info("Creating test user")
            test_data = UserCreate(
                name="Test User",
                email="test@example.com",
                password="password123",
                role="patient"
            )
            await self.create_user(test_data)
        
    async def create_user(self, user_data: UserCreate) -> UserResponse:
        """Create a new user"""
        # Check if user with this email already exists
        existing_user = await self.get_user_by_email(user_data.email)
        if existing_user:
            raise ValueError("Email already registered")
        
        # Hash the password
        hashed_password = self._get_password_hash(user_data.password)
        
        # 获取角色默认权限
        default_permissions = ROLE_PERMISSIONS.get(user_data.role, [])
        permissions = list(set(default_permissions + (user_data.permissions or [])))
        
        # Prepare user document
        user_doc = {
            "name": user_data.name,
            "email": user_data.email,
            "hashed_password": hashed_password,
            "role": user_data.role,
            "permissions": permissions,
            "is_active": user_data.is_active,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        # Insert user
        result = await self.collection.insert_one(user_doc)
        
        # Get created user
        created_user = await self.get_user_by_id(str(result.inserted_id))
        return created_user
        
    async def get_user_by_id(self, user_id: str) -> Optional[UserResponse]:
        """Get user by ID"""
        try:
            user = await self.collection.find_one({"_id": ObjectId(user_id)})
            if user:
                return self._map_user_to_schema(user)
            return None
        except Exception as e:
            logger.error(f"Error getting user by ID: {e}")
            return None
        
    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email"""
        try:
            user = await self.collection.find_one({"email": email})
            return user
        except Exception as e:
            logger.error(f"Error getting user by email: {e}")
            return None
        
    async def update_user(self, user_id: str, user_data: UserUpdate) -> Optional[UserResponse]:
        """Update user details"""
        update_data = {k: v for k, v in user_data.model_dump().items() if v is not None}
        
        if "password" in update_data:
            update_data["hashed_password"] = self._get_password_hash(update_data.pop("password"))
        
        # 处理权限更新
        if "permissions" in update_data:
            # 获取当前用户
            current_user = await self.collection.find_one({"_id": ObjectId(user_id)})
            if not current_user:
                return None
            
            # 获取角色默认权限
            role = update_data.get("role", current_user.get("role", "patient"))
            default_permissions = ROLE_PERMISSIONS.get(role, [])
            
            # 合并默认权限和自定义权限
            permissions = list(set(default_permissions + update_data["permissions"]))
            update_data["permissions"] = permissions
        
        update_data["updated_at"] = datetime.utcnow()
        
        await self.collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": update_data}
        )
        
        return await self.get_user_by_id(user_id)
    
    async def update_user_permissions(
        self, 
        user_id: str, 
        permissions: List[str], 
        operator_id: str,
        request: Optional[Request] = None
    ) -> Optional[UserResponse]:
        """
        更新用户权限
        
        参数:
        - user_id: 目标用户ID
        - permissions: 要设置的权限列表
        - operator_id: 执行操作的用户ID
        - request: HTTP请求对象（可选，用于获取IP地址）
        """
        # 获取当前用户
        user = await self.collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            return None
        
        # 获取原有的用户自定义权限
        current_permissions = user.get("permissions", [])
        
        # 获取角色默认权限
        role = user.get("role", "patient")
        default_permissions = ROLE_PERMISSIONS.get(role, [])
        
        # 合并默认权限和自定义权限
        all_permissions = list(set(default_permissions + permissions))
        
        # 计算新增和移除的权限
        added_permissions = [p for p in permissions if p not in current_permissions]
        removed_permissions = [p for p in current_permissions if p not in permissions]
        
        # 更新用户权限
        await self.collection.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "permissions": all_permissions,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # 获取IP地址
        ip_address = None
        if request and hasattr(request, 'client') and request.client:
            ip_address = request.client.host
        
        # 记录审计日志-权限变更
        try:
            # 记录权限添加操作
            for permission in added_permissions:
                await self.audit_service.log_permission_change(
                    user_id=operator_id,
                    target_user_id=user_id,
                    permission=permission,
                    action="grant",
                    ip_address=ip_address,
                    details={
                        "role": role,
                        "operation": "grant_permission"
                    }
                )
            
            # 记录权限移除操作
            for permission in removed_permissions:
                await self.audit_service.log_permission_change(
                    user_id=operator_id,
                    target_user_id=user_id,
                    permission=permission,
                    action="revoke",
                    ip_address=ip_address,
                    details={
                        "role": role,
                        "operation": "revoke_permission"
                    }
                )
        except Exception as e:
            # 记录日志错误但不影响业务流程
            logger.error(f"Failed to create audit log for permission update: {str(e)}")
        
        return await self.get_user_by_id(user_id)
    
    async def has_permission(self, user_id: str, permission: str) -> bool:
        """检查用户是否具有指定权限"""
        user = await self.collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            return False
        
        # 管理员拥有所有权限
        if user.get("role") == "admin":
            return True
        
        # 检查用户权限列表
        user_permissions = user.get("permissions", [])
        if permission in user_permissions:
            return True
        
        # 检查角色默认权限
        role = user.get("role", "patient")
        default_permissions = ROLE_PERMISSIONS.get(role, [])
        if permission in default_permissions:
            return True
        
        return False
        
    async def list_users(self, role: Optional[str] = None, skip: int = 0, limit: int = 100) -> List[UserResponse]:
        """List users with optional filtering by role"""
        query = {}
        if role:
            query["role"] = role
        
        users = await self.db.users.find(query).skip(skip).limit(limit).to_list(length=limit)
        return [self._user_doc_to_response(user) for user in users]
        
    async def get_doctors(self, 
                          status: Optional[str] = None, 
                          department: Optional[str] = None, 
                          skip: int = 0, 
                          limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取医生列表，支持按状态和科室筛选
        """
        logging.info(f"获取医生列表: status={status}, department={department}, skip={skip}, limit={limit}")
        
        # 基础查询：角色为医生
        query = {"role": "doctor"}
        
        # 添加筛选条件
        if status:
            query["metadata.status"] = status
        
        if department:
            query["department"] = department
        
        logging.info(f"医生查询条件: {query}")
        
        # 执行查询
        doctor_docs = await self.db.users.find(query).skip(skip).limit(limit).to_list(length=limit)
        
        logging.info(f"查询到 {len(doctor_docs)} 条医生记录")
        if len(doctor_docs) > 0:
            logging.debug(f"第一条医生记录: {doctor_docs[0]}")
        
        # 转换为前端需要的格式
        doctors = []
        for doc in doctor_docs:
            # 获取元数据信息，确保即使不存在也返回空字典
            metadata = doc.get("metadata", {}) or {}
            
            doctor = {
                "id": str(doc["_id"]),
                "name": doc.get("name", ""),
                "avatar": "",  # 默认空，将来可以扩展
                "department": doc.get("department", ""),
                "title": doc.get("professional_title", ""),
                "specialty": doc.get("specialty", ""),
                "email": doc.get("email", ""),
                "phone": metadata.get("phone", ""),
                "patients": metadata.get("patients_count", 0),
                "status": metadata.get("status", "在职"),
                "joinDate": metadata.get("join_date", ""),
                "certifications": metadata.get("certifications", []),
            }
            doctors.append(doctor)
        
        logging.info(f"返回 {len(doctors)} 条格式化医生数据")
        if len(doctors) > 0:
            logging.debug(f"第一条格式化医生数据: {doctors[0]}")
        
        return doctors
    
    async def deactivate_user(self, user_id: str) -> bool:
        """停用用户账户"""
        result = await self.collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"is_active": False, "updated_at": datetime.utcnow()}}
        )
        return result.modified_count > 0
    
    async def activate_user(self, user_id: str) -> bool:
        """激活用户账户"""
        result = await self.collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"is_active": True, "updated_at": datetime.utcnow()}}
        )
        return result.modified_count > 0
        
    async def authenticate_user(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate a user"""
        user = await self.get_user_by_email(email)
        if not user:
            return None
        if not self._verify_password(password, user["hashed_password"]):
            return None
        
        # 检查用户是否激活
        if not user.get("is_active", True):
            raise ValueError("用户账户已停用")
        
        # 更新最后登录时间
        await self.collection.update_one(
            {"_id": user["_id"]},
            {"$set": {"last_login": datetime.utcnow()}}
        )
        
        return user
        
    async def create_token(self, user: Dict[str, Any]) -> Token:
        """Create access token for user"""
        user_obj = self._map_user_to_schema(user)
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        # Create JWT token
        to_encode = {
            "sub": str(user["_id"]),
            "exp": expire,
            "email": user["email"],
            "role": user["role"],
            "permissions": user.get("permissions", [])
        }
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        
        return Token(access_token=encoded_jwt, token_type="bearer", user=user_obj)
        
    async def assign_practitioner(self, patient_id: str, practitioner_id: str) -> Optional[UserResponse]:
        """Assign a practitioner to a patient"""
        # Get patient and practitioner to verify they exist
        patient = await self.get_user_by_id(patient_id)
        practitioner = await self.get_user_by_id(practitioner_id)
        
        if not patient or not practitioner or patient.role != "patient" or practitioner.role not in ["doctor", "health_manager"]:
            return None
        
        # 确定应该更新的字段
        field_to_update = "practitioners" if practitioner.role == "doctor" else "health_managers"
        
        # Update patient record with practitioner ID
        await self.collection.update_one(
            {"_id": ObjectId(patient_id)},
            {"$addToSet": {field_to_update: practitioner_id}, "$set": {"updated_at": datetime.utcnow()}}
        )
        
        # 同时更新医生/健管师的患者列表
        await self.collection.update_one(
            {"_id": ObjectId(practitioner_id)},
            {"$addToSet": {"patients": patient_id}, "$set": {"updated_at": datetime.utcnow()}}
        )
        
        return await self.get_user_by_id(patient_id)
    
    async def remove_practitioner(self, patient_id: str, practitioner_id: str) -> Optional[UserResponse]:
        """移除患者的医生/健管师关联"""
        # Get patient and practitioner to verify they exist
        patient = await self.get_user_by_id(patient_id)
        practitioner = await self.get_user_by_id(practitioner_id)
        
        if not patient or not practitioner or patient.role != "patient":
            return None
        
        # 确定应该更新的字段
        field_to_update = "practitioners" if practitioner.role == "doctor" else "health_managers"
        
        # 从患者记录中移除医生/健管师ID
        await self.collection.update_one(
            {"_id": ObjectId(patient_id)},
            {"$pull": {field_to_update: practitioner_id}, "$set": {"updated_at": datetime.utcnow()}}
        )
        
        # 同时从医生/健管师的患者列表中移除患者
        await self.collection.update_one(
            {"_id": ObjectId(practitioner_id)},
            {"$pull": {"patients": patient_id}, "$set": {"updated_at": datetime.utcnow()}}
        )
        
        return await self.get_user_by_id(patient_id)
        
    # Helper methods
    def _get_password_hash(self, password: str) -> str:
        """Hash a password"""
        # Use bcrypt for password hashing
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode(), salt)
        return hashed.decode()
        
    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
        
    def _map_user_to_schema(self, user: Dict[str, Any]) -> UserResponse:
        """Map a user document to a UserResponse schema"""
        base_user = {
            "id": str(user["_id"]),
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
            "permissions": user.get("permissions", []),
            "is_active": user.get("is_active", True),
            "createdAt": user["created_at"],
            "updatedAt": user["updated_at"],
            "last_login": user.get("last_login")
        }
        
        # 根据角色返回不同的响应模型
        from app.schemas.user import DoctorResponse, PatientResponse, HealthManagerResponse, AdminResponse
        
        if user["role"] == "doctor":
            return DoctorResponse(
                **base_user,
                specialty=user.get("specialty"),
                license_number=user.get("license_number"),
                patients=user.get("patients", []),
                organization_id=user.get("organization_id"),
                schedules=user.get("schedules", []),
                professional_title=user.get("professional_title"),
                department=user.get("department")
            )
        elif user["role"] == "patient":
            return PatientResponse(
                **base_user,
                medical_info=user.get("medical_info", {}),
                practitioners=user.get("practitioners", []),
                health_managers=user.get("health_managers", []),
                rehabilitation_plans=user.get("rehabilitation_plans", []),
                devices=user.get("devices", []),
                emergency_contact=user.get("emergency_contact", {}),
                demographic_info=user.get("demographic_info", {})
            )
        elif user["role"] == "health_manager":
            return HealthManagerResponse(
                **base_user,
                certification=user.get("certification"),
                patients=user.get("patients", []),
                organization_id=user.get("organization_id"),
                schedules=user.get("schedules", []),
                specialty_areas=user.get("specialty_areas", []),
                education=user.get("education", {})
            )
        elif user["role"] == "admin":
            return AdminResponse(
                **base_user,
                admin_level=user.get("admin_level", "regular"),
                managed_organizations=user.get("managed_organizations", [])
            )
        else:
            return UserResponse(**base_user) 