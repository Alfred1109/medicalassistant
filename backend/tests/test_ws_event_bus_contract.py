"""
WS04 跨 worker 事件总线契约测试（方案 A2：ws_events capped 集合 + tailable cursor）。

覆盖：
- ws_events（capped 1MB）与 ws_presence（TTL 90s）幂等初始化契约
- 事件帧 schema（ev_v/kind/target/payload/ts/worker_id）与发布契约
- C1 单 worker 护栏：EVENT_BUS_MODE=local（默认）时行为与多 worker 化之前一致，
  不写总线；runtime 启动命令固定单 worker、显式多 worker 请求被拒绝
- bus 模式写侧：send_chat_message/send_notification/send_personal_message 发布
  事件帧而非本地直投（双轨不重复），发布失败退回本进程投递
- 双连接跨 worker 广播：两个 manager 实例（模拟两个 worker）各自读侧消费后，
  均只把帧投递给本进程命中的连接，且各连接恰好收到一次
- ws_events 循环游标回退：cursor 死亡（capped 回卷 kill）后按 last _id 重连重放，
  不重复投递已消费事件；被覆盖的事件不再出现
- presence：TTL 心跳文档形状、过期过滤、跨 worker 在线名单合并、断连即时删除

风格参照 test_communication_contract.py：内存 Mongo 桩 + asyncio 隔离用例；
真实副本集行为（tailable cursor、capped 回卷）见文件尾部 WsEventBusMongoTests，
需显式提供 REHAB_TEST_REPLICA_URI（隔离本地副本集，参照 deploy/mongodb/README.md）。
"""
import asyncio
import importlib.util
import os
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from bson import ObjectId
from pymongo.errors import OperationFailure

from app.api.ws_event_bus import (
    EVENT_FRAME_VERSION,
    PRESENCE_HEARTBEAT_SECONDS,
    PRESENCE_TTL_SECONDS,
    WS_EVENTS_CAP_BYTES,
    WS_EVENTS_COLLECTION,
    WS_PRESENCE_COLLECTION,
    EventBusReader,
    bus_enabled,
    configure_bus,
    ensure_ws_collections,
    load_presence_rooms,
    publish_event,
    remove_presence,
    reset_bus,
    upsert_presence,
)
from app.api.websockets import ConnectionManager, make_manager_deliverer
from app.core.config import Settings, settings


# ---------------------------------------------------------------------------
# 内存 Mongo 桩：仅实现事件总线用到的最小能力
# ---------------------------------------------------------------------------

def _matches(doc, query):
    for key, expected in query.items():
        value = doc.get(key)
        if isinstance(expected, dict) and "$gt" in expected:
            if not (value is not None and value > expected["$gt"]):
                return False
        elif isinstance(expected, dict) and "$in" in expected:
            if value not in expected["$in"]:
                return False
        elif value != expected:
            return False
    return True


class FakeCursor:
    def __init__(self, docs, die_after=None):
        self._docs = list(docs)
        self._die_after = die_after
        self._yielded = 0

    def max_await_time_ms(self, ms):
        # 对齐 pymongo tailable await 游标的方法链（假游标仅吞掉参数）
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        # die_after：模拟 tailable cursor 被 capped 回卷 kill——推进若干条后抛
        # OperationFailure，而不是自然耗尽（tailable 游标不会自然耗尽）。
        if self._die_after is not None and self._yielded >= self._die_after:
            raise OperationFailure("tailable cursor died (capped collection rolled over)")
        if not self._docs:
            if self._die_after is not None:
                raise OperationFailure("tailable cursor died (capped collection rolled over)")
            raise StopAsyncIteration
        self._yielded += 1
        return self._docs.pop(0)


