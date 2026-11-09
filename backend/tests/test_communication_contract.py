"""
WS01 通信契约测试

覆盖：
- REST 发消息落库形状（结构 B：participant1_id/participant2_id、read/deleted、recipient_id）
- client_message_id 幂等键（D4 追认冻结：HTTP 与 WS 入站同键，重复投递返回既有消息不重复落库）
- WS：非成员入房被拒（close 4403 / NOT_CONVERSATION_PARTICIPANT）、
  成员发消息落库且广播载荷带真实服务端 id、重复 client_message_id 幂等
- WS03 已读回执：read_receipt 帧真实落库 + 广播形状（conversation_id/reader_id/
  message_ids/read_at）、非成员拒绝、落库失败错误帧不广播、
  read_at 谓词怪癖修正（广播不依赖墙钟秒边界）
- D3 ConversationPolicy（默认采纳待评审追认 2026-11-09）：有效账号 + 会话参与者
  同一规则覆盖入站/出站；D1 目标形态 participants 数组兼容读
- D6 删除语义（默认采纳待评审追认 2026-11-09）：软删除、双方会话内不可见、
  保留审计与原文引用完整性、不硬删
- D7 事件信封：message / read_receipt / delete_message 帧携带 server_seq
  （_id 大端单调整数，插入型事件重放稳定）
- 启动集合边界：普通启动不隐式建集合，索引声明跳过空库，
  首个消息落库惰性补建索引（test_demo_auth_boundary 回归的契约面）
- 死代码删除后 import app.main 正常（本模块顶部 import 即隐式覆盖）
"""
import asyncio
import os
import re
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError
from starlette.testclient import WebSocketDisconnect

from app.core.auth import get_current_active_user
from app.db.indexes import ensure_communication_indexes
from app.db.mongodb import get_database
from app.main import app
from app.services.communication_service import CommunicationService
from app.schemas.user import UserResponse

OBJECT_ID_PATTERN = re.compile(r"^[0-9a-f]{24}$")


def authenticated_user(doc):
    """Authentication's real contract is a response model, not a Mongo dictionary."""
    return UserResponse(id=str(doc["_id"]), email=doc.get("email", "actor@example.com"),
        name=doc["name"], role=doc["role"], is_active=True,
        createdAt=datetime.utcnow(), updatedAt=datetime.utcnow())


def run(coro):
    """在同步测试中执行一段异步逻辑（FakeDB 与事件循环无绑定）。"""
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# 内存版 Mongo 桩：仅实现通信域用到的最小查询/更新能力
# ---------------------------------------------------------------------------

def _field_matches(doc, key, expected):
    value = doc
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            value = None
            break
        value = value[part]
    if isinstance(expected, dict) and any(op.startswith("$") for op in expected):
        for op, operand in expected.items():
            if op == "$ne" and value == operand:
                return False
            if op == "$in" and value not in operand:
                return False
            if op == "$gt" and not (value is not None and value > operand):
                return False
            if op == "$gte" and not (value is not None and value >= operand):
                return False
            if op == "$lt" and not (value is not None and value < operand):
                return False
        return True
    if value == expected:
        return True
    # ObjectId 与字符串形式的 _id 互相兼容
    return str(value) == str(expected)


def _matches(doc, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(doc, sub) for sub in expected):
                return False
        elif key == "$and":
            if not all(_matches(doc, sub) for sub in expected):
                return False
        else:
            if not _field_matches(doc, key, expected):
                return False
    return True


class FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, field, direction):
        self._docs.sort(
            key=lambda d: d.get(field) or datetime.min,
            reverse=direction < 0,
        )
        return self

    def skip(self, n):
        self._docs = self._docs[n:]
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, length=None):
        return list(self._docs)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._docs:
            raise StopAsyncIteration
        return self._docs.pop(0)


class FakeCollection:
    def __init__(self):
        self.docs = []
        self.indexes = []  # create_index 调用记录：(keys, kwargs)

    async def create_index(self, keys, **kwargs):
        self.indexes.append((list(keys), dict(kwargs)))
        return kwargs.get("name", "_".join(f"{k}_{d}" for k, d in keys))

    async def find_one(self, query):
        for doc in self.docs:
            if _matches(doc, query):
                return dict(doc)
        return None

    async def insert_one(self, doc):
        stored = dict(doc)
        self.docs.append(stored)
        return SimpleNamespace(inserted_id=stored.get("_id"))

    async def update_one(self, query, update):
        modified = 0
        for doc in self.docs:
            if _matches(doc, query):
                doc.update(update.get("$set", {}))
                modified += 1
        return SimpleNamespace(modified_count=modified)

    async def update_many(self, query, update):
        modified = 0
        for doc in self.docs:
            if _matches(doc, query):
                doc.update(update.get("$set", {}))
                modified += 1
        return SimpleNamespace(modified_count=modified)

    async def count_documents(self, query):
        return sum(1 for doc in self.docs if _matches(doc, query))

    def find(self, query):
        return FakeCursor([dict(doc) for doc in self.docs if _matches(doc, query)])


class FakeDB:
    def __init__(self):
        self.conversations = FakeCollection()
        self.messages = FakeCollection()
        self.users = FakeCollection()
        self.notifications = FakeCollection()

    def __getattr__(self, name):
        collection = FakeCollection()
        setattr(self, name, collection)
        return collection

    def __getitem__(self, name):
        return self.__getattr__(name)

    async def list_collection_names(self):
        # 只返回真实存在的集合（模拟 Mongo 语义：未写入/未显式创建的集合不存在）。
        return [name for name, value in self.__dict__.items()
                if isinstance(value, FakeCollection)]

    async def create_collection(self, name):
        return self.__getattr__(name)


def make_user(name, role):
    return {"_id": ObjectId(), "name": name, "role": role, "is_active": True}


def seed_conversation(db, user_a, user_b):
    """直接构造一条结构 B 会话文档，返回 conversation_id。"""
    conversation_id = str(ObjectId())
    db.conversations.docs.append({
        "_id": ObjectId(conversation_id),
        "participant1_id": str(user_a["_id"]),
        "participant2_id": str(user_b["_id"]),
        "type": "chat",
        "status": "active",
        "created_at": datetime.utcnow(),
        "last_message_time": datetime.utcnow(),
        "last_message_preview": "",
        "metadata": {},
    })
    return conversation_id


