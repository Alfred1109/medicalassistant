"""实时通道（WebSocket）连接管理器：中性层。

连接表与投递语义既被 api 层（WS 端点）使用，也被 services 层（发消息后
推送）使用。此前管理器住在 app/api/websockets.py，services 只能反向 import
api（方向倒挂）。本模块是中立住处：services 与 api 都只依赖这里。

事件总线（app/api/ws_event_bus.py）是 WS 基础设施模块，目前仍放在 api 包
下；彻底归位到 app/realtime/ 需要移动该文件（不在本次改动清单内）。
"""
import asyncio
import logging
from typing import Any, Callable, Dict, Optional, Set

from bson import ObjectId
from fastapi import WebSocket

from app.api.ws_event_bus import (
    bus_enabled,
    get_bus_db,
    get_worker_id,
    publish_event,
    remove_presence,
    upsert_presence,
)

logger = logging.getLogger(__name__)


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


def get_connection_manager() -> ConnectionManager:
    """本进程的连接管理器单例。"""
    return manager


# 上层装配点登记的「连接管理器提供方」：晚绑定到提供方自身的解析，
# 使既有运行时注入/patch 点（app.api.websockets.get_connection_manager）
# 在管理器迁出 api 层后仍然生效；未登记时直接用本模块单例。
_manager_provider: Optional[Callable[[], ConnectionManager]] = None


def register_manager_provider(provider: Callable[[], ConnectionManager]) -> None:
    """登记连接管理器提供方（api 层装配时调用）。"""
    global _manager_provider
    _manager_provider = provider


def resolve_connection_manager() -> ConnectionManager:
    """当前进程的连接管理器：优先用上层登记的提供方，否则用本模块单例。"""
    if _manager_provider is not None:
        return _manager_provider()
    return manager