class FakeCollection:
    def __init__(self):
        self.docs = []
        self.indexes = []  # create_index 调用记录：(keys, kwargs)

    async def create_index(self, keys, **kwargs):
        self.indexes.append((keys, dict(kwargs)))
        return kwargs.get("name", str(keys))

    async def insert_one(self, doc):
        stored = dict(doc)
        stored.setdefault("_id", ObjectId())
        self.docs.append(stored)
        return SimpleNamespace(inserted_id=stored["_id"])

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if _matches(doc, query):
                doc.update(update.get("$set", {}))
                return SimpleNamespace(modified_count=1)
        if upsert:
            doc = dict(query)
            doc.update(update.get("$set", {}))
            doc.setdefault("_id", ObjectId())
            self.docs.append(doc)
            return SimpleNamespace(modified_count=0)
        return SimpleNamespace(modified_count=0)

    async def delete_one(self, query):
        before = len(self.docs)
        self.docs = [doc for doc in self.docs if not _matches(doc, query)]
        return SimpleNamespace(deleted_count=before - len(self.docs))

    def find(self, query=None, **kwargs):
        docs = [dict(doc) for doc in self.docs if _matches(doc, query or {})]
        return FakeCursor(docs, die_after=kwargs.get("die_after"))


class FakeDB:
    def __init__(self):
        self.created = {}  # create_collection 记录：name -> options
        self.ws_events = FakeCollection()
        self.ws_presence = FakeCollection()

    def __getitem__(self, name):
        # getattr 仅在属性缺失时触发 __getattr__，避免把已写入数据的集合覆盖成新实例
        return getattr(self, name)

    def __getattr__(self, name):
        collection = FakeCollection()
        setattr(self, name, collection)
        return collection

    async def list_collections(self):
        # 对齐 motor：协程返回可同步迭代的游标/列表
        return [{"name": name, "options": options}
                for name, options in self.created.items()]

    async def create_collection(self, name, **options):
        if name in self.created:
            from pymongo.errors import CollectionInvalid
            raise CollectionInvalid(f"collection {name} already exists")
        self.created[name] = dict(options)
        return SimpleNamespace(name=name)


class FakeWebSocket:
    def __init__(self):
        self.sent = []
        self.scope = {}
        self.closed = False

    async def accept(self):
        pass

    async def send_json(self, message):
        self.sent.append(message)


def make_frame(kind="chat", target=None, payload=None, oid=None):
    return {
        "_id": oid or ObjectId(),
        "ev_v": EVENT_FRAME_VERSION,
        "kind": kind,
        "target": target or {},
        "payload": payload or {},
        "ts": datetime.utcnow(),
        "worker_id": "publisher",
    }


def collect_deliveries(store):
    async def deliver(frame):
        store.append(frame)
    return deliver


class BusTestCase(unittest.IsolatedAsyncioTestCase):
    """公共夹具：隔离 EVENT_BUS_MODE 与总线状态。"""

    def setUp(self):
        self.db = FakeDB()
        self.mode_patch = patch.object(settings, "EVENT_BUS_MODE", "local")
        self.mode_patch.start()
        reset_bus()

    def tearDown(self):
        self.mode_patch.stop()
        reset_bus()

    def go_bus(self):
        self.mode_patch.stop()
        self.mode_patch = patch.object(settings, "EVENT_BUS_MODE", "bus")
        self.mode_patch.start()
        configure_bus(self.db, worker_id="worker-under-test")


# ---------------------------------------------------------------------------
# S1：ws_events / ws_presence 幂等初始化
# ---------------------------------------------------------------------------

class EventBusBootstrapTests(BusTestCase):
    async def test_ws_events_created_capped_with_recommended_size(self):
        await ensure_ws_collections(self.db)
        # §7-6 采纳推荐值：capped，起步 1MB
        self.assertEqual(self.db.created[WS_EVENTS_COLLECTION],
                         {"capped": True, "size": WS_EVENTS_CAP_BYTES})
        self.assertEqual(WS_EVENTS_CAP_BYTES, 1024 * 1024)

    async def test_presence_ttl_index_matches_recommended_values(self):
        await ensure_ws_collections(self.db)
        (keys, kwargs), = self.db.ws_presence.indexes
        self.assertEqual(keys, "heartbeat_at")
        # §7-3 采纳推荐值：TTL 90s、心跳 30s（TTL ≥ 心跳 × 3）
        self.assertEqual(kwargs["expireAfterSeconds"], PRESENCE_TTL_SECONDS)
        self.assertEqual(PRESENCE_TTL_SECONDS, 90)
        self.assertEqual(PRESENCE_HEARTBEAT_SECONDS, 30)

    async def test_bootstrap_is_idempotent(self):
        await ensure_ws_collections(self.db)
        await ensure_ws_collections(self.db)  # 已存在：不重复创建、不抛错
        self.assertEqual(len(self.db.created), 1)

    async def test_existing_non_capped_collection_is_kept_with_warning(self):
        # 集合被隐式 insert 抢先创建成非 capped：不阻断启动、不再创建
        self.db.created[WS_EVENTS_COLLECTION] = {}
        await ensure_ws_collections(self.db)
        self.assertEqual(self.db.created[WS_EVENTS_COLLECTION], {})