class UniqueRaceCollection(FakeCollection):
    """模拟并发窗口下的唯一索引行为：

    - 先查后插的幂等快路径 find_one 可被并发写绕过（suppress_next_find_one）；
    - insert_one 撞 (conversation_id, sender_id, client_message_id) 唯一索引时
      抛 DuplicateKeyError（仅对携带 client_message_id 的文档约束，对应 partial 谓词）。
    """

    def __init__(self):
        super().__init__()
        self.suppress_next_find_one = False

    async def find_one(self, query):
        if self.suppress_next_find_one:
            self.suppress_next_find_one = False
            return None
        return await super().find_one(query)

    async def insert_one(self, doc):
        if doc.get("client_message_id"):
            for existing in self.docs:
                if (existing.get("conversation_id"), existing.get("sender_id"),
                        existing.get("client_message_id")) == \
                        (doc["conversation_id"], doc["sender_id"], doc["client_message_id"]):
                    raise DuplicateKeyError("E11000 duplicate key")
        return await super().insert_one(doc)


class ExplodingUpdateManyCollection(FakeCollection):
    """模拟 mark 路径数据库故障：update_many 一律抛错（find 正常）。"""

    async def update_many(self, query, update):
        raise RuntimeError("db down")


# ---------------------------------------------------------------------------
# REST 契约
# ---------------------------------------------------------------------------

class RestCommunicationContractTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        app.dependency_overrides.clear()

    async def test_send_message_persists_structure_b_shape(self):
        db = FakeDB()
        alice = make_user("Alice", "doctor")
        bob = make_user("Bob", "patient")
        db.users.docs.extend([dict(alice), dict(bob)])
        conversation_id = seed_conversation(db, alice, bob)
        app.dependency_overrides[get_database] = lambda: db

        stored = db.conversations.docs[0]
        # 会话形状：participant1_id/participant2_id 双人约定，无 participants 数组
        self.assertEqual(stored["participant1_id"], str(alice["_id"]))
        self.assertEqual(stored["participant2_id"], str(bob["_id"]))
        self.assertNotIn("participants", stored)
        self.assertNotIn("is_group", stored)

        async def fake_current_user():
            return authenticated_user(alice)

        app.dependency_overrides[get_current_active_user] = fake_current_user
        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            # 单参与者约定：创建会话只带 participant_id，服务端补当前用户为参与者
            created = await client.post(
                "/api/communications/conversations",
                json={"participant_id": str(bob["_id"]), "type": "chat"},
            )
            self.assertEqual(created.status_code, 201)
            self.assertEqual(created.json(), {"id": conversation_id})  # 既有会话去重复用

            sent = await client.post(
                f"/api/communications/conversations/{conversation_id}/messages",
                json={"content": "hello", "type": "text", "client_message_id": "rest-1"},
            )
            self.assertEqual(sent.status_code, 201)
            body = sent.json()
            self.assertEqual(body["conversation_id"], conversation_id)
            self.assertEqual(body["sender_id"], str(alice["_id"]))
            self.assertEqual(body["recipient_id"], str(bob["_id"]))
            self.assertEqual(body["content"], "hello")
            self.assertEqual(body["read"], False)
            self.assertEqual(body["deleted"], False)
            self.assertEqual(body["client_message_id"], "rest-1")
            self.assertRegex(body["id"], OBJECT_ID_PATTERN)
            self.assertIsNotNone(datetime.fromisoformat(body["timestamp"]))

        # 落库文档形状
        self.assertEqual(len(db.messages.docs), 1)
        doc = db.messages.docs[0]
        self.assertEqual(doc["conversation_id"], conversation_id)
        self.assertEqual(doc["sender_id"], str(alice["_id"]))
        self.assertEqual(doc["recipient_id"], str(bob["_id"]))
        self.assertEqual(doc["read"], False)
        self.assertEqual(doc["deleted"], False)
        self.assertEqual(doc["client_message_id"], "rest-1")
        self.assertIn("timestamp", doc)
        # 会话摘要已更新
        self.assertEqual(db.conversations.docs[0]["last_message_preview"], "hello")

    async def test_duplicate_client_message_id_over_http_is_idempotent(self):
        """D4 追认冻结（默认采纳待评审追认 2026-11-09）：HTTP 重试同键投递
        返回既有消息，不重复落库、不重复产生副作用。"""
        db = FakeDB()
        alice = make_user("Alice", "doctor")
        bob = make_user("Bob", "patient")
        db.users.docs.extend([dict(alice), dict(bob)])
        conversation_id = seed_conversation(db, alice, bob)
        app.dependency_overrides[get_database] = lambda: db
        app.dependency_overrides[get_current_active_user] = lambda: authenticated_user(alice)

        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            payload = {"content": "retry me", "client_message_id": "http-idem-1"}
            first = await client.post(
                f"/api/communications/conversations/{conversation_id}/messages",
                json=payload,
            )
            replay = await client.post(
                f"/api/communications/conversations/{conversation_id}/messages",
                json=payload,
            )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(first.json()["id"], replay.json()["id"])
        self.assertEqual(first.json()["client_message_id"], "http-idem-1")
        self.assertEqual(len(db.messages.docs), 1)
        # 幂等重放不产生新副作用（仅首次落库创建 1 条离线通知，D10 桥；摘要不变）
        self.assertEqual(len(db.notifications.docs), 1)
        self.assertEqual(db.conversations.docs[0]["last_message_preview"], "retry me")

    async def test_conversation_membership_is_enforced_for_http_send(self):
        db = FakeDB()
        alice = make_user("Alice", "doctor")
        mallory = make_user("Mallory", "doctor")
        bob = make_user("Bob", "patient")
        db.users.docs.extend([dict(alice), dict(bob)])
        conversation_id = seed_conversation(db, alice, bob)
        app.dependency_overrides[get_database] = lambda: db

        async def fake_current_user():
            return authenticated_user(mallory)

        app.dependency_overrides[get_current_active_user] = fake_current_user
        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                f"/api/communications/conversations/{conversation_id}/messages",
                json={"content": "intrude"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(db.messages.docs), 0)


# ---------------------------------------------------------------------------
# 幂等键契约（HTTP/WS 共用 CommunicationService.send_message）
# ---------------------------------------------------------------------------

class ClientMessageIdIdempotencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_client_message_id_returns_existing_message_without_reinsert(self):
        db = FakeDB()
        alice = make_user("Alice", "doctor")
        bob = make_user("Bob", "patient")
        # D3 策略要求发送者为有效账号
        db.users.docs.extend([dict(alice), dict(bob)])
        conversation_id = seed_conversation(db, alice, bob)

        first = await CommunicationService.send_message(
            db, conversation_id, str(alice["_id"]), "once",
            client_message_id="idem-1",
        )
        second = await CommunicationService.send_message(
            db, conversation_id, str(alice["_id"]), "once",
            client_message_id="idem-1",
        )

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["timestamp"], second["timestamp"])
        self.assertEqual(len(db.messages.docs), 1)
        self.assertEqual(db.messages.docs[0]["client_message_id"], "idem-1")
        # 幂等重放不产生新副作用：仅首次落库创建 1 条离线通知（D10 桥）
        self.assertEqual(len(db.notifications.docs), 1)

    async def test_same_key_from_other_sender_or_conversation_is_not_deduplicated(self):
        db = FakeDB()
        alice = make_user("Alice", "doctor")
        bob = make_user("Bob", "patient")
        carol = make_user("Carol", "doctor")
        db.users.docs.extend([dict(alice), dict(bob), dict(carol)])
        conversation_ab = seed_conversation(db, alice, bob)
        conversation_ac = seed_conversation(db, alice, carol)

        m1 = await CommunicationService.send_message(
            db, conversation_ab, str(alice["_id"]), "a", client_message_id="key",
        )
        # 不同发送者同键：不去重
        m2 = await CommunicationService.send_message(
            db, conversation_ab, str(bob["_id"]), "b", client_message_id="key",
        )
        # 不同会话同键：不去重
        m3 = await CommunicationService.send_message(
            db, conversation_ac, str(alice["_id"]), "c", client_message_id="key",
        )
        self.assertEqual(len({m1["id"], m2["id"], m3["id"]}), 3)
        self.assertEqual(len(db.messages.docs), 3)

    async def test_non_member_send_via_service_is_rejected(self):
        db = FakeDB()
        alice = make_user("Alice", "doctor")
        bob = make_user("Bob", "patient")
        mallory = make_user("Mallory", "doctor")
        conversation_id = seed_conversation(db, alice, bob)

        with self.assertRaises(ValueError):
            await CommunicationService.send_message(
                db, conversation_id, str(mallory["_id"]), "intrude",
            )
        self.assertEqual(len(db.messages.docs), 0)


# ---------------------------------------------------------------------------
# WS01-c：唯一索引基建 / _id 分页 / DuplicateKeyError 兜底
# ---------------------------------------------------------------------------

def make_message_doc(conversation_id, sender_id, recipient_id, content,
                     cmid=None, timestamp=None, oid=None):
    doc = {
        "_id": oid or ObjectId(),
        "conversation_id": conversation_id,
        "sender_id": sender_id,
        "recipient_id": recipient_id,
        "content": content,
        "type": "text",
        "timestamp": timestamp or datetime.utcnow(),
        "read": False,
        "deleted": False,
        "attachments": [],
        "metadata": {},
    }
    if cmid:
        doc["client_message_id"] = cmid
    return doc


class CommunicationIndexDefinitionTests(unittest.IsolatedAsyncioTestCase):
    async def test_idempotency_index_is_partial_unique_on_triple_key(self):
        db = FakeDB()
        await ensure_communication_indexes(db)

        (keys, kwargs), = db.messages.indexes
        self.assertEqual(
            keys,
            [("conversation_id", 1), ("sender_id", 1), ("client_message_id", 1)],
        )
        self.assertTrue(kwargs["unique"])
        # partial 谓词：仅对携带 client_message_id 的文档生效，无键历史文档不受约束
        self.assertEqual(
            kwargs["partialFilterExpression"],
            {"client_message_id": {"$exists": True}},
        )
        self.assertEqual(kwargs["name"], "uniq_conversation_sender_client_message_id")

    async def test_index_creation_is_mounted_in_startup(self):
        import inspect
        import app.main as main_module
        source = inspect.getsource(main_module.startup_db_client)
        self.assertIn("ensure_communication_indexes", source)


class UniqueIndexRaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_key_error_returns_existing_message_without_reinsert(self):
        db = FakeDB()
        db.messages = UniqueRaceCollection()
        alice = make_user("Alice", "doctor")
        bob = make_user("Bob", "patient")
        db.users.docs.extend([dict(alice), dict(bob)])
        conversation_id = seed_conversation(db, alice, bob)

        # 并发窗口：另一请求已落库同键消息，本请求的先查后插被绕过
        concurrent_doc = make_message_doc(
            conversation_id, str(alice["_id"]), str(bob["_id"]), "race",
            cmid="race-1",
        )
        db.messages.docs.append(concurrent_doc)
        db.messages.suppress_next_find_one = True

        replay = await CommunicationService.send_message(
            db, conversation_id, str(alice["_id"]), "race",
            client_message_id="race-1",
        )

        self.assertEqual(replay["id"], str(concurrent_doc["_id"]))
        self.assertEqual(replay["client_message_id"], "race-1")
        self.assertEqual(len(db.messages.docs), 1)  # 不重复落库
        self.assertEqual(len(db.notifications.docs), 0)  # 重放不产生通知副作用
        # 不更新会话摘要
        self.assertEqual(db.conversations.docs[0]["last_message_preview"], "")


class ObjectIdPaginationTests(unittest.IsolatedAsyncioTestCase):
    async def test_before_id_pagination_orders_by_objectid_immune_to_timestamp_drift(self):
        db = FakeDB()
        alice = make_user("Alice", "doctor")
        bob = make_user("Bob", "patient")
        db.users.docs.extend([dict(alice), dict(bob)])
        conversation_id = seed_conversation(db, alice, bob)

        # 时间戳故意与 _id 顺序相反：模拟历史本地时区文档与 UTC 文档交界处的漂移。
        # 按 _id 分页必须完全无视 timestamp 值。
        for i in range(5):
            db.messages.docs.append(make_message_doc(
                conversation_id, str(alice["_id"]), str(bob["_id"]), f"m{i}",
                timestamp=datetime(2026, 1, 1) + timedelta(minutes=100 - i),
                oid=ObjectId(),
            ))

        collected = []
        before = None
        while True:
            page = await CommunicationService.get_messages(
                db, conversation_id, str(alice["_id"]), limit=2, before_id=before,
            )
            if not page:
                break
            # 页内按 _id 升序
            page_ids = [ObjectId(m["id"]) for m in page]
            self.assertEqual(page_ids, sorted(page_ids))
            collected.extend(page)
            before = page[0]["id"]  # 页首（最早一条）作为下一页游标
            self.assertLessEqual(len(collected), 5)

        self.assertEqual(len(collected), 5)
        collected.sort(key=lambda m: ObjectId(m["id"]))
        self.assertEqual([m["content"] for m in collected],
                         ["m0", "m1", "m2", "m3", "m4"])

    async def test_sync_offline_messages_uses_objectid_cursor(self):
        db = FakeDB()
        alice = make_user("Alice", "doctor")
        bob = make_user("Bob", "patient")
        db.users.docs.extend([dict(alice), dict(bob)])
        conversation_id = seed_conversation(db, alice, bob)

        cutoff = datetime(2026, 1, 1, 12, 0, 0)
        # _id 早于游标但 timestamp 晚于 cutoff：按 timestamp 会误判为"新消息"
        old_id_early = make_message_doc(
            conversation_id, str(alice["_id"]), str(bob["_id"]), "old",
            timestamp=datetime(2026, 3, 1),
            oid=ObjectId.from_datetime(cutoff - timedelta(hours=1)),
        )
        # _id 晚于游标但 timestamp 早于 cutoff：按 timestamp 会漏掉
        new_id_late = make_message_doc(
            conversation_id, str(alice["_id"]), str(bob["_id"]), "new",
            timestamp=datetime(2025, 12, 1),
            oid=ObjectId.from_datetime(cutoff + timedelta(hours=1)),
        )
        db.messages.docs.extend([old_id_early, new_id_late])

        result = await CommunicationService.sync_offline_messages(
            db, str(bob["_id"]), cutoff,
        )

        self.assertEqual([m["content"] for m in result], ["new"])


