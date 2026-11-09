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
from app.services.conversation_policy import (
    ConversationPolicy,
    REASON_ACCOUNT_INVALID,
    participant_ids,
)

# 配置日志
logger = logging.getLogger(__name__)

# 通信索引惰性初始化状态（进程级）：普通启动不隐式建集合（启动边界契约），
# 首个消息落库隐式创建 messages 集合后，补建幂等唯一索引（见 send_message）。
_index_state = {"ensured": False}


async def _ensure_indexes_after_first_persist(db) -> None:
    """首个消息落库（隐式建集合）后惰性补建通信索引，每进程最多尝试一次。"""
    if _index_state["ensured"]:
        return
    _index_state["ensured"] = True
    try:
        from app.db.indexes import ensure_communication_indexes
        await ensure_communication_indexes(db)
    except Exception as e:
        # 索引补建失败不阻断消息落库：幂等去重退化为应用层先查后插。
        logger.warning("通信索引惰性初始化失败，幂等去重退化为应用层查重: %s", e)


class CommunicationService:
    """通信服务类"""

    # 统一契约基准（WS01）：时间一律使用 UTC（datetime.utcnow，与全库其余模型一致）。
    # 历史文档中的 timestamp 为服务器本地时区（datetime.now 时代写入），不做回写；
    # 消息读取/分页/离线同步一律改按 _id（ObjectId 单调，真实插入时刻有序），
    # 彻底免疫历史时区漂移，见 get_messages / sync_offline_messages。
    @staticmethod
    def _server_seq(oid: ObjectId) -> int:
        """D7 事件信封 server_seq：ObjectId 12 字节大端整数。

        复用 _id 单调游标基建（ObjectId 按生成时刻单调递增）：插入型事件
        （message）取落库文档 _id（重放稳定）；非插入型事件（read_receipt /
        delete_message）取发射时刻新生 ObjectId（同进程内单调）。跨 worker
        全序属 D11/WS04 范畴。
        """
        return int.from_bytes(oid.binary, "big")

    @staticmethod
    async def is_conversation_participant(
        db: AsyncIOMotorClient,
        conversation_id: str,
        user_id: str,
    ) -> bool:
        """校验 user_id 是否为会话参与者（WS 入房/入站与 HTTP 复用同一判定）。

        无效的 conversation_id / user_id 一律视为非成员，不抛异常，
        供 WebSocket 层在握手阶段安全调用。
        成员判定统一走 ConversationPolicy 的成员层（D1 兼容读两种成员形态）。
        """
        if not ObjectId.is_valid(conversation_id) or not ObjectId.is_valid(user_id):
            return False
        conversation = await db.conversations.find_one({"_id": ObjectId(conversation_id)})
        if not conversation:
            return False
        return user_id in participant_ids(conversation)

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
        # ConversationPolicy（D3，默认采纳待评审追认 2026-11-09）：
        # 出站读与入房/入站同一规则——有效账号 + 会话参与者。
        decision = await ConversationPolicy.authorize(
            db, conversation_id, user_id, layer="outbound")
        if not decision.allowed or decision.conversation is None:
            return None
        conversation = decision.conversation

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
        conversation_id = str(result.inserted_id)

        # 真实业务事件触发点：新会话建立 → 通知受邀参与者（participant2）。
        # 通知失败不影响会话创建（notification_service 内部已兜底 WS 推送失败）。
        try:
            sender = await db.users.find_one({"_id": ObjectId(participant1_id)})
            await NotificationService.create_notification(
                db=db,
                title="新会话",
                content=f"{(sender or {}).get('name', 'Unknown')} 发起了沟通会话，可以开始交流。",
                sender_id=participant1_id,
                sender_name=(sender or {}).get("name", "Unknown"),
                sender_role=(sender or {}).get("role", "unknown"),
                recipient_id=participant2_id,
                notification_type="message",
                priority="normal",
                related_entity_id=conversation_id,
                related_entity_type="conversation"
            )
        except Exception as e:
            logger.warning(f"新会话通知创建失败: {str(e)}")

        return conversation_id

    @staticmethod
    async def get_messages(
        db: AsyncIOMotorClient,
        conversation_id: str,
        user_id: str,
        limit: int = 50,
        before_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取对话中的消息"""
        # ConversationPolicy（D3）：出站读与入房/入站同一规则
        decision = await ConversationPolicy.authorize(
            db, conversation_id, user_id, layer="outbound")
        if not decision.allowed:
            return []

        # 构建查询
        # D6 删除语义（默认采纳待评审追认 2026-11-09）：软删除消息对双方
        # 会话内不可见（$ne True 兼容无 deleted 字段的历史文档）。
        query = {"conversation_id": conversation_id, "deleted": {"$ne": True}}
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
        
        # 保留读取即已读行为，并复用显式标读的授权、落库和事件路径。
        incoming_ids = [str(message["_id"]) for message in messages
                        if message.get("recipient_id") == user_id and not message.get("read", False)]
        if incoming_ids:
            await CommunicationService._mark_messages_as_read(db, conversation_id, user_id, incoming_ids)
            refreshed = {str(doc["_id"]): doc async for doc in db.messages.find(
                {"_id": {"$in": [ObjectId(mid) for mid in incoming_ids]}})}
            messages = [refreshed.get(str(message["_id"]), message) for message in messages]

        for message in messages:
            message["id"] = str(message.pop("_id"))
            message["timestamp"] = message["timestamp"].isoformat()
            if isinstance(message.get("read_at"), datetime):
                message["read_at"] = message["read_at"].isoformat()

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
        # ConversationPolicy（D3，默认采纳待评审追认 2026-11-09）：
        # HTTP/WS 入站共用同一校验语义——有效账号 + 会话参与者。
        # 账号停用（连接期内撤权）与非成员均拒绝；WS 层把 ValueError
        # 统一映射为 NOT_CONVERSATION_PARTICIPANT + 4403 断连。
        decision = await ConversationPolicy.authorize(
            db, conversation_id, sender_id, layer="inbound")
        if not decision.allowed or decision.conversation is None:
            if decision.reason == REASON_ACCOUNT_INVALID:
                raise ValueError("发送者账号不可用")
            raise ValueError("用户不是对话参与者")
        conversation = decision.conversation

        # 幂等去重：重复投递返回既有消息
        if client_message_id:
            existing = await db.messages.find_one({
                "conversation_id": conversation_id,
                "sender_id": sender_id,
                "client_message_id": client_message_id,
            })
            if existing:
                return CommunicationService._format_message(existing)

        # 确定接收者ID（D1 兼容读：participants 数组形态取另一成员；
        # 现行写入仍为双人单聊形态，群聊写入未启用，迁移属 WS01-c）
        other_members = [member for member in participant_ids(conversation) if member != sender_id]
        recipient_id = other_members[0] if other_members else None

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
            # 首个消息落库隐式创建 messages 集合 → 惰性补建幂等唯一索引
            # （普通启动不隐式建集合，见 app/db/indexes.py）。
            await _ensure_indexes_after_first_persist(db)
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
            
            # 向聊天室发送消息（D7：事件信封携带 server_seq，
            # 取落库文档 _id 的大端整数——重放稳定且与插入顺序单调）
            await manager.send_chat_message(
                {
                    "type": "message",
                    "message": message_response,
                    "server_seq": CommunicationService._server_seq(message["_id"]),
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
    async def _mark_messages_as_read(
        db: AsyncIOMotorClient,
        conversation_id: str,
        user_id: str,
        message_ids: Optional[List[str]] = None,
    ) -> int:
        """所有已读入口的统一授权、持久化与事件路径。"""
        # ConversationPolicy（D3）：出站写与入房/入站同一规则
        decision = await ConversationPolicy.authorize(
            db, conversation_id, user_id, layer="outbound")
        if not decision.allowed:
            raise ValueError("用户不是该会话参与者")
        unread_filter = {
            "conversation_id": conversation_id,
            "recipient_id": user_id,
            "read": False,
        }
        if message_ids is not None:
            unread_filter["_id"] = {"$in": [ObjectId(mid) for mid in message_ids]}
        marked_ids = [doc["_id"] async for doc in db.messages.find(unread_filter)]
        if not marked_ids:
            return 0
        now = datetime.utcnow()
        result = await db.messages.update_many(
            {**unread_filter, "_id": {"$in": marked_ids}},
            {"$set": {"read": True, "read_at": now}},
        )
        if result.modified_count == 0:
            return 0
        # 精确取回本次写入，排除被并发请求先标读的文档。
        persisted_ids = [str(doc["_id"]) async for doc in db.messages.find({
            "_id": {"$in": marked_ids}, "read": True, "read_at": now,
        })]
        if persisted_ids:
            try:
                from app.api.websockets import get_connection_manager
                await get_connection_manager().send_chat_message({
                    "type": "read_receipt",
                    "conversation_id": conversation_id,
                    "reader_id": user_id,
                    "message_ids": persisted_ids,
                    "read_at": now.isoformat(),
                    # D7：非插入型事件用发射时刻新生 ObjectId 的单调整数
                    "server_seq": CommunicationService._server_seq(ObjectId()),
                }, conversation_id)
            except Exception as e:
                logger.warning(f"推送已读状态失败: {str(e)}")
        return result.modified_count

    @staticmethod
    async def mark_message_as_read(db: AsyncIOMotorClient, message_id: str, user_id: str) -> bool:
        """接收者且仍为会话成员才能标读；重试保留首次已读时间。"""
        if not ObjectId.is_valid(message_id):
            return False
        message = await db.messages.find_one({"_id": ObjectId(message_id), "recipient_id": user_id})
        if not message:
            return False
        await CommunicationService._mark_messages_as_read(
            db, message["conversation_id"], user_id, [message_id])
        return True

    @staticmethod
    async def mark_conversation_as_read(db: AsyncIOMotorClient, conversation_id: str, user_id: str) -> int:
        """标记会话中发给当前成员的未读消息；返回实际修改数量。"""
        return await CommunicationService._mark_messages_as_read(db, conversation_id, user_id)

    @staticmethod
    async def delete_message(
        db: AsyncIOMotorClient,
        message_id: str,
        user_id: str
    ) -> bool:
        """删除消息（D6 冻结语义：软删除，默认采纳待评审追认 2026-11-09）。

        会话任一参与者均可软删除（发送者撤回 / 接收者删除）：
        - 双方会话内不可见：get_messages / sync_offline_messages 过滤已删文档；
        - 不硬删：文档原样保留 content 等原始字段，附 deleted / deleted_at /
          deleted_by 审计字段，原文按 id 引用仍可解析（引用完整性不破坏）。
        """
        if not ObjectId.is_valid(message_id):
            return False
        message = await db.messages.find_one({
            "_id": ObjectId(message_id),
            "deleted": {"$ne": True},  # 已删除消息不可重复删除
        })

        if not message:
            return False

        # ConversationPolicy（D3）：删除是入站写，须为有效账号 + 会话参与者
        decision = await ConversationPolicy.authorize(
            db, message["conversation_id"], user_id, layer="inbound")
        if not decision.allowed:
            return False

        result = await db.messages.update_one(
            {"_id": ObjectId(message_id), "deleted": {"$ne": True}},
            {"$set": {
                "deleted": True,
                "deleted_at": datetime.utcnow(),
                "deleted_by": user_id,
            }}
        )

        # 通过WebSocket推送消息删除通知（D7：信封携带 server_seq）
        if result.modified_count > 0:
            try:
                from app.api.websockets import get_connection_manager
                manager = get_connection_manager()

                # 发送消息删除通知
                await manager.send_chat_message(
                    {
                        "type": "delete_message",
                        "message_id": message_id,
                        "user_id": user_id,
                        "server_seq": CommunicationService._server_seq(ObjectId()),
                    },
                    message["conversation_id"]
                )
            except Exception as e:
                logger.warning(f"推送消息删除通知失败: {str(e)}")

        # 真实业务事件触发点：消息撤回（软删除）→ 通知对话另一方。
        # 通知失败不影响删除本身。
        if result.modified_count > 0:
            try:
                conversation = await db.conversations.find_one(
                    {"_id": ObjectId(message["conversation_id"])}
                )
                if conversation:
                    other_id = (
                        conversation["participant2_id"]
                        if user_id == conversation["participant1_id"]
                        else conversation["participant1_id"]
                    )
                    sender = await db.users.find_one({"_id": ObjectId(user_id)})
                    await NotificationService.create_notification(
                        db=db,
                        title="消息已撤回",
                        content=f"{(sender or {}).get('name', '对方')} 撤回了一条消息。",
                        sender_id=user_id,
                        sender_name=(sender or {}).get("name", "Unknown"),
                        sender_role=(sender or {}).get("role", "unknown"),
                        recipient_id=str(other_id),
                        notification_type="message",
                        priority="low",
                        related_entity_id=str(message["conversation_id"]),
                        related_entity_type="conversation"
                    )
            except Exception as e:
                logger.warning(f"撤回通知创建失败: {str(e)}")

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
        # D6：软删除消息对双方不可见，离线同步同样过滤（$ne True 兼容历史文档）
        query = {
            "conversation_id": {"$in": conversation_ids},
            "recipient_id": user_id,
            "_id": {"$gt": cursor_id},
            "deleted": {"$ne": True}
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