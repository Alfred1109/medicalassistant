from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from typing import Dict, List, Any, Optional, Set
import json
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import logging

from app.core.auth import get_current_user_ws
from app.core.config import settings
from app.integrations.identity.access import unified_authentication
from app.db.mongodb import get_database, db as mongodb_state
from app.api.ws_event_bus import (
    bus_enabled,
    publish_event,
    remove_presence,
    start_event_bus,
    stop_event_bus,
    upsert_presence,
)
from app.models.user import User
from app.services.communication_service import CommunicationService
from app.services.notification_service import NotificationService

# 配置日志
logger = logging.getLogger(__name__)
IDENTITY_RECHECK_SECONDS = 5


async def receive_authorized(websocket):
    """Recheck idle connections every 5s and every inbound frame; never use stale identity."""
    validator = websocket.scope.get("identity_validator")
    if validator is None:
        return await websocket.receive_text()
    while True:
        try:
            value = await asyncio.wait_for(websocket.receive_text(), timeout=IDENTITY_RECHECK_SECONDS)
        except asyncio.TimeoutError:
            if await validator():
                continue
            await websocket.close(code=4401)
            raise WebSocketDisconnect(code=4401)
        if not await validator():
            await websocket.close(code=4401)
            raise WebSocketDisconnect(code=4401)
        return value