# ---------------------------------------------------------------------------
# WS03 已读回执（服务层：mark_conversation_as_read / mark_message_as_read）
# ---------------------------------------------------------------------------

class _StubManager:
    """捕获服务层广播的连接管理器桩。"""

    def __init__(self):
        self.sent = []

    async def send_chat_message(self, message, conversation_id):
        self.sent.append((message, conversation_id))

    def get_active_users_in_chat(self, conversation_id):
        return set()


class _ScriptedDatetime:
    """按脚本逐次返回 utcnow()，超次数调用即失败——用于钉死
    mark_conversation_as_read 不再调用第二个 utcnow 构造时间谓词。"""

    def __init__(self, moments):
        self._moments = list(moments)

    def utcnow(self):
        if not self._moments:
            raise AssertionError(
                "utcnow 被调用次数超出脚本：疑似重新引入双时钟 read_at 谓词"
            )
        return self._moments.pop(0)


class MarkConversationAsReadTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = FakeDB()
        self.alice = make_user("Alice", "doctor")
        self.bob = make_user("Bob", "patient")
        self.conversation_id = seed_conversation(self.db, self.alice, self.bob)
        # D3 策略：已读路径要求操作者为有效账号
        self.db.users.docs.extend([dict(self.alice), dict(self.bob)])
        self.manager = _StubManager()
        self.manager_patch = patch(
            "app.api.websockets.get_connection_manager",
            return_value=self.manager,
        )
        self.manager_patch.start()

    def tearDown(self):
        self.manager_patch.stop()

    async def test_marks_only_unread_messages_addressed_to_reader(self):
        unread_1 = make_message_doc(
            self.conversation_id, str(self.bob["_id"]), str(self.alice["_id"]), "u1")
        unread_2 = make_message_doc(
            self.conversation_id, str(self.bob["_id"]), str(self.alice["_id"]), "u2")
        already_read = make_message_doc(
            self.conversation_id, str(self.bob["_id"]), str(self.alice["_id"]), "r")
        already_read["read"] = True
        old_read_at = datetime(2025, 1, 1)
        already_read["read_at"] = old_read_at
        # 发给 bob 的消息：alice 标已读不得波及
        to_bob = make_message_doc(
            self.conversation_id, str(self.alice["_id"]), str(self.bob["_id"]), "to-bob")
        self.db.messages.docs.extend([unread_1, unread_2, already_read, to_bob])

        marked = await CommunicationService.mark_conversation_as_read(
            self.db, self.conversation_id, str(self.alice["_id"]),
        )

        self.assertEqual(marked, 2)  # REST 路由 marked_count 契约：返回 int
        self.assertEqual(len(self.manager.sent), 1)
        broadcast, broadcast_conversation_id = self.manager.sent[0]
        self.assertEqual(broadcast_conversation_id, self.conversation_id)
        # 广播形状：conversation_id / reader_id / message_ids / read_at
        self.assertEqual(broadcast["type"], "read_receipt")
        self.assertEqual(broadcast["conversation_id"], self.conversation_id)
        self.assertEqual(broadcast["reader_id"], str(self.alice["_id"]))
        self.assertEqual(
            sorted(broadcast["message_ids"]),
            sorted([str(unread_1["_id"]), str(unread_2["_id"])]),
        )
        self.assertIsNotNone(datetime.fromisoformat(broadcast["read_at"]))

        # 落库：仅发给 alice 的未读消息被标记
        self.assertTrue(unread_1["read"])
        self.assertTrue(unread_2["read"])
        self.assertIsInstance(unread_1["read_at"], datetime)
        # 已读消息不被触碰（read_at 保持原值）
        self.assertEqual(already_read["read_at"], old_read_at)
        # 发给 bob 的消息不受 alice 的已读操作影响
        self.assertFalse(to_bob["read"])

    async def test_get_then_explicit_mark_emits_receipt_once(self):
        message = make_message_doc(
            self.conversation_id, str(self.bob["_id"]), str(self.alice["_id"]), "m")
        self.db.messages.docs.append(message)
        messages = await CommunicationService.get_messages(
            self.db, self.conversation_id, str(self.alice["_id"]))
        marked = await CommunicationService.mark_conversation_as_read(
            self.db, self.conversation_id, str(self.alice["_id"]))
        self.assertTrue(messages[0]["read"])
        self.assertEqual(messages[0]["read_at"], message["read_at"].isoformat())
        self.assertEqual(marked, 0)
        self.assertEqual(len(self.manager.sent), 1)
        self.assertEqual(self.manager.sent[0][0]["message_ids"], [str(message["_id"])])

    async def test_duplicate_single_mark_preserves_first_read_time(self):
        message = make_message_doc(
            self.conversation_id, str(self.bob["_id"]), str(self.alice["_id"]), "m")
        self.db.messages.docs.append(message)
        for _ in range(2):
            self.assertTrue(await CommunicationService.mark_message_as_read(
                self.db, str(message["_id"]), str(self.alice["_id"])))
            if len(self.manager.sent) == 1:
                first_read_at = self.manager.sent[0][0]["read_at"]
        self.assertEqual(message["read_at"].isoformat(), first_read_at)
        self.assertEqual(len(self.manager.sent), 1)

    async def test_rest_read_operations_deny_removed_member_without_changes(self):
        message = make_message_doc(
            self.conversation_id, str(self.bob["_id"]), str(self.alice["_id"]), "m")
        self.db.messages.docs.append(message)
        self.db.conversations.docs.clear()
        app.dependency_overrides[get_database] = lambda: self.db
        app.dependency_overrides[get_current_active_user] = lambda: authenticated_user(self.alice)
        try:
            async with httpx.AsyncClient(app=app, base_url="http://test") as client:
                for endpoint in [f"conversations/{self.conversation_id}", f"messages/{message['_id']}"]:
                    response = await client.put(f"/api/communications/{endpoint}/read")
                    self.assertEqual(response.status_code, 403)
        finally:
            app.dependency_overrides.clear()
        self.assertFalse(message["read"])
        self.assertEqual(self.manager.sent, [])

    async def test_noop_when_no_unread_messages(self):
        marked = await CommunicationService.mark_conversation_as_read(
            self.db, self.conversation_id, str(self.alice["_id"]),
        )
        self.assertEqual(marked, 0)
        self.assertEqual(self.manager.sent, [])

    async def test_broadcast_does_not_depend_on_second_boundary(self):
        """read_at 怪癖回归测试：更新在 10:00:00.900 落库、旧实现若在下一秒
        （10:00:01.000 截断后）反查将一无所获导致广播静默丢失；修正后
        广播基于更新前取好的 _id 列表，且整个过程只调用一次 utcnow。"""
        unread = make_message_doc(
            self.conversation_id, str(self.bob["_id"]), str(self.alice["_id"]), "u1")
        self.db.messages.docs.append(unread)

        update_moment = datetime(2026, 1, 1, 10, 0, 0, 900000)
        scripted = _ScriptedDatetime([update_moment])
        with patch("app.services.communication_service.datetime", scripted):
            marked = await CommunicationService.mark_conversation_as_read(
                self.db, self.conversation_id, str(self.alice["_id"]),
            )

        self.assertEqual(marked, 1)
        self.assertEqual(len(self.manager.sent), 1)
        broadcast, _ = self.manager.sent[0]
        self.assertEqual(broadcast["message_ids"], [str(unread["_id"])])
        self.assertEqual(broadcast["read_at"], update_moment.isoformat())
        self.assertEqual(unread["read_at"], update_moment)

    async def test_mark_message_as_read_broadcasts_same_shape(self):
        message = make_message_doc(
            self.conversation_id, str(self.bob["_id"]), str(self.alice["_id"]), "m")
        self.db.messages.docs.append(message)

        success = await CommunicationService.mark_message_as_read(
            self.db, str(message["_id"]), str(self.alice["_id"]),
        )

        self.assertTrue(success)
        self.assertEqual(len(self.manager.sent), 1)
        broadcast, broadcast_conversation_id = self.manager.sent[0]
        self.assertEqual(broadcast_conversation_id, self.conversation_id)
        self.assertEqual(broadcast["type"], "read_receipt")
        self.assertEqual(broadcast["conversation_id"], self.conversation_id)
        self.assertEqual(broadcast["reader_id"], str(self.alice["_id"]))
        self.assertEqual(broadcast["message_ids"], [str(message["_id"])])
        self.assertTrue(message["read"])

    async def test_mark_message_as_read_rejects_message_addressed_to_other(self):
        message = make_message_doc(
            self.conversation_id, str(self.alice["_id"]), str(self.bob["_id"]), "m")
        self.db.messages.docs.append(message)

        # alice 不是该消息的接收者：不落库、不广播
        success = await CommunicationService.mark_message_as_read(
            self.db, str(message["_id"]), str(self.alice["_id"]),
        )
        self.assertFalse(success)
        self.assertEqual(self.manager.sent, [])
        self.assertFalse(message["read"])


