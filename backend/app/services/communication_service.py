"""
通信服务
处理系统内消息通信、聊天对话和多端同步
"""
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import asyncio
import logging
import json

from app.services.notification_service import NotificationService

# 配置日志
logger = logging.getLogger(__name__)

class CommunicationService:
    """通信服务类"""
    
    @staticmethod
    async def get_conversations(
        db: AsyncIOMotorClient,
        user_id: str,
        limit: int = 20,
        skip: int = 0,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取用户的对话列表"""
        query = {
            "$or": [
                {"participant1_id": user_id},
                {"participant2_id": user_id}
            ]
        }
        
        if status:
            query["status"] = status
        
        cursor = db.conversations.find(query)
        cursor = cursor.sort("last_message_time", -1).skip(skip).limit(limit)
        
        conversations = await cursor.to_list(length=limit)
        for conversation in conversations:
            conversation["id"] = str(conversation["_id"])
            del conversation["_id"]
            
            # 添加未读消息数量
            if conversation["participant1_id"] == user_id:
                other_user_id = conversation["participant2_id"]
                conversation["unread_count"] = await CommunicationService.get_unread_messages_count(
                    db, conversation["id"], user_id
                )
            else:
                other_user_id = conversation["participant1_id"]
                conversation["unread_count"] = await CommunicationService.get_unread_messages_count(
                    db, conversation["id"], user_id
                )
            
            # 获取对话对象的基本信息
            other_user = await db.users.find_one({"_id": ObjectId(other_user_id)})
            if other_user:
                conversation["other_user"] = {
                    "id": str(other_user["_id"]),
                    "name": other_user.get("name", "Unknown"),
                    "role": other_user.get("role", "unknown"),
                    "avatar": other_user.get("avatar", None),
                }
        
        return conversations
    
    @staticmethod
    async def get_conversation(
        db: AsyncIOMotorClient,
        conversation_id: str,
        user_id: str,
    ) -> Optional[Dict[str, Any]]:
        """获取特定对话详情"""
        conversation = await db.conversations.find_one({"_id": ObjectId(conversation_id)})
        
        if not conversation:
            return None
        
        # 验证用户是否为对话参与者
        if user_id != conversation["participant1_id"] and user_id != conversation["participant2_id"]:
            return None
        
        conversation["id"] = str(conversation["_id"])
        del conversation["_id"]
        
        # 获取对话参与者信息
        participant1 = await db.users.find_one({"_id": ObjectId(conversation["participant1_id"])})
        participant2 = await db.users.find_one({"_id": ObjectId(conversation["participant2_id"])})
        
        if participant1:
            conversation["participant1"] = {
                "id": str(participant1["_id"]),
                "name": participant1.get("name", "Unknown"),
                "role": participant1.get("role", "unknown"),
                "avatar": participant1.get("avatar", None),
            }
        
        if participant2:
            conversation["participant2"] = {
                "id": str(participant2["_id"]),
                "name": participant2.get("name", "Unknown"),
                "role": participant2.get("role", "unknown"),
                "avatar": participant2.get("avatar", None),
            }
        
        # 添加未读消息数量
        conversation["unread_count"] = await CommunicationService.get_unread_messages_count(
            db, conversation["id"], user_id
        )
        
        return conversation
    
    @staticmethod
    async def create_conversation(
        db: AsyncIOMotorClient,
        participant1_id: str,
        participant2_id: str,
        conversation_type: str = "chat"
    ) -> str:
        """创建新对话"""
        # 检查是否已存在相同参与者的对话
        existing = await db.conversations.find_one({
            "$or": [
                {
                    "participant1_id": participant1_id,
                    "participant2_id": participant2_id
                },
                {
                    "participant1_id": participant2_id,
                    "participant2_id": participant1_id
                }
            ],
            "type": conversation_type
        })
        
        if existing:
            return str(existing["_id"])
        
        # 创建新对话
        conversation = {
            "_id": ObjectId(),
            "participant1_id": participant1_id,
            "participant2_id": participant2_id,
            "type": conversation_type,
            "status": "active",
            "created_at": datetime.now(),
            "last_message_time": datetime.now(),
            "last_message_preview": "",
            "metadata": {}
        }
        
        result = await db.conversations.insert_one(conversation)
        return str(result.inserted_id)
    
    @staticmethod
    async def get_messages(
        db: AsyncIOMotorClient,
        conversation_id: str,
        user_id: str,
        limit: int = 50,
        before_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取对话中的消息"""
        # 验证用户是否为对话参与者
        conversation = await db.conversations.find_one({"_id": ObjectId(conversation_id)})
        if not conversation or (user_id != conversation["participant1_id"] and user_id != conversation["participant2_id"]):
            return []
        
        # 构建查询
        query = {"conversation_id": conversation_id}
        if before_id:
            # 获取指定消息之前的消息（向上加载历史消息）
            before_message = await db.messages.find_one({"_id": ObjectId(before_id)})
            if before_message:
                query["timestamp"] = {"$lt": before_message["timestamp"]}
        
        # 获取消息
        cursor = db.messages.find(query)
        cursor = cursor.sort("timestamp", -1).limit(limit)
        
        messages = await cursor.to_list(length=limit)
        messages.reverse()  # 将消息按时间正序排列
        
        # 格式化消息
        for message in messages:
            message["id"] = str(message["_id"])
            del message["_id"]
            message["timestamp"] = message["timestamp"].isoformat()
            
            # 如果消息发送者不是当前用户，标记为已读
            if message["sender_id"] != user_id and not message.get("read", False):
                await db.messages.update_one(
                    {"_id": ObjectId(message["id"])},
                    {"$set": {"read": True, "read_at": datetime.now()}}
                )
                message["read"] = True
                message["read_at"] = datetime.now().isoformat()
        
        return messages
    
    @staticmethod
    async def send_message(
        db: AsyncIOMotorClient,
        conversation_id: str,
        sender_id: str,
        content: str,
        message_type: str = "text",
        attachments: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """发送新消息"""
        # 验证用户是否为对话参与者
        conversation = await db.conversations.find_one({"_id": ObjectId(conversation_id)})
        if not conversation or (sender_id != conversation["participant1_id"] and sender_id != conversation["participant2_id"]):
            raise ValueError("用户不是对话参与者")
        
        # 确定接收者ID
        recipient_id = conversation["participant1_id"] if sender_id == conversation["participant2_id"] else conversation["participant2_id"]
        
        # 创建消息
        now = datetime.now()
        message = {
            "_id": ObjectId(),
            "conversation_id": conversation_id,
            "sender_id": sender_id,
            "recipient_id": recipient_id,
            "content": content,
            "type": message_type,
            "timestamp": now,
            "read": False,
            "deleted": False,
            "attachments": attachments or [],
            "metadata": metadata or {}
        }
        
        # 保存消息
        await db.messages.insert_one(message)
        
        # 更新对话最后消息信息
        await db.conversations.update_one(
            {"_id": ObjectId(conversation_id)},
            {
                "$set": {
                    "last_message_time": now,
                    "last_message_preview": content[:50] + ("..." if len(content) > 50 else "")
                }
            }
        )
        
        # 准备返回的消息格式
        message_response = {
            "id": str(message["_id"]),
            "conversation_id": message["conversation_id"],
            "sender_id": message["sender_id"],
            "recipient_id": message["recipient_id"],
            "content": message["content"],
            "type": message["type"],
            "timestamp": message["timestamp"].isoformat(),
            "read": message["read"],
            "deleted": message["deleted"],
            "attachments": message["attachments"],
            "metadata": message["metadata"]
        }
        
        # 通过WebSocket推送消息（如果有连接管理器）
        try:
            from app.api.websockets import get_connection_manager
            manager = get_connection_manager()
            
            # 向聊天室发送消息
            await manager.send_chat_message(
                {
                    "type": "message",
                    "message": message_response
                },
                conversation_id
            )
            
            # 如果接收者不在线，发送通知
            active_users = manager.get_active_users_in_chat(conversation_id)
            if recipient_id not in active_users:
                # 获取发送者信息
                sender = await db.users.find_one({"_id": ObjectId(sender_id)})
                
                if sender:
                    # 创建通知
                    await NotificationService.create_notification(
                        db=db,
                        title="新消息",
                        content=f"{sender.get('name', 'Unknown')} 发送了新消息: {content[:30]}...",
                        sender_id=sender_id,
                        sender_name=sender.get("name", "Unknown"),
                        sender_role=sender.get("role", "unknown"),
                        recipient_id=recipient_id,
                        notification_type="message",
                        priority="normal",
                        related_entity_id=conversation_id,
                        related_entity_type="conversation"
                    )
        except Exception as e:
            logger.warning(f"通过WebSocket推送消息失败: {str(e)}")
        
        return message_response
    
    @staticmethod
    async def get_unread_messages_count(
        db: AsyncIOMotorClient,
        conversation_id: str,
        user_id: str
    ) -> int:
        """获取指定对话中用户未读消息数量"""
        count = await db.messages.count_documents({
            "conversation_id": conversation_id,
            "recipient_id": user_id,
            "read": False,
            "deleted": False
        })
        return count
    
    @staticmethod
    async def get_total_unread_messages_count(
        db: AsyncIOMotorClient,
        user_id: str
    ) -> int:
        """获取用户所有对话的未读消息总数"""
        count = await db.messages.count_documents({
            "recipient_id": user_id,
            "read": False,
            "deleted": False
        })
        return count
    
    @staticmethod
    async def mark_message_as_read(
        db: AsyncIOMotorClient,
        message_id: str,
        user_id: str
    ) -> bool:
        """将消息标记为已读"""
        message = await db.messages.find_one({
            "_id": ObjectId(message_id),
            "recipient_id": user_id
        })
        
        if not message:
            return False
        
        result = await db.messages.update_one(
            {"_id": ObjectId(message_id)},
            {"$set": {"read": True, "read_at": datetime.now()}}
        )
        
        # 通过WebSocket推送消息状态更新
        if result.modified_count > 0:
            try:
                from app.api.websockets import get_connection_manager
                manager = get_connection_manager()
                
                # 发送消息状态更新
                await manager.send_chat_message(
                    {
                        "type": "read_receipt",
                        "user_id": user_id,
                        "message_ids": [message_id]
                    },
                    message["conversation_id"]
                )
            except Exception as e:
                logger.warning(f"推送消息已读状态失败: {str(e)}")
        
        return result.modified_count > 0
    
    @staticmethod
    async def mark_conversation_as_read(
        db: AsyncIOMotorClient,
        conversation_id: str,
        user_id: str
    ) -> int:
        """将对话中所有消息标记为已读"""
        result = await db.messages.update_many(
            {
                "conversation_id": conversation_id,
                "recipient_id": user_id,
                "read": False
            },
            {"$set": {"read": True, "read_at": datetime.now()}}
        )
        
        # 通过WebSocket推送消息状态更新
        if result.modified_count > 0:
            try:
                # 获取标记为已读的消息ID
                cursor = db.messages.find({
                    "conversation_id": conversation_id,
                    "recipient_id": user_id,
                    "read": True,
                    "read_at": {"$gte": datetime.now().replace(microsecond=0)}  # 近似查询刚被标记为已读的消息
                })
                
                message_ids = []
                async for message in cursor:
                    message_ids.append(str(message["_id"]))
                
                if message_ids:
                    from app.api.websockets import get_connection_manager
                    manager = get_connection_manager()
                    
                    # 发送消息状态更新
                    await manager.send_chat_message(
                        {
                            "type": "read_receipt",
                            "user_id": user_id,
                            "message_ids": message_ids
                        },
                        conversation_id
                    )
            except Exception as e:
                logger.warning(f"推送对话已读状态失败: {str(e)}")
        
        return result.modified_count
    
    @staticmethod
    async def delete_message(
        db: AsyncIOMotorClient,
        message_id: str,
        user_id: str
    ) -> bool:
        """删除消息（软删除）"""
        message = await db.messages.find_one({
            "_id": ObjectId(message_id),
            "sender_id": user_id  # 只允许发送者删除
        })
        
        if not message:
            return False
        
        result = await db.messages.update_one(
            {"_id": ObjectId(message_id)},
            {"$set": {"deleted": True, "deleted_at": datetime.now()}}
        )
        
        # 通过WebSocket推送消息删除通知
        if result.modified_count > 0:
            try:
                from app.api.websockets import get_connection_manager
                manager = get_connection_manager()
                
                # 发送消息删除通知
                await manager.send_chat_message(
                    {
                        "type": "delete_message",
                        "message_id": message_id,
                        "user_id": user_id
                    },
                    message["conversation_id"]
                )
            except Exception as e:
                logger.warning(f"推送消息删除通知失败: {str(e)}")
        
        return result.modified_count > 0
    
    @staticmethod
    async def sync_offline_messages(
        db: AsyncIOMotorClient,
        user_id: str,
        last_sync_time: datetime
    ) -> List[Dict[str, Any]]:
        """同步用户离线期间的新消息"""
        # 查找用户参与的所有对话
        conversations = await db.conversations.find({
            "$or": [
                {"participant1_id": user_id},
                {"participant2_id": user_id}
            ]
        }).to_list(length=100)  # 限制同步的对话数量
        
        conversation_ids = [str(conv["_id"]) for conv in conversations]
        
        # 查询离线期间的新消息
        query = {
            "conversation_id": {"$in": conversation_ids},
            "recipient_id": user_id,
            "timestamp": {"$gt": last_sync_time}
        }
        
        cursor = db.messages.find(query).sort("timestamp", 1)
        offline_messages = await cursor.to_list(length=1000)  # 限制同步的消息数量
        
        # 格式化消息
        messages = []
        for message in offline_messages:
            messages.append({
                "id": str(message["_id"]),
                "conversation_id": message["conversation_id"],
                "sender_id": message["sender_id"],
                "recipient_id": message["recipient_id"],
                "content": message["content"],
                "type": message["type"],
                "timestamp": message["timestamp"].isoformat(),
                "read": message["read"],
                "deleted": message["deleted"],
                "attachments": message["attachments"],
                "metadata": message["metadata"]
            })
        
        return messages 