# ---------------------------------------------------------------------------
# 写侧：事件帧 schema 与发布契约
# ---------------------------------------------------------------------------

class PublishFrameContractTests(BusTestCase):
    async def test_frame_carries_version_kind_target_payload_and_origin(self):
        configure_bus(self.db, worker_id="w1")
        payload = {"type": "message", "message": {"id": "m1"}}
        frame = await publish_event("chat", {"conversation_id": "conv1"}, payload)

        stored = self.db.ws_events.docs[0]
        self.assertEqual(stored["ev_v"], EVENT_FRAME_VERSION)
        self.assertEqual(stored["ev_v"], 1)  # schema 版本，为 A1 升级位预留
        self.assertEqual(stored["kind"], "chat")
        self.assertEqual(stored["target"], {"conversation_id": "conv1"})
        self.assertEqual(stored["payload"], payload)
        self.assertEqual(stored["worker_id"], "w1")
        self.assertIsInstance(stored["ts"], datetime)
        # 发布返回值与落库文档逐字段一致（_id 由集合层生成，不入返回值契约）
        self.assertTrue(all(stored[key] == value for key, value in frame.items()))

    async def test_publish_without_configured_bus_fails_loudly(self):
        with self.assertRaises(RuntimeError):
            await publish_event("chat", {"conversation_id": "c"}, {})

    async def test_invalid_mode_is_rejected_at_configure_time(self):
        with patch.object(settings, "EVENT_BUS_MODE", "something-else"):
            with self.assertRaises(ValueError):
                configure_bus(self.db, worker_id="w1")


# ---------------------------------------------------------------------------
# C1 单 worker 护栏（过渡期口径）
# ---------------------------------------------------------------------------

_spec = importlib.util.spec_from_file_location(
    "rehab_ws04_runtime", Path(__file__).resolve().parents[2] / "scripts/runtime.py")
runtime = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runtime)


class SingleWorkerGuardrailTests(BusTestCase):
    async def test_default_mode_is_local_and_bus_disabled(self):
        # 默认（无环境变量覆盖）保持单 worker 直连语义
        self.assertEqual(Settings.model_fields["EVENT_BUS_MODE"].default, "local")
        self.assertFalse(bus_enabled())

    async def test_local_mode_delivers_locally_without_touching_bus(self):
        manager = ConnectionManager()
        ws = FakeWebSocket()
        await manager.connect_to_chat(ws, "alice", "conv1", "c1")

        await manager.send_chat_message({"type": "message", "message": {"id": "m1"}}, "conv1")

        self.assertEqual(len(ws.sent), 1)  # 行为与多 worker 化之前一致
        self.assertEqual(self.db.ws_events.docs, [])  # 不写总线
        self.assertEqual(self.db.ws_presence.docs, [])  # 不写 presence

    async def test_launcher_command_is_pinned_to_single_worker(self):
        # C1 护栏：启动命令固定单 worker（无 --workers 可乘之机）
        command = runtime.backend_command("python", "127.0.0.1", 5502)
        self.assertNotIn("--workers", command)

    def test_explicit_multi_worker_request_is_rejected(self):
        with patch.dict(os.environ, {"MEDICALASSISTANT_BACKEND_WORKERS": "4"}):
            with self.assertRaisesRegex(runtime.RuntimeFailure, "single-worker"):
                runtime.enforce_single_worker_guard()

    def test_single_worker_request_is_allowed(self):
        for value in (None, "1"):
            env = {"MEDICALASSISTANT_BACKEND_WORKERS": value} if value else {}
            with patch.dict(os.environ, env):
                if value is None:
                    os.environ.pop("MEDICALASSISTANT_BACKEND_WORKERS", None)
                runtime.enforce_single_worker_guard()  # 不抛错


