"""
WS01 通信契约测试

覆盖：
- REST 发消息落库形状（结构 B：participant1_id/participant2_id、read/deleted、recipient_id）
- client_message_id 幂等键（HTTP 与 WS 入站同键，重复投递返回既有消息不重复落库）
- WS：非成员入房被拒（close 4403 / NOT_CONVERSATION_PARTICIPANT）、
  成员发消息落库且广播载荷带真实服务端 id、重复 client_message_id 幂等
- 死代码删除后 import app.main 正常（本模块顶部 import 即隐式覆盖）
"""
import asyncio
import os
import re
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from bson import ObjectId
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDisconnect

from app.core.auth import get_current_active_user
from app.db.mongodb import get_database
from app.main import app
from app.services.communication_service import CommunicationService

OBJECT_ID_PATTERN = re.compile(r"^[0-9a-f]{24}$")


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
            return alice

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

    async def test_conversation_membership_is_enforced_for_http_send(self):
        db = FakeDB()
        alice = make_user("Alice", "doctor")
        mallory = make_user("Mallory", "doctor")
        bob = make_user("Bob", "patient")
        db.users.docs.extend([dict(alice), dict(bob)])
        conversation_id = seed_conversation(db, alice, bob)
        app.dependency_overrides[get_database] = lambda: db

        async def fake_current_user():
            return mallory

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
        self.assertEqual(len(db.notifications.docs), 0)  # 幂等重放不产生新副作用

    async def test_same_key_from_other_sender_or_conversation_is_not_deduplicated(self):
        db = FakeDB()
        alice = make_user("Alice", "doctor")
        bob = make_user("Bob", "patient")
        carol = make_user("Carol", "doctor")
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