# 维护活跃连接的管理器
class ConnectionManager:
    def __init__(self):
        # 所有活跃连接：user_id -> {connection_id -> websocket}
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}
        # 聊天室连接：conversation_id -> {user_id -> {connection_id -> websocket}}
        self.chat_rooms: Dict[str, Dict[str, Dict[str, WebSocket]]] = {}
        # 通知连接：user_id -> {connection_id -> websocket}
        self.notification_connections: Dict[str, Dict[str, WebSocket]] = {}
        # WS04（bus 模式）：跨 worker 在线名单缓存 conversation_id -> {user_id, ...}，
        # 由 ws_event_bus.run_presence_loop 周期性从 ws_presence 集合刷新；
        # local 模式不读写（在线判定保持本进程精确语义）。
        self.presence_rooms_cache: Dict[str, Set[str]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str, connection_id: str):
        """建立新的WebSocket连接"""
        await websocket.accept()
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = {}
        
        self.active_connections[user_id][connection_id] = websocket
        logger.info(f"User {user_id} connected with connection {connection_id}")
    
    async def connect_to_chat(self, websocket: WebSocket, user_id: str, conversation_id: str, connection_id: str):
        """将用户连接到特定聊天室"""
        await self.connect(websocket, user_id, connection_id)

        if conversation_id not in self.chat_rooms:
            self.chat_rooms[conversation_id] = {}

        if user_id not in self.chat_rooms[conversation_id]:
            self.chat_rooms[conversation_id][user_id] = {}

        self.chat_rooms[conversation_id][user_id][connection_id] = websocket
        logger.info(f"User {user_id} joined chat room {conversation_id}")
        # bus 模式：入房立即写 presence 心跳，让其他 worker 尽快看到本用户在线（I2/I5）
        if bus_enabled():
            self._schedule_presence_sync(user_id)
    
    async def connect_to_notifications(self, websocket: WebSocket, user_id: str, connection_id: str):
        """建立通知WebSocket连接"""
        await self.connect(websocket, user_id, connection_id)
        
        if user_id not in self.notification_connections:
            self.notification_connections[user_id] = {}
        
        self.notification_connections[user_id][connection_id] = websocket
        logger.info(f"User {user_id} connected to notifications with connection {connection_id}")
    
    def disconnect(self, user_id: str, connection_id: str):
        """断开WebSocket连接"""
        if user_id in self.active_connections and connection_id in self.active_connections[user_id]:
            del self.active_connections[user_id][connection_id]
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
            logger.info(f"User {user_id} disconnected connection {connection_id}")
        
        # 同时从通知连接中移除
        if user_id in self.notification_connections and connection_id in self.notification_connections[user_id]:
            del self.notification_connections[user_id][connection_id]
            if not self.notification_connections[user_id]:
                del self.notification_connections[user_id]
        
        # 从所有聊天室中移除
        for conversation_id in list(self.chat_rooms.keys()):
            if user_id in self.chat_rooms[conversation_id] and connection_id in self.chat_rooms[conversation_id][user_id]:
                del self.chat_rooms[conversation_id][user_id][connection_id]
                if not self.chat_rooms[conversation_id][user_id]:
                    del self.chat_rooms[conversation_id][user_id]
                if not self.chat_rooms[conversation_id]:
                    del self.chat_rooms[conversation_id]

        # bus 模式：断连立即同步 presence（本 worker 已无房间则删除文档，
        # 不等 TTL），让其他 worker 的在线名单尽快收敛。
        if bus_enabled():
            self._schedule_presence_sync(user_id)

    # ---- WS04 presence（bus 模式）：跨 worker 在线视图 ----

    def presence_user_rooms(self) -> Dict[str, Set[str]]:
        """本进程在聊天室内的用户 -> 会话集合（presence 心跳的数据源）。"""
        rooms: Dict[str, Set[str]] = {}
        for conversation_id, users in self.chat_rooms.items():
            for user_id in users:
                rooms.setdefault(user_id, set()).add(conversation_id)
        return rooms

    def apply_presence_cache(self, rooms: Dict[str, Set[str]]) -> None:
        """由 presence 心跳循环周期性刷新跨 worker 在线名单缓存。"""
        self.presence_rooms_cache = rooms

    def _schedule_presence_sync(self, user_id: str):
        """调度一次 presence 同步（disconnect 为同步方法，挂后台任务执行）。"""
        try:
            asyncio.get_running_loop().create_task(self.sync_user_presence(user_id))
        except RuntimeError:
            # 无事件循环（测试/导入场景）：presence 交由 TTL 兜底清理。
            pass

    async def sync_user_presence(self, user_id: str):
        """把某用户在本 worker 的房间归属写入/删除 presence 文档。"""
        from app.api.ws_event_bus import get_bus_db, get_worker_id
        db = get_bus_db()
        worker_id = get_worker_id()
        if db is None or worker_id is None:
            return
        rooms = self.presence_user_rooms().get(user_id, set())
        if rooms:
            await upsert_presence(db, worker_id, user_id, rooms)
        else:
            await remove_presence(db, worker_id, user_id)

    async def _send_authorized(self, websocket, user_id, connection_id, message):
        validator = websocket.scope.get("identity_validator")
        if validator is not None and not await validator():
            self.disconnect(user_id, connection_id)
            await websocket.close(code=4401)
            return
        await websocket.send_json(message)

    async def send_personal_message(self, message: Dict[str, Any], user_id: str):
        """向特定用户的所有连接分发消息（WS04）。

        - local 模式（默认，C1 过渡口径）：仅本进程投递，与多 worker 化之前一致；
        - bus 模式：事件帧写入 ws_events 总线，由各 worker（含本进程）的读侧
          任务调用 deliver_personal_local 投递本进程连接——这里不再直投，避免
          双轨重复。发布失败退回本进程投递并告警。
        """
        if bus_enabled():
            try:
                await publish_event("personal", {"user_id": user_id}, message)
                return
            except Exception as e:
                logger.warning(f"ws_events 发布失败，退回本进程投递: {str(e)}")
        await self.deliver_personal_local(message, user_id)

    async def deliver_personal_local(self, message: Dict[str, Any], user_id: str):
        """本进程投递：仅命中本进程连接表（读侧任务与 local 模式共用）。"""
        if user_id in self.active_connections:
            for connection_id, websocket in list(self.active_connections[user_id].items()):
                try:
                    await self._send_authorized(websocket, user_id, connection_id, message)
                except Exception as e:
                    logger.error(f"Error sending message to user {user_id}: {str(e)}")

    async def send_chat_message(self, message: Dict[str, Any], conversation_id: str):
        """向聊天室所有成员分发帧（WS04）。模式语义同 send_personal_message。"""
        if bus_enabled():
            try:
                await publish_event("chat", {"conversation_id": conversation_id}, message)
                return
            except Exception as e:
                logger.warning(f"ws_events 发布失败，退回本进程投递: {str(e)}")
        await self.deliver_chat_local(message, conversation_id)

    async def deliver_chat_local(self, message: Dict[str, Any], conversation_id: str):
        """本进程投递：仅命中本进程聊天室连接表（读侧任务与 local 模式共用）。"""
        if conversation_id in self.chat_rooms:
            for user_id, connections in list(self.chat_rooms[conversation_id].items()):
                for connection_id, websocket in list(connections.items()):
                    try:
                        await self._send_authorized(websocket, user_id, connection_id, message)
                    except Exception as e:
                        logger.error(f"Error sending chat message to user {user_id} in conversation {conversation_id}: {str(e)}")

    async def send_notification(self, notification: Dict[str, Any], user_id: str):
        """向用户的通知连接分发通知（WS04）。模式语义同 send_personal_message。"""
        if bus_enabled():
            try:
                await publish_event("notification", {"user_id": user_id}, notification)
                return
            except Exception as e:
                logger.warning(f"ws_events 发布失败，退回本进程投递: {str(e)}")
        await self.deliver_notification_local(notification, user_id)

    async def deliver_notification_local(self, notification: Dict[str, Any], user_id: str):
        """本进程投递：仅命中本进程通知连接表（读侧任务与 local 模式共用）。"""
        if user_id in self.notification_connections:
            for connection_id, websocket in list(self.notification_connections[user_id].items()):
                try:
                    await self._send_authorized(websocket, user_id, connection_id, {
                        "type": "notification",
                        "data": notification
                    })
                except Exception as e:
                    logger.error(f"Error sending notification to user {user_id}: {str(e)}")

    def get_active_users_in_chat(self, conversation_id: str) -> Set[str]:
        """获取聊天室中的活跃用户ID集合。

        local 模式：仅本进程连接（与既有语义一致）。
        bus 模式：本进程连接 ∪ ws_presence 聚合的跨 worker 名单（缓存视图，
        刷新间隔见 ws_event_bus.PRESENCE_REFRESH_SECONDS，滞后上界即该间隔）。
        """
        active: Set[str] = set()
        if conversation_id in self.chat_rooms:
            active.update(self.chat_rooms[conversation_id].keys())
        if bus_enabled():
            active.update(self.presence_rooms_cache.get(conversation_id, set()))
        return active