# ---------------------------------------------------------------------------
# S2：bus 模式写侧切换（双轨不重复）
# ---------------------------------------------------------------------------

class BusModeWriteSideTests(BusTestCase):
    async def test_bus_mode_publishes_instead_of_local_direct_delivery(self):
        self.go_bus()
        manager = ConnectionManager()
        ws = FakeWebSocket()
        await manager.connect_to_chat(ws, "alice", "conv1", "c1")

        payload = {"type": "message", "message": {"id": "m1"}}
        await manager.send_chat_message(dict(payload), "conv1")

        # 写侧只发布，不直投（本进程投递由读侧任务完成，避免双轨重复）
        self.assertEqual(ws.sent, [])
        (frame,) = self.db.ws_events.docs
        self.assertEqual(frame["kind"], "chat")
        self.assertEqual(frame["target"], {"conversation_id": "conv1"})
        self.assertEqual(frame["payload"], payload)

        # 读侧消费后本进程连接收到，且恰好一次
        reader = EventBusReader(make_manager_deliverer(manager), self.db)
        self.assertEqual(await reader.dispatch_available(), 1)
        self.assertEqual(ws.sent, [payload])

    async def test_publish_failure_falls_back_to_local_delivery(self):
        self.go_bus()
        manager = ConnectionManager()
        ws = FakeWebSocket()
        await manager.connect_to_chat(ws, "alice", "conv1", "c1")

        with patch("app.api.websockets.publish_event", side_effect=RuntimeError("mongo down")):
            await manager.send_chat_message({"type": "message"}, "conv1")

        # broker 故障退路：本进程投递兜底（聊天域另有落库 + 离线同步）
        self.assertEqual(len(ws.sent), 1)


# ---------------------------------------------------------------------------
# 双连接跨 worker 广播
# ---------------------------------------------------------------------------

class CrossWorkerBroadcastTests(BusTestCase):
    async def test_chat_frame_reaches_connections_on_both_workers_exactly_once(self):
        self.go_bus()
        # 两个 manager 实例模拟两个 uvicorn worker，共享同一 ws_events 总线
        manager_a = ConnectionManager()
        manager_b = ConnectionManager()
        ws_alice_on_a = FakeWebSocket()
        ws_bob_on_a = FakeWebSocket()
        ws_bob_on_b = FakeWebSocket()
        await manager_a.connect_to_chat(ws_alice_on_a, "alice", "conv1", "ca1")
        await manager_a.connect_to_chat(ws_bob_on_a, "bob", "conv1", "ca2")
        await manager_b.connect_to_chat(ws_bob_on_b, "bob", "conv1", "cb1")

        payload = {"type": "message", "message": {"id": "m1", "content": "hi"}}
        await manager_a.send_chat_message(dict(payload), "conv1")

        reader_a = EventBusReader(make_manager_deliverer(manager_a), self.db)
        reader_b = EventBusReader(make_manager_deliverer(manager_b), self.db)
        await reader_a.dispatch_available()
        await reader_b.dispatch_available()

        # worker A 上的 alice 与 bob、worker B 上的 bob 各收到一次
        self.assertEqual(ws_alice_on_a.sent, [payload])
        self.assertEqual(ws_bob_on_a.sent, [payload])
        self.assertEqual(ws_bob_on_b.sent, [payload])
        self.assertEqual(len(self.db.ws_events.docs), 1)  # 单条事件帧 fan-out

    async def test_notification_and_personal_frames_route_by_user_across_workers(self):
        self.go_bus()
        manager_a = ConnectionManager()
        manager_b = ConnectionManager()
        notif_bob_on_b = FakeWebSocket()
        personal_alice_on_a = FakeWebSocket()
        await manager_b.connect_to_notifications(notif_bob_on_b, "bob", "nb1")
        await manager_a.connect_to_notifications(personal_alice_on_a, "alice", "na1")

        notification = {"id": "n1", "title": "新消息"}
        await manager_a.send_notification(notification, "bob")
        count_frame = {"type": "notification_count", "count": 3}
        await manager_a.send_personal_message(count_frame, "alice")

        reader_a = EventBusReader(make_manager_deliverer(manager_a), self.db)
        reader_b = EventBusReader(make_manager_deliverer(manager_b), self.db)
        await reader_a.dispatch_available()
        await reader_b.dispatch_available()

        # 通知帧只投给目标用户的通知连接（跨 worker：发布在 A、连接在 B）
        self.assertEqual(notif_bob_on_b.sent, [{"type": "notification", "data": notification}])
        self.assertEqual(personal_alice_on_a.sent, [count_frame])
        # 非目标连接不串扰
        self.assertEqual(len(notif_bob_on_b.sent), 1)

    async def test_unknown_frame_kind_is_ignored_not_fanned_out(self):
        self.go_bus()
        manager = ConnectionManager()
        ws = FakeWebSocket()
        await manager.connect_to_chat(ws, "alice", "conv1", "c1")
        reader = EventBusReader(make_manager_deliverer(manager), self.db)
        await reader._deliver(make_frame(kind="mystery", target={"conversation_id": "conv1"}))
        # 未知 kind 不路由到任何连接（读侧告警后忽略）
        self.assertEqual(ws.sent, [])


