"""
通知域契约测试（WS01 盘点后续诚实化）

覆盖：
- NotificationService 落库/未读计数/已读/删除的真实语义（FakeDB 桩）
- 通知归属校验：非收件人不能已读/删除他人通知
- 通知 REST 契约（GET 列表 / unread/count / PUT read）
- 真实业务事件触发点（communication_service）：
  离线消息 → 通知；在线收件人 → 不产生通知；
  新会话建立 → 通知受邀方；消息撤回 → 通知另一方
- WS /ws/notifications 契约：连接即推真实未读数；离线消息触发实时推送
"""
import asyncio
import re
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from bson import ObjectId
from fastapi.testclient import TestClient

from app.core.auth import get_current_user
from app.db.mongodb import get_database
from app.main import app
from app.services.communication_service import CommunicationService
from app.services.notification_service import NotificationService

OBJECT_ID_PATTERN = re.compile(r"^[0-9a-f]{24}$")


# ---------------------------------------------------------------------------
# 内存版 Mongo 桩（与 test_communication_contract.py 同款最小实现，此处
# 补充通知域用到的 delete_one / delete_many / insert_many）
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

    async def insert_many(self, docs):
        for doc in docs:
            self.docs.append(dict(doc))
        return SimpleNamespace(
            inserted_ids=[doc.get("_id") for doc in docs]
        )

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

    async def delete_one(self, query):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not _matches(d, query)]
        return SimpleNamespace(deleted_count=before - len(self.docs))

    async def delete_many(self, query):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not _matches(d, query)]
        return SimpleNamespace(deleted_count=before - len(self.docs))

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


def seed_message(db, conversation_id, sender, recipient, content="hello"):
    message_id = str(ObjectId())
    db.messages.docs.append({
        "_id": ObjectId(message_id),
        "conversation_id": conversation_id,
        "sender_id": str(sender["_id"]),
        "recipient_id": str(recipient["_id"]),
        "content": content,
        "type": "text",
        "timestamp": datetime.utcnow(),
        "read": False,
        "deleted": False,
        "attachments": [],
        "metadata": {},
    })
    return message_id


async def _drain_tasks():
    """让 create_notification 里 create_task 的推送协程跑完，避免悬空任务。"""
    for _ in range(3):
        await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# 落库 / 未读计数 / 已读 / 删除 的真实语义
# ---------------------------------------------------------------------------

class NotificationServiceContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_notification_persists_shape_and_returns_id(self):
        db = FakeDB()
        sender = make_user("Alice", "doctor")
        recipient = make_user("Bob", "patient")

        notification_id = await NotificationService.create_notification(
            db=db,
            title="新消息",
            content="Alice 发送了新消息: hello",
            sender_id=str(sender["_id"]),
            sender_name="Alice",
            sender_role="doctor",
            recipient_id=str(recipient["_id"]),
            notification_type="message",
            priority="normal",
            related_entity_id=str(ObjectId()),
            related_entity_type="conversation",
        )
        await _drain_tasks()

        self.assertRegex(notification_id, OBJECT_ID_PATTERN)
        self.assertEqual(len(db.notifications.docs), 1)
        doc = db.notifications.docs[0]
        self.assertEqual(doc["recipient_id"], str(recipient["_id"]))
        self.assertEqual(doc["sender_id"], str(sender["_id"]))
        self.assertEqual(doc["read"], False)  # 新通知必为未读
        self.assertEqual(doc["notification_type"], "message")
        self.assertEqual(doc["priority"], "normal")
        self.assertIsInstance(doc["time"], datetime)

    async def test_unread_count_tracks_read_state(self):
        db = FakeDB()
        bob = make_user("Bob", "patient")
        for _ in range(2):
            await NotificationService.create_notification(
                db=db, title="t", content="c",
                sender_id=str(ObjectId()), sender_name="x", sender_role="doctor",
                recipient_id=str(bob["_id"]),
            )
        await _drain_tasks()

        self.assertEqual(await NotificationService.get_unread_count(db, str(bob["_id"])), 2)

        first_id = str(db.notifications.docs[0]["_id"])
        self.assertTrue(
            await NotificationService.mark_as_read(db, first_id, str(bob["_id"]))
        )
        self.assertEqual(await NotificationService.get_unread_count(db, str(bob["_id"])), 1)

        modified = await NotificationService.mark_all_as_read(db, str(bob["_id"]))
        self.assertEqual(modified, 1)
        self.assertEqual(await NotificationService.get_unread_count(db, str(bob["_id"])), 0)

    async def test_unread_count_is_per_recipient(self):
        db = FakeDB()
        bob = make_user("Bob", "patient")
        carol = make_user("Carol", "patient")
        await NotificationService.create_notification(
            db=db, title="t", content="c",
            sender_id=str(ObjectId()), sender_name="x", sender_role="doctor",
            recipient_id=str(bob["_id"]),
        )
        await _drain_tasks()

        self.assertEqual(await NotificationService.get_unread_count(db, str(bob["_id"])), 1)
        self.assertEqual(await NotificationService.get_unread_count(db, str(carol["_id"])), 0)

    async def test_non_recipient_cannot_mark_read_or_delete(self):
        db = FakeDB()
        bob = make_user("Bob", "patient")
        mallory = make_user("Mallory", "doctor")
        notification_id = await NotificationService.create_notification(
            db=db, title="t", content="c",
            sender_id=str(ObjectId()), sender_name="x", sender_role="doctor",
            recipient_id=str(bob["_id"]),
        )
        await _drain_tasks()

        self.assertFalse(
            await NotificationService.mark_as_read(db, notification_id, str(mallory["_id"]))
        )
        self.assertFalse(
            await NotificationService.delete_notification(db, notification_id, str(mallory["_id"]))
        )
        # 通知未被修改/删除
        self.assertEqual(len(db.notifications.docs), 1)
        self.assertEqual(db.notifications.docs[0]["read"], False)
        # 收件人本人可以已读+删除
        self.assertTrue(
            await NotificationService.mark_as_read(db, notification_id, str(bob["_id"]))
        )
        self.assertTrue(
            await NotificationService.delete_notification(db, notification_id, str(bob["_id"]))
        )
        self.assertEqual(len(db.notifications.docs), 0)

    async def test_clear_all_only_clears_own_notifications(self):
        db = FakeDB()
        bob = make_user("Bob", "patient")
        carol = make_user("Carol", "patient")
        for recipient in (bob, carol):
            await NotificationService.create_notification(
                db=db, title="t", content="c",
                sender_id=str(ObjectId()), sender_name="x", sender_role="doctor",
                recipient_id=str(recipient["_id"]),
            )
        await _drain_tasks()

        deleted = await NotificationService.clear_all_notifications(db, str(bob["_id"]))
        self.assertEqual(deleted, 1)
        remaining_ids = [str(d["_id"]) for d in db.notifications.docs]
        self.assertEqual(len(remaining_ids), 1)
        self.assertEqual(
            remaining_ids[0],
            str(db.notifications.docs[0]["_id"]),
        )
        # 剩余的是 Carol 的
        self.assertEqual(db.notifications.docs[0]["recipient_id"], str(carol["_id"]))

    async def test_get_notifications_returns_json_safe_list(self):
        db = FakeDB()
        bob = make_user("Bob", "patient")
        other = make_user("Carol", "patient")
        for recipient in (bob, other):
            await NotificationService.create_notification(
                db=db, title="t", content="c",
                sender_id=str(ObjectId()), sender_name="x", sender_role="doctor",
                recipient_id=str(recipient["_id"]),
            )
        await _drain_tasks()

        result = await NotificationService.get_notifications(db, str(bob["_id"]))
        self.assertEqual(len(result), 1)
        self.assertRegex(result[0]["id"], OBJECT_ID_PATTERN)
        self.assertNotIn("_id", result[0])
        self.assertEqual(result[0]["recipient_id"], str(bob["_id"]))

        # read 筛选：全部未读时 read=True 查询应为空
        result_read = await NotificationService.get_notifications(
            db, str(bob["_id"]), read=True
        )
        self.assertEqual(result_read, [])


# ---------------------------------------------------------------------------
# 通知 REST 契约（/api/notifications）
# ---------------------------------------------------------------------------

class NotificationRouterContractTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        app.dependency_overrides.clear()

    async def test_list_unread_count_and_mark_read_endpoints(self):
        db = FakeDB()
        bob = make_user("Bob", "patient")
        for _ in range(2):
            await NotificationService.create_notification(
                db=db, title="t", content="c",
                sender_id=str(ObjectId()), sender_name="x", sender_role="doctor",
                recipient_id=str(bob["_id"]),
            )
        await _drain_tasks()
        app.dependency_overrides[get_database] = lambda: db

        async def fake_current_user():
            return bob

        app.dependency_overrides[get_current_user] = fake_current_user
        # follow_redirects：路由为 "/notifications/"，前端实际请求 /notifications 靠 307 跟随
        async with httpx.AsyncClient(
            app=app, base_url="http://test", follow_redirects=True
        ) as client:
            listing = await client.get("/api/notifications")
            self.assertEqual(listing.status_code, 200)
            body = listing.json()
            self.assertEqual(len(body), 2)
            self.assertRegex(body[0]["id"], OBJECT_ID_PATTERN)
            self.assertEqual(body[0]["read"], False)

            count = await client.get("/api/notifications/unread/count")
            self.assertEqual(count.status_code, 200)
            self.assertEqual(count.json(), 2)

            first_id = body[0]["id"]
            marked = await client.put(f"/api/notifications/{first_id}/read")
            self.assertEqual(marked.status_code, 200)
            self.assertEqual(
                (await client.get("/api/notifications/unread/count")).json(), 1
            )

            # 非本人通知 → 404
            stranger_doc_id = str(ObjectId())
            missing = await client.put(f"/api/notifications/{stranger_doc_id}/read")
            self.assertEqual(missing.status_code, 404)

            mark_all = await client.put("/api/notifications/read-all")
            self.assertEqual(mark_all.status_code, 200)
            self.assertEqual(
                (await client.get("/api/notifications/unread/count")).json(), 0
            )

            deleted = await client.delete(f"/api/notifications/{first_id}")
            self.assertEqual(deleted.status_code, 200)
            self.assertEqual(len(db.notifications.docs), 1)


# ---------------------------------------------------------------------------
# 真实业务事件触发点（communication_service）
# ---------------------------------------------------------------------------

class NotificationTriggerTests(unittest.IsolatedAsyncioTestCase):
    async def test_offline_recipient_message_creates_notification(self):
        db = FakeDB()
        alice = make_user("Alice", "doctor")
        bob = make_user("Bob", "patient")
        db.users.docs.extend([dict(alice), dict(bob)])  # 通知内容需回查发送者
        conversation_id = seed_conversation(db, alice, bob)

        await CommunicationService.send_message(
            db, conversation_id, str(alice["_id"]), "offline hello"
        )
        await _drain_tasks()

        self.assertEqual(len(db.notifications.docs), 1)
        doc = db.notifications.docs[0]
        self.assertEqual(doc["recipient_id"], str(bob["_id"]))
        self.assertEqual(doc["sender_id"], str(alice["_id"]))
        self.assertEqual(doc["notification_type"], "message")
        self.assertEqual(doc["related_entity_id"], conversation_id)
        self.assertEqual(doc["related_entity_type"], "conversation")

    async def test_online_recipient_gets_no_notification(self):
        from app.api.websockets import get_connection_manager

        db = FakeDB()
        alice = make_user("Alice", "doctor")
        bob = make_user("Bob", "patient")
        conversation_id = seed_conversation(db, alice, bob)

        # bob "在线"（挂在聊天室里，无需真实 socket）
        manager = get_connection_manager()
        manager.chat_rooms.setdefault(conversation_id, {})[str(bob["_id"])] = {
            "stub": None
        }
        try:
            await CommunicationService.send_message(
                db, conversation_id, str(alice["_id"]), "online hello"
            )
        finally:
            manager.chat_rooms.pop(conversation_id, None)
        await _drain_tasks()

        self.assertEqual(len(db.notifications.docs), 0)

    async def test_create_conversation_notifies_invitee_once(self):
        db = FakeDB()
        alice = make_user("Alice", "doctor")
        bob = make_user("Bob", "patient")
        db.users.docs.extend([dict(alice), dict(bob)])

        conversation_id = await CommunicationService.create_conversation(
            db, str(alice["_id"]), str(bob["_id"])
        )
        await _drain_tasks()

        self.assertEqual(len(db.notifications.docs), 1)
        doc = db.notifications.docs[0]
        self.assertEqual(doc["recipient_id"], str(bob["_id"]))
        self.assertEqual(doc["sender_id"], str(alice["_id"]))
        self.assertEqual(doc["sender_name"], "Alice")
        self.assertEqual(doc["sender_role"], "doctor")
        self.assertEqual(doc["notification_type"], "message")
        self.assertEqual(doc["related_entity_type"], "conversation")
        self.assertEqual(doc["related_entity_id"], conversation_id)

        # 复用既有会话（幂等早退）不重复通知
        again = await CommunicationService.create_conversation(
            db, str(alice["_id"]), str(bob["_id"])
        )
        self.assertEqual(again, conversation_id)
        self.assertEqual(len(db.notifications.docs), 1)

    async def test_delete_message_notifies_other_party(self):
        db = FakeDB()
        alice = make_user("Alice", "doctor")
        bob = make_user("Bob", "patient")
        conversation_id = seed_conversation(db, alice, bob)
        message_id = seed_message(db, conversation_id, alice, bob)

        self.assertTrue(
            await CommunicationService.delete_message(
                db, message_id, str(alice["_id"])
            )
        )
        await _drain_tasks()

        self.assertEqual(len(db.notifications.docs), 1)
        doc = db.notifications.docs[0]
        self.assertEqual(doc["recipient_id"], str(bob["_id"]))
        self.assertEqual(doc["sender_id"], str(alice["_id"]))
        self.assertEqual(doc["title"], "消息已撤回")
        self.assertEqual(doc["related_entity_id"], conversation_id)

        # 非发送者删除 → 拒绝且不产生通知
        message_id2 = seed_message(db, conversation_id, alice, bob)
        self.assertFalse(
            await CommunicationService.delete_message(
                db, message_id2, str(bob["_id"])
            )
        )
        self.assertEqual(len(db.notifications.docs), 1)