# ---------------------------------------------------------------------------
# WS 契约（/ws/chat/{conversation_id}）
# ---------------------------------------------------------------------------

_ws_routes_registered = False


def _ensure_ws_routes():
    """main.py 在 startup 事件里注册 WS 路由；测试不走 lifespan，手动注册一次。"""
    global _ws_routes_registered
    if not _ws_routes_registered:
        from app.api.websockets import setup_websockets
        setup_websockets(app)
        _ws_routes_registered = True


class WebSocketChatContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_ws_routes()

    def setUp(self):
        self.client = TestClient(app)
        self.db = FakeDB()
        self.alice = make_user("Alice", "doctor")
        self.bob = make_user("Bob", "patient")
        self.mallory = make_user("Mallory", "doctor")
        self.db.users.docs.extend([dict(self.alice), dict(self.bob)])
        self.conversation_id = seed_conversation(self.db, self.alice, self.bob)
        app.dependency_overrides[get_database] = lambda: self.db

    def tearDown(self):
        app.dependency_overrides.pop(get_database, None)

    def connect(self, user):
        """以给定用户身份建立 WS 连接（鉴权走补丁注入，须在会话存续期间生效）。"""
        ws_patch = patch(
            "app.api.websockets.get_current_user_ws",
            new=AsyncMock(return_value=user),
        )
        ws_patch.start()
        session = self.client.websocket_connect(
            f"/ws/chat/{self.conversation_id}?token=stub"
        )
        # 把补丁的退出挂到会话上下文退出之后
        class _Session:
            def __enter__(self):
                return session.__enter__()

            def __exit__(self, *exc):
                try:
                    return session.__exit__(*exc)
                finally:
                    ws_patch.stop()

        return _Session()

    @staticmethod
    def skip_join(ws):
        """入房后会先收到 user_joined 帧（含本人），跳过直到出现业务帧。"""
        while True:
            frame = ws.receive_json()
            if frame["type"] != "user_joined":
                return frame

    @staticmethod
    def receive_close(ws):
        """读取服务端关闭帧（TestClient 下 receive() 以原始消息返回 close）。"""
        frame = ws.receive()
        assert frame["type"] == "websocket.close", f"expected close, got: {frame}"
        return SimpleNamespace(code=frame.get("code", 1000), reason=frame.get("reason", ""))

    def test_non_member_is_rejected_on_connect(self):
        with self.connect(self.mallory) as ws:
            error = ws.receive_json()
            self.assertEqual(error["type"], "error")
            self.assertEqual(error["error_code"], "NOT_CONVERSATION_PARTICIPANT")
            disconnect = self.receive_close(ws)
        self.assertEqual(disconnect.code, 4403)
        self.assertEqual(len(self.db.messages.docs), 0)

    def test_member_message_is_persisted_and_broadcast_with_real_id(self):
        with self.connect(self.alice) as ws:
            ws.send_json({
                "type": "message",
                "content": "hello ws",
                "client_message_id": "ws-1",
            })
            # 第一帧为落库成功后的聊天室广播（真实服务端 id / UTC 时间戳）
            broadcast = self.skip_join(ws)
            self.assertEqual(broadcast["type"], "message")
            message = broadcast["message"]
            self.assertRegex(message["id"], OBJECT_ID_PATTERN)
            self.assertEqual(message["conversation_id"], self.conversation_id)
            self.assertEqual(message["sender_id"], str(self.alice["_id"]))
            self.assertEqual(message["recipient_id"], str(self.bob["_id"]))
            self.assertEqual(message["content"], "hello ws")
            self.assertIsNotNone(datetime.fromisoformat(message["timestamp"]))
            # 第二帧为发送者幂等回执
            ack = ws.receive_json()
            self.assertEqual(ack["type"], "message_ack")
            self.assertEqual(ack["client_message_id"], "ws-1")
            self.assertEqual(ack["message"]["id"], message["id"])

        # 落库验证
        self.assertEqual(len(self.db.messages.docs), 1)
        doc = self.db.messages.docs[0]
        self.assertEqual(doc["client_message_id"], "ws-1")
        self.assertEqual(doc["conversation_id"], self.conversation_id)
        self.assertEqual(doc["sender_id"], str(self.alice["_id"]))
        self.assertEqual(doc["recipient_id"], str(self.bob["_id"]))
        self.assertEqual(doc["read"], False)
        # 会话摘要同步更新
        self.assertEqual(self.db.conversations.docs[0]["last_message_preview"], "hello ws")

    def test_duplicate_client_message_id_over_ws_is_idempotent(self):
        with self.connect(self.alice) as ws:
            payload = {"type": "message", "content": "hello ws", "client_message_id": "ws-dup"}
            ws.send_json(payload)
            first_broadcast = self.skip_join(ws)
            first_ack = ws.receive_json()

            ws.send_json(payload)  # 重复投递
            # 无重复广播，只有 ack（返回既有消息）
            replay_ack = ws.receive_json()

        self.assertEqual(first_ack["message"]["id"], first_broadcast["message"]["id"])
        self.assertEqual(replay_ack["type"], "message_ack")
        self.assertEqual(replay_ack["client_message_id"], "ws-dup")
        self.assertEqual(replay_ack["message"]["id"], first_broadcast["message"]["id"])
        self.assertEqual(len(self.db.messages.docs), 1)
        # 离线通知只在首次落库时创建一次，幂等重放不重复产生
        self.assertEqual(len(self.db.notifications.docs), 1)

    def test_empty_content_is_rejected_without_persisting(self):
        with self.connect(self.alice) as ws:
            ws.send_json({"type": "message", "content": ""})
            error = self.skip_join(ws)
            self.assertEqual(error["type"], "error")
            self.assertEqual(error["error_code"], "INVALID_PAYLOAD")
        self.assertEqual(len(self.db.messages.docs), 0)

    def test_other_member_can_also_send(self):
        with self.connect(self.bob) as ws:
            ws.send_json({"type": "message", "content": "from bob"})
            broadcast = self.skip_join(ws)
            self.assertEqual(broadcast["message"]["sender_id"], str(self.bob["_id"]))
        self.assertEqual(len(self.db.messages.docs), 1)

    # ---- WS03：read_receipt 真实落库 ----

    def test_ws_read_receipt_persists_and_broadcasts_shape(self):
        m1 = make_message_doc(
            self.conversation_id, str(self.bob["_id"]), str(self.alice["_id"]), "m1")
        m2 = make_message_doc(
            self.conversation_id, str(self.bob["_id"]), str(self.alice["_id"]), "m2")
        self.db.messages.docs.extend([m1, m2])

        with self.connect(self.alice) as ws:
            ws.send_json({"type": "read_receipt"})
            broadcast = self.skip_join(ws)

        self.assertEqual(broadcast["type"], "read_receipt")
        self.assertEqual(broadcast["conversation_id"], self.conversation_id)
        self.assertEqual(broadcast["reader_id"], str(self.alice["_id"]))
        self.assertEqual(
            sorted(broadcast["message_ids"]),
            sorted([str(m1["_id"]), str(m2["_id"])]),
        )
        self.assertIsNotNone(datetime.fromisoformat(broadcast["read_at"]))
        # 落库验证：未读消息被标记已读
        for doc in self.db.messages.docs:
            self.assertTrue(doc["read"])
            self.assertIsInstance(doc["read_at"], datetime)

    def test_ws_read_receipt_rejected_for_member_removed_mid_session(self):
        with self.connect(self.alice) as ws:
            self.assertEqual(ws.receive_json()["type"], "user_joined")
            # 连接期间被移出会话（入房校验已过，帧级成员校验须兜底）
            self.db.conversations.docs.clear()
            ws.send_json({"type": "read_receipt"})
            error = ws.receive_json()

        self.assertEqual(error["type"], "error")
        self.assertEqual(error["error_code"], "NOT_CONVERSATION_PARTICIPANT")
        # 与 message 分支同语义：拒绝并断连
        # （close 帧由服务端发出；上下文退出即关闭，不另断言 close code）
        self.assertEqual(len(self.db.messages.docs), 0)

    def test_ws_read_receipt_persist_failure_sends_error_without_broadcast(self):
        self.db.messages = ExplodingUpdateManyCollection()
        m1 = make_message_doc(
            self.conversation_id, str(self.bob["_id"]), str(self.alice["_id"]), "m1")
        self.db.messages.docs.append(m1)

        with self.connect(self.alice) as ws:
            self.assertEqual(ws.receive_json()["type"], "user_joined")
            ws.send_json({"type": "read_receipt"})
            error = self.skip_join(ws)
            self.assertEqual(error["type"], "error")
            self.assertEqual(error["error_code"], "READ_RECEIPT_PERSIST_FAILED")
            # 再次发送：仍只回错误帧——若误广播，这里会先收到 read_receipt 帧
            ws.send_json({"type": "read_receipt"})
            error2 = self.skip_join(ws)
            self.assertEqual(error2["type"], "error")
            self.assertEqual(error2["error_code"], "READ_RECEIPT_PERSIST_FAILED")

        # 未落库
        self.assertEqual(self.db.messages.docs[0]["read"], False)