# ---------------------------------------------------------------------------
# ws_events 循环游标回退（cursor 死亡 → 按 last _id 重连重放）
# ---------------------------------------------------------------------------

class ScriptedReader(EventBusReader):
    """按脚本逐个返回游标，脚本耗尽后回退到真实（假集合）开标。"""

    def __init__(self, cursors, **kwargs):
        super().__init__(**kwargs)
        self._script = list(cursors)

    def _open_cursor(self):
        if self._script:
            return self._script.pop(0)
        return super()._open_cursor()


class CursorRollbackReplayTests(BusTestCase):
    async def test_dead_cursor_replays_from_last_id_without_duplicates(self):
        e1 = make_frame(payload={"n": 1})
        e2 = make_frame(payload={"n": 2})
        e3 = make_frame(payload={"n": 3})
        self.db.ws_events.docs.extend([dict(e1), dict(e2), dict(e3)])

        delivered = []
        reader = ScriptedReader(
            [FakeCursor([dict(e1), dict(e2)], die_after=2)],  # 消费两条后被回卷 kill
            deliver=collect_deliveries(delivered), db=self.db,
        )

        with self.assertRaises(OperationFailure):
            await reader.dispatch_available()
        self.assertEqual([f["payload"]["n"] for f in delivered], [1, 2])
        self.assertEqual(reader.last_id, e2["_id"])

        # 模拟 capped 回卷覆盖了 e1（重放窗口外的丢失，聊天域有落库兜底）
        self.db.ws_events.docs = [d for d in self.db.ws_events.docs if d["_id"] != e1["_id"]]

        # 重连：_id > last_id 过滤天然去重——e1/e2 不重复投递，仅补到 e3
        self.assertEqual(await reader.dispatch_available(), 1)
        self.assertEqual([f["payload"]["n"] for f in delivered], [1, 2, 3])

        # 再次消费：无新事件、无重复
        self.assertEqual(await reader.dispatch_available(), 0)
        self.assertEqual(len(delivered), 3)

    async def test_run_loop_reconnects_and_can_be_cancelled(self):
        e1 = make_frame(payload={"n": 1})
        self.db.ws_events.docs.append(dict(e1))
        delivered = []
        reader = ScriptedReader(
            [FakeCursor([dict(e1)], die_after=1)],
            deliver=collect_deliveries(delivered), db=self.db, reconnect_delay=0.01,
        )
        task = asyncio.create_task(reader.run())
        await asyncio.sleep(0.05)  # 死亡 → 重连 → 空转若干轮
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self.assertEqual([f["payload"]["n"] for f in delivered], [1])

    async def test_first_cursor_starts_from_oldest_surviving_event(self):
        # 从未消费过的 worker（last_id=None）从最老的存活事件开始，不遗漏
        self.db.ws_events.docs.extend([dict(make_frame(payload={"n": i})) for i in range(3)])
        delivered = []
        reader = EventBusReader(collect_deliveries(delivered), self.db)
        self.assertEqual(await reader.dispatch_available(), 3)
        self.assertEqual([f["payload"]["n"] for f in delivered], [0, 1, 2])


# ---------------------------------------------------------------------------
# presence（S3 连接层部分）
# ---------------------------------------------------------------------------

