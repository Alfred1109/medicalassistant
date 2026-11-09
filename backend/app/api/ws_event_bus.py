"""
WS04 跨 worker 事件总线（设计稿方案 A2：Mongo capped collection + tailable cursor）。

机制（docs/wp5-ws04-multiworker-design-draft-2026-11-07.md §3-A2 / §5-S1/S2）：
- 写侧：每个需要实时分发的事件显式 insert 一条事件帧到 ws_events（capped，1MB）；
- 读侧：每个 worker 一个 tailable await cursor 消费全部事件帧，按 target 过滤后
  只投递给本进程命中的连接（复用 ConnectionManager 的本进程投递方法）；
- cursor 死亡（capped 回卷 / 连接故障）时按 last _id 重连重放，重放窗口内的
  短暂断线可补，超出窗口被覆盖则丢（聊天域有落库 + 离线同步兜底）；
- presence：ws_presence 集合（user_id/worker_id/心跳时间 + TTL 索引）维护跨
  worker 在线视图，供本进程在线判定合并跨 worker 名单。

配置开关（core/config.py）：EVENT_BUS_MODE = local | bus
- local（默认）：单 worker 直连分发，行为与多 worker 化之前完全一致（C1 护栏
  口径，设计稿 §3-C1 / §7-5）；
- bus：写侧 publish 到 ws_events，读侧任务跨 worker 分发。
"""
import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, Optional, Set

from pymongo import CursorType

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 事件帧 schema 与推荐默认值（设计稿 §7 决策点，2026-11-09 采纳推荐值）
# ---------------------------------------------------------------------------

EVENT_FRAME_VERSION = 1  # ev_v：事件帧 schema 版本，为 A1(change streams) 升级位预留

# §7-6 推荐起步值：1MB（约数千条事件帧）；capped 一经创建不可改容量，
# 有量级预期后再按"峰值事件速率 × 回放窗口"评估扩容（需新建集合切名）。
WS_EVENTS_CAP_BYTES = 1024 * 1024

# §7-3 推荐值：presence TTL 90s、心跳 30s（TTL ≥ 心跳 × 3，防 worker GC 暂停误判）。
PRESENCE_TTL_SECONDS = 90
PRESENCE_HEARTBEAT_SECONDS = 30

# presence 缓存刷新间隔：disconnect 虽主动删除 presence 文档，但跨 worker 的
# 在线名单是周期刷新的缓存视图，滞后上界即本间隔。设计稿未给推荐值（待定项），
# 取心跳间隔的 1/6，在误判"在线"方向把窗口压到 5s。
PRESENCE_REFRESH_SECONDS = 5

EVENT_BUS_RECONNECT_DELAY_SECONDS = 1.0  # cursor 死亡后的重连间隔
MAX_AWAIT_TIME_MS = 1000  # tailable await cursor 的唤醒粒度

WS_EVENTS_COLLECTION = "ws_events"
WS_PRESENCE_COLLECTION = "ws_presence"

VALID_BUS_MODES = ("local", "bus")


def bus_enabled() -> bool:
    """当前是否处于跨 worker 总线模式（bus）。"""
    return settings.EVENT_BUS_MODE == "bus"


# ---------------------------------------------------------------------------
# 进程内总线状态（每个 worker 一份：db 句柄、worker 身份、后台任务）
# ---------------------------------------------------------------------------

_state: Dict[str, Any] = {
    "db": None,
    "worker_id": None,
    "reader_task": None,
    "presence_task": None,
}


def configure_bus(db: Any, worker_id: Optional[str] = None) -> str:
    """绑定本 worker 的 db 句柄与身份（启动序列调用；测试可显式注入假 db）。"""
    if settings.EVENT_BUS_MODE not in VALID_BUS_MODES:
        raise ValueError(f"EVENT_BUS_MODE 必须是 {VALID_BUS_MODES} 之一，实际为 {settings.EVENT_BUS_MODE!r}")
    _state["db"] = db
    # worker 身份优先取容器编排注入值，否则进程内随机——presence 按
    # (user_id, worker_id) 归属，重启后旧文档由 TTL 兜底清理。
    _state["worker_id"] = worker_id or os.getenv("MEDICALASSISTANT_WORKER_ID") or uuid.uuid4().hex
    return _state["worker_id"]


def reset_bus() -> None:
    """清空总线状态（测试隔离用；生产不调用）。"""
    _state.update({"db": None, "worker_id": None, "reader_task": None, "presence_task": None})


def get_bus_db() -> Any:
    return _state["db"]


def get_worker_id() -> Optional[str]:
    return _state["worker_id"]


# ---------------------------------------------------------------------------
# ws_events / ws_presence 幂等初始化（S1：挂在启动序列，等价 ensure_communication_indexes 位置）
# ---------------------------------------------------------------------------