# ---------------------------------------------------------------------------
# WS 契约（/ws/notifications）
# ---------------------------------------------------------------------------

_ws_routes_registered = False


def _ensure_ws_routes():
    global _ws_routes_registered
    if not _ws_routes_registered:
        from app.api.websockets import setup_websockets
        setup_websockets(app)
        _ws_routes_registered = True


class WebSocketNotificationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_ws_routes()

    def setUp(self):
        self.client = TestClient(app)
        self.db = FakeDB()
        self.alice = make_user("Alice", "doctor")
        self.bob = make_user("Bob", "patient")
        self.db.users.docs.extend([dict(self.alice), dict(self.bob)])
        self.conversation_id = seed_conversation(self.db, self.alice, self.bob)
        app.dependency_overrides[get_database] = lambda: self.db

    def tearDown(self):
        app.dependency_overrides.pop(get_database, None)

    def _connect(self, user, path):
        ws_patch = patch(
            "app.api.websockets.get_current_user_ws",
            new=AsyncMock(return_value=user),
        )
        ws_patch.start()
        session = self.client.websocket_connect(f"{path}?token=stub")

        class _Session:
            def __enter__(self):
                return session.__enter__()

            def __exit__(self, *exc):
                try:
                    return session.__exit__(*exc)
                finally:
                    ws_patch.stop()

        return _Session()

    def test_connect_pushes_real_unread_count(self):
        # bob 有 2 条未读通知
        for _ in range(2):
            self.db.notifications.docs.append({
                "_id": ObjectId(),
                "title": "t",
                "content": "c",
                "sender_id": str(self.alice["_id"]),
                "sender_name": "Alice",
                "sender_role": "doctor",
                "recipient_id": str(self.bob["_id"]),
                "time": datetime.utcnow(),
                "read": False,
                "notification_type": "message",
                "priority": "normal",
                "related_entity_id": None,
                "related_entity_type": None,
            })

        with self._connect(self.bob, "/ws/notifications") as ws:
            frame = ws.receive_json()
            self.assertEqual(frame["type"], "notification_count")
            # 首帧计数与库中真实未读数一致
            self.assertEqual(frame["count"], 2)

    def test_offline_message_pushes_notification_frame_in_realtime(self):
        with self._connect(self.bob, "/ws/notifications") as notif_ws, \
                self._connect(self.alice, f"/ws/chat/{self.conversation_id}") as chat_ws:
            # bob 在通知通道不在聊天室 → 离线，触发通知
            chat_ws.send_json({"type": "message", "content": "push me"})
            # alice 侧先收到聊天室广播
            while True:
                frame = chat_ws.receive_json()
                if frame["type"] == "message":
                    break

            # bob 先收到连接时的初始未读计数帧（此刻为 0），跳过
            initial = notif_ws.receive_json()
            self.assertEqual(initial["type"], "notification_count")

            # bob 收到实时通知帧（形状：{type:"notification", data:{...}}）
            notification_frame = notif_ws.receive_json()
            self.assertEqual(notification_frame["type"], "notification")
            data = notification_frame["data"]
            self.assertEqual(data["title"], "新消息")
            self.assertEqual(data["sender_id"], str(self.alice["_id"]))
            self.assertEqual(data["related_entity_id"], self.conversation_id)

            # 随后是刷新后的未读计数帧
            count_frame = notif_ws.receive_json()
            self.assertEqual(count_frame["type"], "notification_count")
            self.assertEqual(count_frame["count"], 1)

        # 落库验证
        self.assertEqual(len(self.db.notifications.docs), 1)
        self.assertEqual(
            self.db.notifications.docs[0]["recipient_id"], str(self.bob["_id"])
        )


if __name__ == "__main__":
    unittest.main()