class PresenceContractTests(BusTestCase):
    async def test_presence_doc_carries_ttl_and_heartbeat_fields(self):
        configure_bus(self.db, worker_id="w1")
        await upsert_presence(self.db, "w1", "alice", {"conv1", "conv2"})

        (doc,) = self.db.ws_presence.docs
        self.assertEqual(doc["user_id"], "alice")
        self.assertEqual(doc["worker_id"], "w1")
        self.assertEqual(doc["conversation_ids"], ["conv1", "conv2"])
        self.assertLess(doc["expires_at"] - doc["heartbeat_at"],
                        timedelta(seconds=PRESENCE_TTL_SECONDS + 1))

    async def test_empty_room_set_removes_presence_document(self):
        configure_bus(self.db, worker_id="w1")
        await upsert_presence(self.db, "w1", "alice", {"conv1"})
        await upsert_presence(self.db, "w1", "alice", set())
        self.assertEqual(self.db.ws_presence.docs, [])
        await remove_presence(self.db, "w1", "ghost")  # 不存在也不抛错

    async def test_expired_presence_documents_are_not_counted_online(self):
        configure_bus(self.db, worker_id="w1")
        fresh = {"user_id": "alice", "worker_id": "w1",
                 "conversation_ids": ["conv1"], "expires_at": datetime.utcnow() + timedelta(seconds=30)}
        expired = {"user_id": "bob", "worker_id": "w2",
                   "conversation_ids": ["conv1"], "expires_at": datetime.utcnow() - timedelta(seconds=1)}
        self.db.ws_presence.docs.extend([fresh, expired])
        rooms = await load_presence_rooms(self.db)
        # Mongo TTL 监控约 60s 一轮：读侧按 expires_at 过滤是权威判据
        self.assertEqual(rooms, {"conv1": {"alice"}})

    async def test_active_users_merge_local_connections_with_cross_worker_presence(self):
        self.go_bus()
        manager = ConnectionManager()
        ws = FakeWebSocket()
        await manager.connect_to_chat(ws, "alice", "conv1", "c1")
        # bob 实际连在另一 worker，经 presence 缓存进入名单
        manager.apply_presence_cache({"conv1": {"bob"}})
        self.assertEqual(manager.get_active_users_in_chat("conv1"), {"alice", "bob"})
        # 未出现的会话不受缓存串扰
        self.assertEqual(manager.get_active_users_in_chat("conv2"), set())

    async def test_local_mode_presence_cache_is_not_merged(self):
        manager = ConnectionManager()
        ws = FakeWebSocket()
        await manager.connect_to_chat(ws, "alice", "conv1", "c1")
        manager.apply_presence_cache({"conv1": {"bob"}})  # 即使被灌入也不合并
        self.assertEqual(manager.get_active_users_in_chat("conv1"), {"alice"})

    async def test_disconnect_syncs_presence_without_waiting_for_ttl(self):
        self.go_bus()
        manager = ConnectionManager()
        ws = FakeWebSocket()
        await manager.connect_to_chat(ws, "alice", "conv1", "c1")
        await manager.sync_user_presence("alice")
        self.assertEqual(len(self.db.ws_presence.docs), 1)

        manager.disconnect("alice", "c1")
        await asyncio.sleep(0.05)  # 让后台 presence 同步任务执行
        # 本 worker 已无房间：presence 立即删除（不等 90s TTL），无需手动触发
        self.assertEqual(self.db.ws_presence.docs, [])


# ---------------------------------------------------------------------------
# 真实副本集行为（tailable cursor / capped 回卷）——需隔离本地副本集
# ---------------------------------------------------------------------------

REPLICA_URI = os.environ.get("REHAB_TEST_REPLICA_URI")