async def ensure_ws_collections(db: Any) -> None:
    """幂等创建 ws_events（capped 1MB）并声明 ws_presence 的 TTL 索引。

    capped 集合一经创建不可改容量；若集合已存在但非 capped（例如先被隐式
    insert 创建），只告警不阻断——事件写入仍可用，仅失去回放窗口。
    """
    # motor 的 list_collections 协程返回 pymongo CommandCursor（同步迭代即可）
    existing = {info["name"]: info.get("options", {})
                for info in await db.list_collections()}
    if WS_EVENTS_COLLECTION not in existing:
        try:
            await db.create_collection(
                WS_EVENTS_COLLECTION, capped=True, size=WS_EVENTS_CAP_BYTES)
            logger.info("事件总线集合已创建: %s (capped, %d bytes)", WS_EVENTS_COLLECTION, WS_EVENTS_CAP_BYTES)
        except Exception as e:
            # 并发 worker 同时创建的竞态：集合已存在即视为成功。
            names = {info["name"] for info in await db.list_collections()}
            if WS_EVENTS_COLLECTION not in names:
                raise
            logger.info("事件总线集合已由其他 worker 创建: %s", WS_EVENTS_COLLECTION)
    elif not existing[WS_EVENTS_COLLECTION].get("capped"):
        logger.warning(
            "集合 %s 已存在且非 capped：事件可写但无回放窗口（游标不可 tailable），"
            "建议迁移为 capped 集合", WS_EVENTS_COLLECTION)

    # TTL 索引：以 heartbeat_at + expireAfterSeconds=PRESENCE_TTL_SECONDS 表达
    # "90s 未心跳即失联"；读侧另按 expires_at 过滤兜底（Mongo TTL 监控约 60s 一轮）。
    await db[WS_PRESENCE_COLLECTION].create_index(
        "heartbeat_at", expireAfterSeconds=PRESENCE_TTL_SECONDS,
        name="ws_presence_heartbeat_ttl")
    logger.info("presence TTL 索引已就绪: ws_presence.heartbeat_at (%ds)", PRESENCE_TTL_SECONDS)


# ---------------------------------------------------------------------------
# 写侧：事件帧发布（S2）
# ---------------------------------------------------------------------------