# 创建连接管理器实例
# WS04：多 worker 分发已按设计稿方案 A2 落地（ws_events capped 集合总线）。
# - EVENT_BUS_MODE=local（默认）：本 manager 维持单 worker 直连语义（C1 过渡
#   口径：多 worker 扩容受 WS04 门控，启动器 scripts/runtime.py 有护栏）；
# - EVENT_BUS_MODE=bus：send_* 方法把事件帧发布到 ws_events，本进程读侧任务
#   （setup_websockets 挂载）消费后经 deliver_*_local 投递本进程连接，
#   presence 心跳维护跨 worker 在线名单。
manager = ConnectionManager()


def make_manager_deliverer(manager_instance: ConnectionManager):
    """把总线事件帧路由到本进程连接（读侧任务的投递回调）。

    payload 与 local 模式直投载荷逐字一致；未知 kind 只告警不投递。
    """
    async def deliver(frame: Dict[str, Any]):
        kind = frame.get("kind")
        target = frame.get("target") or {}
        payload = frame.get("payload")
        if kind == "chat":
            await manager_instance.deliver_chat_local(payload, target.get("conversation_id"))
        elif kind == "notification":
            await manager_instance.deliver_notification_local(payload, target.get("user_id"))
        elif kind == "personal":
            await manager_instance.deliver_personal_local(payload, target.get("user_id"))
        else:
            logger.warning("收到未知事件帧类型，已忽略: %s (ev_v=%s)", kind, frame.get("ev_v"))
    return deliver