# ---------------------------------------------------------------------------
# 启动集合边界（修复 test_demo_auth_boundary 回归：普通启动不隐式建集合）
# ---------------------------------------------------------------------------

class StartupCollectionBoundaryTests(unittest.IsolatedAsyncioTestCase):
    """ensure_communication_indexes 不得在空库上隐式创建 messages 集合
    （create_index 会隐式 createCollection，曾导致普通启动产生未声明集合写入），
    索引由首个消息落库路径惰性补建。"""

    async def asyncSetUp(self):
        from app.services import communication_service as communication_module
        self.communication_module = communication_module
        communication_module._index_state["ensured"] = False

    async def asyncTearDown(self):
        self.communication_module._index_state["ensured"] = False

    async def test_index_declaration_skips_missing_collection(self):
        db = FakeDB()

        async def empty_names():
            return []

        db.list_collection_names = empty_names  # 空库：没有任何集合
        await ensure_communication_indexes(db)
        # 未触碰 messages → 不隐式建集合、不声明索引
        self.assertEqual(db.messages.indexes, [])

    async def test_index_declaration_runs_for_existing_collection(self):
        db = FakeDB()  # messages 已在 __dict__ 中（等价于集合已存在）
        await ensure_communication_indexes(db)
        self.assertEqual(len(db.messages.indexes), 1)

    async def test_first_message_persist_bootstraps_index_lazily_exactly_once(self):
        db = FakeDB()
        alice = make_user("Alice", "doctor")
        bob = make_user("Bob", "patient")
        db.users.docs.extend([dict(alice), dict(bob)])
        conversation_id = seed_conversation(db, alice, bob)

        await CommunicationService.send_message(
            db, conversation_id, str(alice["_id"]), "m1", client_message_id="lazy-1")
        # 首个消息落库（隐式建集合）后，索引恰好补建一次
        self.assertEqual(len(db.messages.indexes), 1)
        self.assertEqual(
            db.messages.indexes[0][1]["name"],
            "uniq_conversation_sender_client_message_id",
        )
        await CommunicationService.send_message(
            db, conversation_id, str(alice["_id"]), "m2", client_message_id="lazy-2")
        # 每进程最多尝试一次，不随每条消息重复建索引
        self.assertEqual(len(db.messages.indexes), 1)


