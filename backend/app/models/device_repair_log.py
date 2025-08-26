"""
设备修复日志模型
用于记录设备修复操作的历史和结果
"""
from datetime import datetime
from bson import ObjectId
from typing import Dict, List, Optional, Any

class DeviceRepairLog:
    """设备修复日志模型"""
    collection_name = "device_repair_logs"
    
    def __init__(
        self,
        device_id: str,  # 设备ID
        device_type: str,  # 设备类型
        repair_time: datetime,  # 修复时间
        initial_status: Dict[str, Any],  # 修复前的状态
        repair_actions: List[str],  # 执行的修复动作
        repair_results: List[Dict[str, Any]],  # 修复结果详情
        overall_success: bool,  # 整体修复是否成功
        performed_by: Optional[str] = None,  # 执行修复的用户ID
        notes: Optional[str] = None,  # 备注信息
        created_at: Optional[datetime] = None,
        _id: Optional[str] = None
    ):
        self.device_id = device_id
        self.device_type = device_type
        self.repair_time = repair_time
        self.initial_status = initial_status
        self.repair_actions = repair_actions
        self.repair_results = repair_results
        self.overall_success = overall_success
        self.performed_by = performed_by
        self.notes = notes
        self.created_at = created_at or datetime.utcnow()
        self._id = _id or str(ObjectId())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DeviceRepairLog':
        """从字典创建设备修复日志对象"""
        if not data:
            return None
            
        return cls(
            device_id=data.get("device_id"),
            device_type=data.get("device_type"),
            repair_time=data.get("repair_time"),
            initial_status=data.get("initial_status", {}),
            repair_actions=data.get("repair_actions", []),
            repair_results=data.get("repair_results", []),
            overall_success=data.get("overall_success", False),
            performed_by=data.get("performed_by"),
            notes=data.get("notes"),
            created_at=data.get("created_at"),
            _id=str(data.get("_id")) if data.get("_id") else None
        )
    
    @classmethod
    def from_mongo(cls, mongo_doc: Dict[str, Any]) -> Optional['DeviceRepairLog']:
        """从MongoDB文档创建设备修复日志对象"""
        if not mongo_doc:
            return None
            
        data = mongo_doc.copy()
        if "_id" in data:
            data["_id"] = str(data["_id"])
        
        return cls.from_dict(data)
    
    def to_mongo(self) -> Dict[str, Any]:
        """将设备修复日志对象转换为MongoDB文档"""
        doc = self.__dict__.copy()
        if doc.get("_id") and isinstance(doc["_id"], str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc
    
    def to_dict(self) -> Dict[str, Any]:
        """将设备修复日志对象转换为字典，用于API响应"""
        result = self.__dict__.copy()
        # 将时间转换为ISO格式字符串
        if isinstance(result.get("repair_time"), datetime):
            result["repair_time"] = result["repair_time"].isoformat()
        if isinstance(result.get("created_at"), datetime):
            result["created_at"] = result["created_at"].isoformat()
        return result 