async def publish_event(kind: str, target: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """向 ws_events 总线发布一条事件帧。

    帧结构（设计稿 §5-S1）：{ev_v, kind, target, payload, ts, worker_id}
    - kind：chat（聊天房间帧）/ notification（通知推送）/ personal（定向未读数等）
    - target：{conversation_id} 或 {user_id}，读侧按本进程命中过滤
    - payload：客户端最终收到的原始帧（与 local 模式直投载荷完全一致）
    """
    db = _state["db"]
    if db is None:
        raise RuntimeError("事件总线未配置（configure_bus 未调用）")
    frame = {
        "ev_v": EVENT_FRAME_VERSION,
        "kind": kind,
        "target": target,
        "payload": payload,
        "ts": datetime.utcnow(),
        "worker_id": _state["worker_id"],
    }
    await db[WS_EVENTS_COLLECTION].insert_one(dict(frame))
    return frame


# ---------------------------------------------------------------------------
# presence 写读（S3 的连接层部分；消费方 communication_service 不在本次改动面）
# ---------------------------------------------------------------------------

async def upsert_presence(db: Any, worker_id: str, user_id: str, conversation_ids: Set[str]) -> None:
    """心跳/入房时更新 presence；conversation_ids 为空集合时删除文档。"""
    if not conversation_ids:
        await remove_presence(db, worker_id, user_id)
        return
    now = datetime.utcnow()
    await db[WS_PRESENCE_COLLECTION].update_one(
        {"user_id": user_id, "worker_id": worker_id},
        {"$set": {
            "conversation_ids": sorted(conversation_ids),
            "heartbeat_at": now,
            "expires_at": now + timedelta(seconds=PRESENCE_TTL_SECONDS),
        }},
        upsert=True,
    )


async def remove_presence(db: Any, worker_id: str, user_id: str) -> None:
    """主动下线：断连立即删除 presence 文档（不等 TTL）。"""
    await db[WS_PRESENCE_COLLECTION].delete_one({"user_id": user_id, "worker_id": worker_id})


async def load_presence_rooms(db: Any) -> Dict[str, Set[str]]:
    """把全部未过期 presence 聚合为 conversation_id -> {user_id, ...}。

    只认 expires_at 仍在未来的文档：Mongo TTL 监控约 60s 才跑一轮，
    读侧过滤是权威判据，TTL 索引仅作兜底清理。
    """
    now = datetime.utcnow()
    rooms: Dict[str, Set[str]] = {}
    async for doc in db[WS_PRESENCE_COLLECTION].find({"expires_at": {"$gt": now}}):
        for conversation_id in doc.get("conversation_ids", []):
            rooms.setdefault(conversation_id, set()).add(doc["user_id"])
    return rooms


async def run_presence_loop(manager: Any, reconnect_delay: float = EVENT_BUS_RECONNECT_DELAY_SECONDS) -> None:
    """本 worker 的 presence 心跳循环（bus 模式，每个 worker 一个）。

    - 每 PRESENCE_HEARTBEAT_SECONDS 写一轮本进程全部在线用户的心跳；
    - 每 PRESENCE_REFRESH_SECONDS 刷新跨 worker 在线名单缓存（apply_presence_cache），
      供 get_active_users_in_chat 合并出完整名单（I5）与在线判定（I2）使用；
    - 心跳写失败不阻塞主流程（设计稿 §六），仅告警。
    """
    db = _state["db"]
    worker_id = _state["worker_id"]
    if db is None:
        logger.warning("presence 心跳循环未启动：总线未配置")
        return
    last_heartbeat = 0.0
    while True:
        try:
            now = asyncio.get_running_loop().time()
            if now - last_heartbeat >= PRESENCE_HEARTBEAT_SECONDS:
                user_rooms = manager.presence_user_rooms()
                for user_id, rooms in user_rooms.items():
                    await upsert_presence(db, worker_id, user_id, rooms)
                last_heartbeat = now
            manager.apply_presence_cache(await load_presence_rooms(db))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("presence 心跳/缓存刷新失败（不阻塞主流程）: %s", e)
        await asyncio.sleep(PRESENCE_REFRESH_SECONDS)


# ---------------------------------------------------------------------------
# 读侧：tailable await cursor 消费循环（S1）
# ---------------------------------------------------------------------------

class EventBusReader:
    """ws_events 读侧消费者：tailable await cursor + 死亡重连重放。

    - _open_cursor 可在测试中覆写/注入假游标；
    - dispatch_available 消费当前可得事件（真游标上 tailable await 会阻塞等待
      新帧，max_await_time_ms 控制唤醒粒度；假游标自然耗尽即返回）；
    - 游标死亡（capped 回卷 kill / 连接故障）由 run 循环捕获，按 last _id
      重连重放：_id > last_id 的过滤天然去重，不会重复投递已消费事件。
    """

    def __init__(self, deliver: Callable[[Dict[str, Any]], Awaitable[None]],
                 db: Optional[Any] = None,
                 collection: str = WS_EVENTS_COLLECTION,
                 reconnect_delay: float = EVENT_BUS_RECONNECT_DELAY_SECONDS):
        self._deliver = deliver
        self._db = db if db is not None else _state["db"]
        self._collection = collection
        self._reconnect_delay = reconnect_delay
        self._last_id: Optional[Any] = None

    @property
    def last_id(self) -> Optional[Any]:
        return self._last_id

    def _open_cursor(self):
        query: Dict[str, Any] = {}
        if self._last_id is not None:
            query["_id"] = {"$gt": self._last_id}
        # tailable cursor 不允许 sort：capped 集合自然序即插入序，_id 单调一致。
        cursor = self._db[self._collection].find(query, cursor_type=CursorType.TAILABLE_AWAIT)
        return cursor.max_await_time_ms(MAX_AWAIT_TIME_MS)

    async def dispatch_available(self) -> int:
        """消费当前游标可得的全部事件帧并投递；返回本轮消费条数。"""
        cursor = self._open_cursor()
        count = 0
        async for doc in cursor:
            self._last_id = doc["_id"]
            await self._deliver(doc)
            count += 1
        return count

    async def run(self) -> None:
        """消费主循环：游标死亡/故障时按 last _id 重连重放，直到任务被取消。"""
        while True:
            try:
                await self.dispatch_available()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("ws_events 游标中断，按 last _id 重连重放: %s", e)
            await asyncio.sleep(self._reconnect_delay)


async def start_event_bus(db: Any, deliver: Callable[[Dict[str, Any]], Awaitable[None]],
                          manager: Optional[Any] = None) -> None:
    """启动本 worker 的总线任务（读侧消费 + presence 心跳）。

    db 句柄由调用方传入（生产为 connect_to_mongodb 之后的 mongodb_state.db，
    与设计稿 S1"挂入 main.py 启动序列"等价——setup_websockets 由该序列调用）。
    """
    configure_bus(db)
    db = _state["db"]
    if db is None:
        logger.warning("事件总线未启动：db 句柄不可用")
        return
    await ensure_ws_collections(db)
    reader = EventBusReader(deliver, db)
    _state["reader_task"] = asyncio.create_task(reader.run(), name="ws-event-bus-reader")
    if manager is not None:
        _state["presence_task"] = asyncio.create_task(
            run_presence_loop(manager), name="ws-presence-heartbeat")
    logger.info("WS04 事件总线已启动（worker=%s, mode=bus）", _state["worker_id"])


async def stop_event_bus() -> None:
    """停止总线后台任务（shutdown；测试中用于清理）。"""
    for key in ("reader_task", "presence_task"):
        task = _state.get(key)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    _state.update({"reader_task": None, "presence_task": None})