# ---------------------------------------------------------------------------
# D3 ConversationPolicy（默认采纳待评审追认 2026-11-09）
# ---------------------------------------------------------------------------

class ConversationPolicyDecisionTests(unittest.IsolatedAsyncioTestCase):
    """有效账号 + 会话参与者同一规则覆盖入站写与出站读。"""

    async def test_disabled_account_member_is_denied_on_send_and_read(self):
        db = FakeDB()
        alice = make_user("Alice", "doctor")
        bob = make_user("Bob", "patient")
        bob["is_active"] = False  # 连接期内被停用
        db.users.docs.extend([dict(alice), dict(bob)])
        conversation_id = seed_conversation(db, alice, bob)

        # 入站写：账号停用即拒绝，不落库
        with self.assertRaises(ValueError):
            await CommunicationService.send_message(
                db, conversation_id, str(bob["_id"]), "hi")
        self.assertEqual(len(db.messages.docs), 0)
        # 出站读：同一规则
        self.assertEqual(
            await CommunicationService.get_messages(db, conversation_id, str(bob["_id"])), [])
        self.assertIsNone(
            await CommunicationService.get_conversation(db, conversation_id, str(bob["_id"])))

    async def test_participants_array_shape_is_accepted_for_membership(self):
        """D1 目标形态兼容读：participants 数组会话在成员层与收发路径可用
        （写入侧仍为结构 B 双人形态，迁移属 WS01-c）。"""
        db = FakeDB()
        alice = make_user("Alice", "doctor")
        bob = make_user("Bob", "patient")
        db.users.docs.extend([dict(alice), dict(bob)])
        conversation_id = str(ObjectId())
        db.conversations.docs.append({
            "_id": ObjectId(conversation_id),
            "participants": [
                {"user_id": str(alice["_id"]), "role": "doctor", "joined_at": datetime.utcnow()},
                {"user_id": str(bob["_id"]), "role": "patient", "joined_at": datetime.utcnow()},
            ],
            "type": "chat",
            "status": "active",
            "created_at": datetime.utcnow(),
            "last_message_time": datetime.utcnow(),
            "metadata": {},
        })

        self.assertTrue(await CommunicationService.is_conversation_participant(
            db, conversation_id, str(alice["_id"])))
        sent = await CommunicationService.send_message(
            db, conversation_id, str(alice["_id"]), "array-shape")
        self.assertEqual(sent["recipient_id"], str(bob["_id"]))

    async def test_missing_user_record_is_denied(self):
        db = FakeDB()
        alice = make_user("Alice", "doctor")
        bob = make_user("Bob", "patient")
        conversation_id = seed_conversation(db, alice, bob)
        # 用户记录缺失（成员校验通过但账号层无记录）→ 拒绝
        with self.assertRaises(ValueError):
            await CommunicationService.send_message(
                db, conversation_id, str(alice["_id"]), "ghost")
        self.assertEqual(len(db.messages.docs), 0)


# ---------------------------------------------------------------------------
# D6 删除语义（默认采纳待评审追认 2026-11-09）
# ---------------------------------------------------------------------------