# 在应用中注册WebSocket路由
def setup_websockets(app: FastAPI):
    # WS04：bus 模式下挂载事件总线（读侧 tailable cursor + presence 心跳）。
    # setup_websockets 由 main.py 启动序列在 connect_to_mongodb() 成功后调用，
    # 与设计稿 S1 的挂载点等价；local 模式（默认）不启动任何总线任务。
    if bus_enabled():
        async def _startup_event_bus():
            await start_event_bus(mongodb_state.db, make_manager_deliverer(manager), manager)

        app.add_event_handler("startup", _startup_event_bus)
        app.add_event_handler("shutdown", stop_event_bus)

    @app.websocket("/ws/chat/{conversation_id}")
    async def websocket_chat_endpoint(
        websocket: WebSocket, 
        conversation_id: str,
        db: AsyncIOMotorClient = Depends(get_database)
    ):
        """聊天WebSocket端点"""
        user = None
        connection_id = f"conn_{datetime.now().timestamp()}"
        
        try:
            # 验证用户身份
            user = await get_current_user_ws(websocket, db)
            if not user:
                await websocket.close(code=1008)  # Policy violation
                return
            
            user_id = str(user["_id"])

            if unified_authentication():
                async def valid_identity():
                    try:
                        current = await get_current_user_ws(websocket, db)
                        return bool(current and str(current["_id"]) == user_id and
                            await CommunicationService.is_conversation_participant(db, conversation_id, user_id))
                    except Exception:
                        return False
                websocket.scope["identity_validator"] = valid_identity

            # 会话成员校验（WS02 前置）：非会话参与者拒绝入房。
            # 房间名即会话 id（/ws/chat/{conversation_id}，Mongo ObjectId 字符串），
            # 沿用现有约定，不做别名映射。
            if not await CommunicationService.is_conversation_participant(db, conversation_id, user_id):
                # 先 accept 以便投递明确错误码，再以 4403（应用定义：非会话成员）断连
                await websocket.accept()
                await websocket.send_json({
                    "type": "error",
                    "error_code": "NOT_CONVERSATION_PARTICIPANT",
                    "message": "用户不是该会话参与者",
                })
                await websocket.close(code=4403)
                logger.warning(f"User {user_id} denied joining chat room {conversation_id}: not a participant")
                return

            # 建立连接
            await manager.connect_to_chat(websocket, user_id, conversation_id, connection_id)
            
            # 通知聊天室中的其他用户有新用户加入
            active_users = manager.get_active_users_in_chat(conversation_id)
            await manager.send_chat_message(
                {
                    "type": "user_joined",
                    "user_id": user_id,
                    "user_name": user.get("name", "Unknown"),
                    "active_users": list(active_users),
                    "timestamp": datetime.now().isoformat()
                },
                conversation_id
            )
            
            # 处理消息
            try:
                while True:
                    # 接收消息
                    data = await receive_authorized(websocket)
                    message_data = json.loads(data)
                    
                    # 根据消息类型处理
                    if message_data.get("type") == "message":
                        # 先持久化、再广播（落库失败不广播，WS03）。
                        # 广播由 CommunicationService.send_message 在落库成功后完成，
                        # 载荷携带落库文档的真实 _id 与 UTC 时间戳（不再用时间戳冒充 id）。
                        message_content = message_data.get("content", "")
                        client_message_id = message_data.get("client_message_id")  # 幂等键，可选
                        if not message_content:
                            await websocket.send_json({
                                "type": "error",
                                "error_code": "INVALID_PAYLOAD",
                                "message": "content is required",
                            })
                            continue
                        try:
                            message_response = await CommunicationService.send_message(
                                db,
                                conversation_id,
                                user_id,
                                message_content,
                                message_data.get("message_type", "text"),
                                message_data.get("attachments"),
                                message_data.get("metadata"),
                                client_message_id=client_message_id,
                            )
                        except ValueError:
                            # 非会话成员（连接期间被移出/会话不存在）：拒绝并断连
                            await websocket.send_json({
                                "type": "error",
                                "error_code": "NOT_CONVERSATION_PARTICIPANT",
                                "message": "用户不是该会话参与者",
                            })
                            manager.disconnect(user_id, connection_id)
                            await websocket.close(code=4403)
                            return
                        except Exception as e:
                            # 数据库失败：向发送者回错误帧，不广播
                            logger.error(f"Failed to persist chat message in conversation {conversation_id}: {str(e)}")
                            await websocket.send_json({
                                "type": "error",
                                "error_code": "MESSAGE_PERSIST_FAILED",
                                "message": "消息落库失败，请重试",
                            })
                            continue

                        # 幂等回执：告知发送者该 client_message_id 对应的服务端消息
                        # （重复投递时 message 为既有文档，载荷 id 不变）
                        await websocket.send_json({
                            "type": "message_ack",
                            "client_message_id": client_message_id,
                            "message": message_response,
                        })
                    elif message_data.get("type") == "typing":
                        # 纯瞬态信号（WS03 处置：维持仅转发，不落库）。理由：
                        # 1) "正在输入"无持久化语义，落库反而不诚实；
                        # 2) 房间内成员均已在入房时通过 is_conversation_participant
                        #    校验，转发只发生在已校验房间内，逐帧重复查库纯属浪费；
                        # 3) 前端（chatWsService.ts）明确不发送不消费该帧。
                        await manager.send_chat_message(
                            {
                                "type": "typing",
                                "user_id": user_id,
                                "user_name": user.get("name", "Unknown"),
                                "is_typing": message_data.get("is_typing", False)
                            },
                            conversation_id
                        )
                    elif message_data.get("type") == "read_receipt":
                        # WS03：已读回执真实落库。语义与 REST
                        # PUT /communications/conversations/{id}/read 一致——把本会话中
                        # 发给当前用户的所有未读消息标记已读（HTTP/WS 共用同一服务方法，
                        # DB 单一事实源）；落库成功后由服务方法向房间广播 read_receipt
                        # 帧（conversation_id/reader_id/message_ids/read_at），对方客户端
                        # 实时感知"对方已读"。落库失败回错误帧，不广播。
                        # 帧不携带消息粒度：单条已读走 REST
                        # PUT /communications/messages/{message_id}/read。
                        if not await CommunicationService.is_conversation_participant(db, conversation_id, user_id):
                            # 连接期间被移出会话：与 message 分支同语义，拒绝并断连
                            await websocket.send_json({
                                "type": "error",
                                "error_code": "NOT_CONVERSATION_PARTICIPANT",
                                "message": "用户不是该会话参与者",
                            })
                            manager.disconnect(user_id, connection_id)
                            await websocket.close(code=4403)
                            return
                        try:
                            await CommunicationService.mark_conversation_as_read(db, conversation_id, user_id)
                        except Exception as e:
                            # 数据库失败：向发送者回错误帧，不广播
                            logger.error(f"Failed to persist read receipt in conversation {conversation_id}: {str(e)}")
                            await websocket.send_json({
                                "type": "error",
                                "error_code": "READ_RECEIPT_PERSIST_FAILED",
                                "message": "已读回执落库失败，请重试",
                            })
                            continue
            except WebSocketDisconnect:
                # 用户断开连接
                manager.disconnect(user_id, connection_id)
                # 通知其他用户
                active_users = manager.get_active_users_in_chat(conversation_id)
                await manager.send_chat_message(
                    {
                        "type": "user_left",
                        "user_id": user_id,
                        "user_name": user.get("name", "Unknown"),
                        "active_users": list(active_users),
                        "timestamp": datetime.now().isoformat()
                    },
                    conversation_id
                )
            except Exception as e:
                logger.error(f"Error in chat websocket: {str(e)}")
                manager.disconnect(user_id, connection_id)
        except Exception as e:
            logger.error(f"Error establishing chat websocket connection: {str(e)}")
            try:
                await websocket.close(code=1011)  # Internal error
            except:
                pass
    
    @app.websocket("/ws/notifications")
    async def websocket_notification_endpoint(
        websocket: WebSocket,
        db: AsyncIOMotorClient = Depends(get_database)
    ):
        """通知WebSocket端点"""
        user = None
        connection_id = f"notif_{datetime.now().timestamp()}"
        
        try:
            # 验证用户身份
            user = await get_current_user_ws(websocket, db)
            if not user:
                await websocket.close(code=1008)  # Policy violation
                return
            
            user_id = str(user["_id"])

            if unified_authentication():
                async def valid_identity():
                    try:
                        current = await get_current_user_ws(websocket, db)
                        return bool(current and str(current["_id"]) == user_id)
                    except Exception:
                        return False
                websocket.scope["identity_validator"] = valid_identity
            
            # 建立连接
            await manager.connect_to_notifications(websocket, user_id, connection_id)
            
            # 发送初始未读通知数量
            unread_count = await NotificationService.get_unread_count(db, user_id)
            await manager._send_authorized(websocket, user_id, connection_id, {
                "type": "notification_count",
                "count": unread_count
            })
            
            # 处理消息
            try:
                while True:
                    # 保持连接活跃，接收可能的客户端消息
                    data = await receive_authorized(websocket)
                    # 这里可以处理客户端发送的配置消息，如通知设置等
            except WebSocketDisconnect:
                # 用户断开连接
                manager.disconnect(user_id, connection_id)
            except Exception as e:
                logger.error(f"Error in notification websocket: {str(e)}")
                manager.disconnect(user_id, connection_id)
        except Exception as e:
            logger.error(f"Error establishing notification websocket connection: {str(e)}")
            try:
                await websocket.close(code=1011)  # Internal error
            except:
                pass

    # 添加其他WebSocket端点...

# 暴露管理器实例，供其他模块使用
def get_connection_manager():
    return manager