@unittest.skipUnless(REPLICA_URI, "set REHAB_TEST_REPLICA_URI to an isolated local replica set")
class WsEventBusMongoTests(unittest.IsolatedAsyncioTestCase):
    """真实 capped 集合上的读侧行为（参照 deploy/mongodb/README.md 的隔离副本集）。

    每个用例使用独立随机库（rehab_ws_ 前缀），结束后删除；不要指向业务实例。
    """

    def setUp(self):
        if not REPLICA_URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")):
            self.fail("test URI must use a local explicit port")

    async def asyncSetUp(self):
        from motor.motor_asyncio import AsyncIOMotorClient
        self.client = AsyncIOMotorClient(REPLICA_URI, serverSelectionTimeoutMS=3000)
        self.db = self.client["rehab_ws_" + uuid4().hex]
        self.mode_patch = patch.object(settings, "EVENT_BUS_MODE", "bus")
        self.mode_patch.start()
        configure_bus(self.db, worker_id="mongo-test-worker")

    async def asyncTearDown(self):
        self.mode_patch.stop()
        reset_bus()
        await self.client.drop_database(self.db.name)
        self.client.close()

    async def _wait_for(self, predicate, timeout=5.0, interval=0.02):
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            if predicate():
                return
            await asyncio.sleep(interval)
        self.fail("condition not met within timeout")

    async def test_capped_bootstrap_and_cross_worker_delivery_on_real_replica_set(self):
        await ensure_ws_collections(self.db)

        # capped 选项在真实集合上生效（§7-6：1MB）
        options = {info["name"]: info for info in await self.db.list_collections()}
        ws_events_options = options[WS_EVENTS_COLLECTION].get("options", {})
        self.assertTrue(ws_events_options.get("capped"))
        self.assertEqual(ws_events_options.get("size"), WS_EVENTS_CAP_BYTES)

        # 两个"worker"各自的读侧任务消费同一真实集合
        manager_a, manager_b = ConnectionManager(), ConnectionManager()
        ws_bob_on_b = FakeWebSocket()
        await manager_b.connect_to_chat(ws_bob_on_b, "bob", "conv1", "cb1")
        reader_a = EventBusReader(make_manager_deliverer(manager_a), self.db)
        reader_b = EventBusReader(make_manager_deliverer(manager_b), self.db)
        task_a = asyncio.create_task(reader_a.run())
        task_b = asyncio.create_task(reader_b.run())
        try:
            # 读侧就绪后发布（发布者所在 worker 与收件人所在 worker 不同）
            await asyncio.sleep(0.1)
            payloads = [{"type": "message", "message": {"id": f"m{i}"}} for i in range(3)]
            for payload in payloads:
                await manager_a.send_chat_message(dict(payload), "conv1")

            await self._wait_for(lambda: len(ws_bob_on_b.sent) == 3)
            self.assertEqual(ws_bob_on_b.sent, payloads)  # 顺序一致、各一次
        finally:
            task_a.cancel()
            task_b.cancel()
            await asyncio.gather(task_a, task_b, return_exceptions=True)

    async def test_capped_rollover_replays_from_oldest_surviving_event(self):
        # 4KB 小 capped 集合：写入足够多事件后最早的被覆盖（模拟慢消费者回卷）
        await self.db.create_collection("ws_events_probe", capped=True, size=4096)

        inserted_ids = []
        for i in range(20):
            result = await self.db.ws_events_probe.insert_one(
                make_frame(payload={"n": i, "pad": "x" * 400}))
            inserted_ids.append(result.inserted_id)

        delivered = []
        reader = EventBusReader(collect_deliveries(delivered), self.db,
                                collection="ws_events_probe")
        task = asyncio.create_task(reader.run())
        try:
            # last_id=None 的全新消费者从最老的存活事件开始，逐条投递且不重复
            await self._wait_for(
                lambda: len({str(f["_id"]) for f in delivered}) == len(delivered)
                and len(delivered) > 0 and reader.last_id == inserted_ids[-1],
                timeout=8.0)
            await asyncio.sleep(0.2)  # 留出空转窗口，确认无重复回灌

            delivered_ids = [str(f["_id"]) for f in delivered]
            self.assertEqual(len(delivered_ids), len(set(delivered_ids)))
            self.assertNotIn(str(inserted_ids[0]), delivered_ids)  # 最早事件已被覆盖
            # 从最老存活事件开始（4KB 小集合内 20 条中前若干条已被回卷覆盖）
            survivors_cursor = self.db.ws_events_probe.find({})
            survivors = [doc async for doc in survivors_cursor]
            oldest_surviving = min(doc["_id"] for doc in survivors)
            self.assertEqual(delivered_ids[0], str(oldest_surviving))
            self.assertEqual(reader.last_id, inserted_ids[-1])
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


if __name__ == "__main__":
    unittest.main()
