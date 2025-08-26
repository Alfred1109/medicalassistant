from datetime import datetime
from typing import Optional, Dict, Any

class AuditLog:
    """
    审计日志模型，用于记录系统中的权限相关操作
    """
    def __init__(
        self,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        status: str = "success",
        created_at: Optional[datetime] = None,
    ):
        self.user_id = user_id
        self.action = action  # 操作类型: 'login', 'logout', 'access', 'modify', 'grant', 'revoke'
        self.resource_type = resource_type  # 资源类型: 'permission', 'role', 'user', 等
        self.resource_id = resource_id
        self.details = details or {}  # 详细信息
        self.ip_address = ip_address
        self.status = status  # 'success' or 'failure'
        self.created_at = created_at or datetime.utcnow()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AuditLog':
        """从字典创建审计日志对象"""
        created_at = data.get('created_at')
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        
        return cls(
            user_id=data.get('user_id'),
            action=data.get('action'),
            resource_type=data.get('resource_type'),
            resource_id=data.get('resource_id'),
            details=data.get('details'),
            ip_address=data.get('ip_address'),
            status=data.get('status', 'success'),
            created_at=created_at,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """将审计日志对象转换为字典"""
        return {
            'user_id': self.user_id,
            'action': self.action,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'details': self.details,
            'ip_address': self.ip_address,
            'status': self.status,
            'created_at': self.created_at.isoformat(),
        } 