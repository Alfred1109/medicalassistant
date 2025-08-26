"""
通信数据模型
定义消息和对话
"""
from datetime import datetime
from bson import ObjectId
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

class Message:
    """消息模型"""
    collection_name = "messages"
    
    def __init__(
        self,
        conversation_id: str,
        sender_id: str,
        sender_type: str,  # patient, doctor, health_manager, system
        content: str,
        content_type: str = "text",  # text, image, file, etc.
        attachments: List[Dict[str, Any]] = None,
        is_read: bool = False,
        read_at: datetime = None,
        created_at: datetime = None,
        updated_at: datetime = None,
        _id: str = None,
        metadata: Dict[str, Any] = None
    ):
        self.conversation_id = conversation_id
        self.sender_id = sender_id
        self.sender_type = sender_type
        self.content = content
        self.content_type = content_type
        self.attachments = attachments or []
        self.is_read = is_read
        self.read_at = read_at
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self._id = _id or str(ObjectId())
        self.metadata = metadata or {}
    
    @classmethod
    def from_mongo(cls, mongo_doc):
        """从MongoDB文档创建消息对象"""
        if not mongo_doc:
            return None
            
        message_data = mongo_doc.copy()
        message_data["_id"] = str(message_data["_id"])
        
        return cls(**message_data)
    
    def to_mongo(self):
        """将消息对象转换为MongoDB文档"""
        doc = self.__dict__.copy()
        if doc.get("_id") and isinstance(doc["_id"], str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc
    
    def to_dict(self):
        """将消息对象转换为字典，用于API响应"""
        return self.__dict__.copy()
    
    def mark_as_read(self):
        """标记消息为已读"""
        self.is_read = True
        self.read_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def add_attachment(self, file_name: str, file_type: str, file_url: str, file_size: int = None):
        """添加附件"""
        attachment = {
            "file_name": file_name,
            "file_type": file_type,
            "file_url": file_url,
            "file_size": file_size,
            "uploaded_at": datetime.utcnow()
        }
        self.attachments.append(attachment)
        self.updated_at = datetime.utcnow()


class Conversation:
    """对话模型"""
    collection_name = "conversations"
    
    def __init__(
        self,
        title: str = None,
        participants: List[Dict[str, Any]] = None,  # 包含参与者ID和类型
        last_message: Dict[str, Any] = None,
        unread_counts: Dict[str, int] = None,  # 每个用户的未读消息数
        is_group: bool = False,
        creator_id: str = None,
        status: str = "active",  # active, archived, deleted
        created_at: datetime = None,
        updated_at: datetime = None,
        _id: str = None,
        metadata: Dict[str, Any] = None
    ):
        self.title = title
        self.participants = participants or []
        self.last_message = last_message
        self.unread_counts = unread_counts or {}
        self.is_group = is_group
        self.creator_id = creator_id
        self.status = status
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self._id = _id or str(ObjectId())
        self.metadata = metadata or {}
    
    @classmethod
    def from_mongo(cls, mongo_doc):
        """从MongoDB文档创建对话对象"""
        if not mongo_doc:
            return None
            
        conv_data = mongo_doc.copy()
        conv_data["_id"] = str(conv_data["_id"])
        
        return cls(**conv_data)
    
    def to_mongo(self):
        """将对话对象转换为MongoDB文档"""
        doc = self.__dict__.copy()
        if doc.get("_id") and isinstance(doc["_id"], str):
            doc["_id"] = ObjectId(doc["_id"])
        return doc
    
    def to_dict(self):
        """将对话对象转换为字典，用于API响应"""
        return self.__dict__.copy()
    
    def add_participant(self, user_id: str, user_type: str):
        """添加参与者"""
        participant = {
            "user_id": user_id,
            "user_type": user_type,
            "joined_at": datetime.utcnow()
        }
        self.participants.append(participant)
        self.unread_counts[user_id] = 0
        self.updated_at = datetime.utcnow()
    
    def remove_participant(self, user_id: str):
        """移除参与者"""
        self.participants = [p for p in self.participants if p["user_id"] != user_id]
        if user_id in self.unread_counts:
            del self.unread_counts[user_id]
        self.updated_at = datetime.utcnow()
    
    def update_last_message(self, message: Message):
        """更新最后一条消息"""
        self.last_message = {
            "message_id": message._id,
            "sender_id": message.sender_id,
            "sender_type": message.sender_type,
            "content": message.content,
            "content_type": message.content_type,
            "created_at": message.created_at
        }
        
        # 更新未读计数
        for participant in self.participants:
            user_id = participant["user_id"]
            if user_id != message.sender_id:
                self.unread_counts[user_id] = self.unread_counts.get(user_id, 0) + 1
                
        self.updated_at = datetime.utcnow()
    
    def mark_as_read_for_user(self, user_id: str):
        """为指定用户标记对话为已读"""
        self.unread_counts[user_id] = 0
        self.updated_at = datetime.utcnow()
    
    def archive(self):
        """归档对话"""
        self.status = "archived"
        self.updated_at = datetime.utcnow()
    
    def activate(self):
        """激活对话"""
        self.status = "active"
        self.updated_at = datetime.utcnow()

# 通知模型
class Notification(BaseModel):
    id: str = Field(default_factory=lambda: str(ObjectId()))
    title: str
    content: str
    sender_id: str  # 发送者ID
    sender_name: str  # 发送者名称
    sender_role: str  # 发送者角色
    recipient_id: str  # 接收者ID
    time: datetime = Field(default_factory=datetime.now)
    read: bool = False
    notification_type: str = "general"  # 通知类型：general, medical, appointment, system
    priority: str = "normal"  # 优先级：low, normal, high, urgent
    related_entity_id: Optional[str] = None  # 相关实体ID（如预约ID、健康记录ID等）
    related_entity_type: Optional[str] = None  # 相关实体类型
    
    class Config:
        schema_extra = {
            "example": {
                "id": "60d21b4967d0d8992e610c85",
                "title": "康复计划已更新",
                "content": "您的康复计划已由张医生更新，请查看最新内容。",
                "sender_id": "60d21b4967d0d8992e610c82",
                "sender_name": "张医生",
                "sender_role": "doctor",
                "recipient_id": "60d21b4967d0d8992e610c83",
                "time": "2023-08-15T14:30:00.000Z",
                "read": False,
                "notification_type": "medical",
                "priority": "high",
                "related_entity_id": "60d21b4967d0d8992e610c84",
                "related_entity_type": "rehabilitation_plan"
            }
        } 