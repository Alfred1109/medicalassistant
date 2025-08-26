"""
组织机构数据模型
定义医疗机构及其多层级结构
"""
from datetime import datetime
from bson import ObjectId
from typing import Dict, List, Optional, Any

class Organization:
    """组织机构模型，支持多层级结构"""
    collection_name = "organizations"
    
    def __init__(
        self,
        name: str,
        description: str = None,
        type: str = "hospital",  # hospital, clinic, rehabilitation_center, etc.
        address: Dict[str, Any] = None,
        contact_info: Dict[str, Any] = None,
        parent_id: str = None,
        admin_ids: List[str] = None,
        tags: List[str] = None,
        active: bool = True,
        created_at: datetime = None,
        updated_at: datetime = None,
        _id: str = None,
        metadata: Dict[str, Any] = None
    ):
        self.name = name
        self.description = description or ""
        self.type = type
        self.address = address or {}
        self.contact_info = contact_info or {}
        self.parent_id = parent_id
        self.admin_ids = admin_ids or []
        self.tags = tags or []
        self.active = active
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self._id = _id or str(ObjectId())
        self.metadata = metadata or {}
        
    @classmethod
    def from_mongo(cls, mongo_doc):
        """从MongoDB文档创建组织对象"""
        if not mongo_doc:
            return None
            
        org_data = mongo_doc.copy()
        org_data["_id"] = str(org_data["_id"])
        
        return cls(**org_data)
        
    def to_mongo(self):
        """将组织对象转换为MongoDB文档"""
        doc = self.__dict__.copy()
        if doc.get("_id") and isinstance(doc["_id"], str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc
        
    def to_dict(self):
        """将组织对象转换为字典，用于API响应"""
        return self.__dict__.copy()
        
    def add_admin(self, admin_id: str):
        """添加管理员"""
        if admin_id not in self.admin_ids:
            self.admin_ids.append(admin_id)
            self.updated_at = datetime.utcnow()
            
    def remove_admin(self, admin_id: str):
        """移除管理员"""
        if admin_id in self.admin_ids:
            self.admin_ids.remove(admin_id)
            self.updated_at = datetime.utcnow()
            
    def add_tag(self, tag: str):
        """添加标签"""
        if tag not in self.tags:
            self.tags.append(tag)
            self.updated_at = datetime.utcnow()
            
    def remove_tag(self, tag: str):
        """移除标签"""
        if tag in self.tags:
            self.tags.remove(tag)
            self.updated_at = datetime.utcnow()
    
    def update_info(self, **kwargs):
        """更新组织信息"""
        for key, value in kwargs.items():
            if hasattr(self, key) and key not in ["_id", "created_at"]:
                setattr(self, key, value)
        self.updated_at = datetime.utcnow() 