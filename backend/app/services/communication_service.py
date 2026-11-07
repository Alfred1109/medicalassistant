"""
通信服务
处理系统内消息通信、聊天对话和多端同步
"""
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
import asyncio
import logging

from app.services.notification_service import NotificationService

# 配置日志
logger = logging.getLogger(__name__)


class CommunicationService:
    """通信服务类"""

    # 统一契约基准（WS01）：时间一律使用 UTC（datetime.utcnow，与全库其余模型一致）。
    # 历史文档中的 timestamp 为服务器本地时区（datetime.now 时代写入），不做回写；
    # 消息读取/分页/离线同步一律改按 _id（ObjectId 单调，真实插入时刻有序），
    # 彻底免疫历史时区漂移，见 get_messages / sync_offline_messages。
    @staticmethod
    async def is_conversation_participant(
        db: AsyncIOMotorClient,
        conversation_id: str,
        user_id: str,
    ) -> bool:
        """校验 user_id 是否为会话参与者（WS 入房/入站与 HTTP 复用同一判定）。

        无效的 conversation_id / user_id 一律视为非成员，不抛异常，
        供 WebSocket 层在握手阶段安全调用。
        """
        if not ObjectId.is_valid(conversation_id) or not ObjectId.is_valid(user_id):
            return False
        conversation = await db.conversations.find_one({"_id": ObjectId(conversation_id)})
        if not conversation:
            return False
        return user_id in (conversation.get("participant1_id"), conversation.get("participant2_id"))

    @staticmethod
    def _format_message(message: Dict[str, Any]) -> Dict[str, Any]:
        """将 messages 集合文档格式化为对外响应（唯一真实结构：participant1/2 + read/deleted）"""
        formatted = {
            "id": str(message["_id"]),
            "conversation_id": message["conversation_id"],
            "sender_id": message["sender_id"],
            "recipient_id": message["recipient_id"],
            "content": message["content"],
            "type": message["type"],
            "timestamp": message["timestamp"].isoformat(),
            "read": message.get("read", False),
            "deleted": message.get("deleted", False),
            "attachments": message.get("attachments", []),
            "metadata": message.get("metadata", {}),
        }
        if message.get("client_message_id"):
            formatted["client_message_id"] = message["client_message_id"]
        return formatted
    
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
        
        # 创建新对话（时间统一 UTC）
        now = datetime.utcnow()
        conversation = {
            "_id": ObjectId(),
            "participant1_id": participant1_id,
            "participant2_id": participant2_id,
            "type": conversation_type,
            "status": "active",
            "created_at": now,
            "last_message_time": now,
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
        if before_id and ObjectId.is_valid(before_id):
            # 获取指定消息之前的消息（向上加载历史消息）。
            # 分页游标用消息 _id（ObjectId 单调递增，与插入时间有序一致）做 $lt
            # 比较：新写入已统一 UTC，但历史文档 timestamp 是本地时区时代写入，
            # 按 timestamp 分页在切换交界处会排序漂移；_id 永远按真实插入时刻
            # 生成，天然免疫该漂移。前端以响应里的 id 字符串回传即可。
            query["_id"] = {"$lt": ObjectId(before_id)}

        # 获取消息（按 _id 降序取最近 limit 条）
        cursor = db.messages.find(query)
        cursor = cursor.sort("_id", -1).limit(limit)
        
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
                    {"$set": {"read": True, "read_at": datetime.utcnow()}}
                )
                message["read"] = True
                message["read_at"] = datetime.utcnow().isoformat()
        
        return messages
    
    @staticmethod
    async def send_message(
        db: AsyncIOMotorClient,
        conversation_id: str,
        sender_id: str,
        content: str,
        message_type: str = "text",
        attachments: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        client_message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """发送新消息。

        client_message_id 为可选幂等键（WS01/WS03）：HTTP 与 WS 入站共用。
        同一发送者在同一会话内重复投递同一 client_message_id 时，直接返回
        既有消息（不重复落库、不重复广播）。快路径为应用层先查后插；并发
        窗口内的重复投递由 DB 层 (conversation_id, sender_id, client_message_id)
        partial unique 索引（见 app/db/indexes.py）以 DuplicateKeyError 拦截，
        捕获后重查返回既有消息，语义与快路径一致（不重复产生副作用）。
        """
        # 验证用户是否为对话参与者（HTTP/WS 共用的成员校验语义）
        conversation = await db.conversations.find_one({"_id": ObjectId(conversation_id)})
        if not conversation or (sender_id != conversation["participant1_id"] and sender_id != conversation["participant2_id"]):
            raise ValueError("用户不是对话参与者")

        # 幂等去重：重复投递返回既有消息
        if client_message_id:
            existing = await db.messages.find_one({
                "conversation_id": conversation_id,
                "sender_id": sender_id,
                "client_message_id": client_message_id,
            })
            if existing:
                return CommunicationService._format_message(existing)

        # 确定接收者ID
        recipient_id = conversation["participant1_id"] if sender_id == conversation["participant2_id"] else conversation["participant2_id"]

        # 创建消息（时间统一 UTC）
        now = datetime.utcnow()
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
        if client_message_id:
            message["client_message_id"] = client_message_id

        # 保存消息（落库成功后才允许广播——数据库失败绝不广播）。
        # DuplicateKeyError：并发投递通过了先查后插的检查窗口，被唯一索引兜底
        # 拦截——重查返回既有消息，等价于幂等快路径（不更新会话摘要、不广播、
        # 不发通知，避免重复副作用）。
        try:
            await db.messages.insert_one(message)
        except DuplicateKeyError:
            existing = await db.messages.find_one({
                "conversation_id": conversation_id,
                "sender_id": sender_id,
                "client_message_id": client_message_id,
            })
            if existing:
                return CommunicationService._format_message(existing)
            raise

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

        # 准备返回的消息格式（广播载荷与响应共用，携带真实服务端 id/时间戳）
        message_response = CommunicationService._format_message(message)
        
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
            {"$set": {"read": True, "read_at": datetime.utcnow()}}
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
            {"$set": {"read": True, "read_at": datetime.utcnow()}}
        )

        # 通过WebSocket推送消息状态更新
        if result.modified_count > 0:
            try:
                # 获取标记为已读的消息ID
                cursor = db.messages.find({
                    "conversation_id": conversation_id,
                    "recipient_id": user_id,
                    "read": True,
                    "read_at": {"$gte": datetime.utcnow().replace(microsecond=0)}  # 近似查询刚被标记为已读的消息
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
            {"$set": {"deleted": True, "deleted_at": datetime.utcnow()}}
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

        # 查询离线期间的新消息：与 get_messages 一致改按 _id 比较（ObjectId
        # 单调，from_datetime 把 last_sync_time 视为 UTC 生成游标），历史文档
        # timestamp 为本地时区时代写入，按 timestamp 比较会在切换交界处漂移。
        cursor_id = ObjectId.from_datetime(last_sync_time)
        query = {
            "conversation_id": {"$in": conversation_ids},
            "recipient_id": user_id,
            "_id": {"$gt": cursor_id}
        }

        cursor = db.messages.find(query).sort("_id", 1)
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