"""
通信数据模型（WS01 统一后）

消息与会话不再使用模型类结构（原 Message/Conversation 双 schema 已删除）：
唯一真实结构为 CommunicationService 的隐式 schema
（conversations: participant1_id/participant2_id；
 messages: recipient_id/read/deleted，时间统一 UTC，可选 client_message_id 幂等键），
见 backend/app/services/communication_service.py。

本文件仅保留仍在被 notification_router.py 引用的 Notification Pydantic 模型。
"""
from datetime import datetime
from bson import ObjectId
from typing import Optional
from pydantic import BaseModel, Field

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