class DeletionSemanticsTests(unittest.IsolatedAsyncioTestCase):
    """软删除、双方会话内不可见、保留审计与原文引用完整性、不硬删。"""

    def setUp(self):
        self.db = FakeDB()
        self.alice = make_user("Alice", "doctor")
        self.bob = make_user("Bob", "patient")
        self.db.users.docs.extend([dict(self.alice), dict(self.bob)])
        self.conversation_id = seed_conversation(self.db, self.alice, self.bob)
        self.manager = _StubManager()
        self.manager_patch = patch(
            "app.api.websockets.get_connection_manager",
            return_value=self.manager,
        )
        self.manager_patch.start()

    def tearDown(self):
        self.manager_patch.stop()

    async def _send(self, content):
        return await CommunicationService.send_message(
            self.db, self.conversation_id, str(self.alice["_id"]), content)

    async def test_sender_delete_hides_from_both_and_preserves_original(self):
        message = await self._send("retract me")
        self.assertTrue(await CommunicationService.delete_message(
            self.db, message["id"], str(self.alice["_id"])))

        # 双方会话内均不可见
        self.assertEqual(await CommunicationService.get_messages(
            self.db, self.conversation_id, str(self.alice["_id"])), [])
        self.assertEqual(await CommunicationService.get_messages(
            self.db, self.conversation_id, str(self.bob["_id"])), [])

        # 不硬删：原文与原始字段保留，附审计字段（引用完整性不破坏）
        doc = self.db.messages.docs[0]
        self.assertEqual(doc["content"], "retract me")
        self.assertEqual(doc["sender_id"], str(self.alice["_id"]))
        self.assertTrue(doc["deleted"])
        self.assertIsInstance(doc["deleted_at"], datetime)
        self.assertEqual(doc["deleted_by"], str(self.alice["_id"]))

        # 删除事件广播带 server_seq
        delete_frame = self.manager.sent[-1][0]
        self.assertEqual(delete_frame["type"], "delete_message")
        self.assertEqual(delete_frame["message_id"], message["id"])
        self.assertIsInstance(delete_frame["server_seq"], int)

    async def test_recipient_can_delete_received_message(self):
        message = await self._send("for bob")
        self.assertTrue(await CommunicationService.delete_message(
            self.db, message["id"], str(self.bob["_id"])))
        doc = self.db.messages.docs[0]
        self.assertEqual(doc["deleted_by"], str(self.bob["_id"]))
        self.assertEqual(await CommunicationService.get_messages(
            self.db, self.conversation_id, str(self.bob["_id"])), [])

    async def test_non_participant_cannot_delete(self):
        mallory = make_user("Mallory", "doctor")
        self.db.users.docs.append(dict(mallory))
        message = await self._send("secret")
        self.assertFalse(await CommunicationService.delete_message(
            self.db, message["id"], str(mallory["_id"])))
        self.assertFalse(self.db.messages.docs[0]["deleted"])

    async def test_delete_is_idempotent_second_call_returns_false(self):
        message = await self._send("once")
        self.assertTrue(await CommunicationService.delete_message(
            self.db, message["id"], str(self.alice["_id"])))
        self.assertFalse(await CommunicationService.delete_message(
            self.db, message["id"], str(self.alice["_id"])))
        self.assertEqual(len(self.db.messages.docs), 1)  # 不硬删、不重复写

    async def test_deleted_message_excluded_from_offline_sync_and_unread(self):
        message = await self._send("gone")
        await CommunicationService.delete_message(
            self.db, message["id"], str(self.alice["_id"]))

        synced = await CommunicationService.sync_offline_messages(
            self.db, str(self.bob["_id"]), datetime.utcnow() - timedelta(hours=1))
        self.assertEqual(synced, [])
        self.assertEqual(await CommunicationService.get_unread_messages_count(
            self.db, self.conversation_id, str(self.bob["_id"])), 0)


# ---------------------------------------------------------------------------
# D7 事件信封 server_seq（_id 单调整数）
# ---------------------------------------------------------------------------

class ServerSeqEnvelopeTests(unittest.IsolatedAsyncioTestCase):
    """message / read_receipt / delete_message 帧携带 server_seq：
    插入型事件取落库 _id（重放稳定、与插入顺序单调），非插入型事件取发射时刻
    新生 ObjectId 的同进程单调整数。"""

    def setUp(self):
        self.db = FakeDB()
        self.alice = make_user("Alice", "doctor")
        self.bob = make_user("Bob", "patient")
        self.db.users.docs.extend([dict(self.alice), dict(self.bob)])
        self.conversation_id = seed_conversation(self.db, self.alice, self.bob)
        self.manager = _StubManager()
        self.manager_patch = patch(
            "app.api.websockets.get_connection_manager",
            return_value=self.manager,
        )
        self.manager_patch.start()

    def tearDown(self):
        self.manager_patch.stop()

    async def test_message_frames_carry_monotonic_server_seq_derived_from_id(self):
        first = await CommunicationService.send_message(
            self.db, self.conversation_id, str(self.alice["_id"]), "m1",
            client_message_id="seq-1")
        second = await CommunicationService.send_message(
            self.db, self.conversation_id, str(self.alice["_id"]), "m2",
            client_message_id="seq-2")

        frames = [payload for payload, _ in self.manager.sent
                  if payload["type"] == "message"]
        self.assertEqual(len(frames), 2)
        seqs = [frame["server_seq"] for frame in frames]
        self.assertTrue(all(isinstance(seq, int) and seq > 0 for seq in seqs))
        self.assertLess(seqs[0], seqs[1])  # 与落库顺序单调一致
        # 与消息 id 同源：server_seq = _id 的 12 字节大端整数
        self.assertEqual(seqs[0], int.from_bytes(ObjectId(first["id"]).binary, "big"))

    async def test_replayed_message_does_not_emit_second_frame(self):
        payload = {"client_message_id": "dup"}
        await CommunicationService.send_message(
            self.db, self.conversation_id, str(self.alice["_id"]), "m", **payload)
        await CommunicationService.send_message(
            self.db, self.conversation_id, str(self.alice["_id"]), "m", **payload)
        frames = [p for p, _ in self.manager.sent if p["type"] == "message"]
        self.assertEqual(len(frames), 1)  # 幂等重放不产生新事件帧

    async def test_read_receipt_carries_server_seq(self):
        unread = make_message_doc(
            self.conversation_id, str(self.alice["_id"]), str(self.bob["_id"]), "u")
        self.db.messages.docs.append(unread)
        await CommunicationService.mark_conversation_as_read(
            self.db, self.conversation_id, str(self.bob["_id"]))

        receipt = self.manager.sent[0][0]
        self.assertEqual(receipt["type"], "read_receipt")
        self.assertIsInstance(receipt["server_seq"], int)
        self.assertGreater(receipt["server_seq"], 0)


# ---------------------------------------------------------------------------
# 死代码清理回归
# ---------------------------------------------------------------------------

class DeadCodeRemovalTests(unittest.TestCase):
    def test_struct_a_models_are_gone_and_notification_survives(self):
        import app.models.communication as communication_models
        self.assertFalse(hasattr(communication_models, "Message"))
        self.assertFalse(hasattr(communication_models, "Conversation"))
        self.assertTrue(hasattr(communication_models, "Notification"))

    def test_message_conversation_crud_are_gone(self):
        import app.db.crud_services as crud_services
        self.assertFalse(hasattr(crud_services, "MessageCRUD"))
        self.assertFalse(hasattr(crud_services, "ConversationCRUD"))
        factory = crud_services.get_crud_services(FakeDB())
        self.assertNotIn("message", factory)
        self.assertNotIn("conversation", factory)

    def test_dead_api_aggregator_file_is_removed(self):
        self.assertFalse(os.path.exists(
            os.path.join(os.path.dirname(__file__), "..", "app", "api", "api.py")
        ))

    def test_no_dead_references_to_removed_symbols(self):
        import app.core.dependencies as dependencies
        self.assertFalse(hasattr(dependencies, "get_message_crud"))
        self.assertFalse(hasattr(dependencies, "get_conversation_crud"))

    def test_import_app_main_still_works(self):
        # 本模块顶部已 import app.main；此处再显式断言一次
        import app.main as main_module
        self.assertIsNotNone(main_module.app)


if __name__ == "__main__":
    unittest.main()
