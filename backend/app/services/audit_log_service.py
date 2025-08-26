from datetime import datetime
from typing import List, Dict, Any, Optional
from bson import ObjectId

from motor.motor_asyncio import AsyncIOMotorDatabase
from app.models.audit_log import AuditLog
from app.schemas.audit_log import AuditLogCreate, AuditLogFilter


class AuditLogService:
    """审计日志服务类"""
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.audit_logs
    
    async def create_log(self, log_data: AuditLogCreate, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """创建审计日志"""
        # 准备日志数据
        log_dict = log_data.dict()
        if ip_address:
            log_dict["ip_address"] = ip_address
        
        log_dict["created_at"] = datetime.utcnow()
        
        # 插入数据库
        result = await self.collection.insert_one(log_dict)
        log_dict["id"] = str(result.inserted_id)
        
        return log_dict
    
    async def log_permission_check(
        self, 
        user_id: str, 
        permission: str, 
        resource_id: Optional[str] = None, 
        is_granted: bool = True,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """记录权限检查日志"""
        log_data = AuditLogCreate(
            user_id=user_id,
            action="access",
            resource_type="permission",
            resource_id=resource_id,
            status="success" if is_granted else "failure",
            details={
                "permission": permission,
                **(details or {})
            }
        )
        return await self.create_log(log_data, ip_address)
    
    async def log_permission_change(
        self,
        user_id: str,
        target_user_id: str,
        permission: str,
        action: str,  # 'grant' or 'revoke'
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """记录权限变更日志"""
        log_data = AuditLogCreate(
            user_id=user_id,
            action=action,
            resource_type="permission",
            resource_id=target_user_id,
            details={
                "permission": permission,
                "target_user_id": target_user_id,
                **(details or {})
            }
        )
        return await self.create_log(log_data, ip_address)
    
    async def log_role_assignment(
        self,
        user_id: str,
        target_user_id: str,
        role: str,
        action: str,  # 'assign' or 'remove'
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """记录角色分配日志"""
        log_data = AuditLogCreate(
            user_id=user_id,
            action=action,
            resource_type="role",
            resource_id=target_user_id,
            details={
                "role": role,
                "target_user_id": target_user_id,
                **(details or {})
            }
        )
        return await self.create_log(log_data, ip_address)
    
    async def get_logs(
        self, 
        filter_params: AuditLogFilter, 
        skip: int = 0, 
        limit: int = 50,
        sort_by: str = "created_at",
        sort_order: int = -1  # -1 for descending, 1 for ascending
    ) -> Dict[str, Any]:
        """获取审计日志列表"""
        # 构建查询条件
        query = {}
        
        if filter_params.user_id:
            query["user_id"] = filter_params.user_id
        
        if filter_params.action:
            query["action"] = filter_params.action
        
        if filter_params.resource_type:
            query["resource_type"] = filter_params.resource_type
        
        if filter_params.resource_id:
            query["resource_id"] = filter_params.resource_id
        
        if filter_params.status:
            query["status"] = filter_params.status
        
        # 时间范围查询
        date_query = {}
        if filter_params.start_date:
            date_query["$gte"] = filter_params.start_date
        
        if filter_params.end_date:
            date_query["$lte"] = filter_params.end_date
        
        if date_query:
            query["created_at"] = date_query
        
        # 统计总数
        total = await self.collection.count_documents(query)
        
        # 查询数据
        cursor = self.collection.find(query)
        cursor = cursor.sort(sort_by, sort_order).skip(skip).limit(limit)
        
        logs = []
        async for log in cursor:
            log["id"] = str(log.pop("_id"))
            logs.append(log)
        
        return {
            "total": total,
            "items": logs
        }
    
    async def get_recent_logs_by_user(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取用户最近的审计日志"""
        cursor = self.collection.find({"user_id": user_id})
        cursor = cursor.sort("created_at", -1).limit(limit)
        
        logs = []
        async for log in cursor:
            log["id"] = str(log.pop("_id"))
            logs.append(log)
        
        return logs
    
    async def get_log_by_id(self, log_id: str) -> Optional[Dict[str, Any]]:
        """通过ID获取审计日志"""
        log = await self.collection.find_one({"_id": ObjectId(log_id)})
        if not log:
            return None
        
        log["id"] = str(log.pop("_id"))
        return log 