"""T76 通信附件端到端契约：上传 → 引用归属校验 → 消息落库 → 下载。

覆盖：
1. 上传鉴权（会话参与者 + 医护/患者角色门槛）与类型/大小限制
   （图片 ≤5MB、文件 ≤10MB，白名单外类型 422）；
2. 消息发送时的引用归属校验：他人附件 / 跨会话附件 / 已被其他消息
   绑定的附件一律拒绝；幂等重放（同 client_message_id）放行；
3. 消息带附件端到端：富化引用（id/kind/name/size/url）随消息落库，
   GET messages 返回同形引用，附件绑定消息 id（防重复引用）；
4. 下载：仅限附件所属会话参与者。

打桩方式：内存 FakeDB + 真实路由/服务（require_message_write_storage 与
本地存储目录打桩），不触碰真实 MongoDB。
"""

import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bson import ObjectId
from fastapi.testclient import TestClient
from jose import jwt

from app.core.auth import get_current_active_user
from app.core.config import settings
from app.db.mongodb import get_database
from app.main import app
from app.schemas.user import UserResponse

PATIENT_ID = str(ObjectId())
DOCTOR_ID = str(ObjectId())
OUTSIDER_ID = str(ObjectId())
CONVERSATION_ID = str(ObjectId())
OTHER_CONVERSATION_ID = str(ObjectId())

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64
PDF_BYTES = b"%PDF-1.4" + b"0" * 64


def make_operator(role="patient", user_id=PATIENT_ID):
    now = datetime.utcnow()
    return UserResponse(id=user_id, email="actor@example.com", name="合成操作者",
                        role=role, is_active=True, createdAt=now, updatedAt=now)


def _match(doc, query):
    for key, expected in query.items():
        value = doc.get(key)
        if isinstance(expected, dict) and any(op.startswith("$") for op in expected):
            if "$in" in expected:
                if isinstance(value, (list, tuple)):
                    if not any(item in expected["$in"] for item in value):
                        return False
                elif value not in expected["$in"]:
                    return False
            if "$ne" in expected and value == expected["$ne"]:
                return False
        elif value != expected:
            return False
    return True


class FakeCollection:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, projection=None, **kwargs):
        for doc in self.docs:
            if _match(doc, query):
                return doc
        return None

    def find(self, query, projection=None, **kwargs):
        return FakeCursor([doc for doc in self.docs if _match(doc, query)])

    async def insert_one(self, document):
        self.docs.append(document)
        return SimpleNamespace(inserted_id=document.get("_id"))

    async def update_one(self, query, update, **kwargs):
        for doc in self.docs:
            if _match(doc, query):
                doc.update(update.get("$set", {}))
                return SimpleNamespace(matched_count=1, modified_count=1, upserted_id=None)
        return SimpleNamespace(matched_count=0, modified_count=0, upserted_id=None)

    async def update_many(self, query, update, **kwargs):
        matched = 0
        for doc in self.docs:
            if _match(doc, query):
                doc.update(update.get("$set", {}))
                matched += 1
        return SimpleNamespace(matched_count=matched, modified_count=matched)

    async def delete_one(self, query):
        for index, doc in enumerate(self.docs):
            if _match(doc, query):
                self.docs.pop(index)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)

    async def count_documents(self, query):
        return len([doc for doc in self.docs if _match(doc, query)])


class FakeCursor:
    def __init__(self, rows):
        self.rows = list(rows)

    def sort(self, key, direction=1):
        self.rows.sort(key=lambda doc: str(doc.get(key) or ""), reverse=direction < 0)
        return self

    def skip(self, count):
        self.rows = self.rows[count:]
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    async def to_list(self, length=None):
        rows = list(self.rows)
        return rows[:length] if length is not None else rows

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        if self._index >= len(self.rows):
            raise StopAsyncIteration
        row = self.rows[self._index]
        self._index += 1
        return row


class FakeDatabase:
    """内存库：通信域用到的集合按名提供，未知集合自动建空集合。"""

    def __init__(self):
        self.users = FakeCollection()
        self.conversations = FakeCollection()
        self.messages = FakeCollection()
        self.communication_attachments = FakeCollection()
        self.notifications = FakeCollection()
        self.client = None  # 无事务替身 → 降级顺序写路径

    def __getitem__(self, name):
        return getattr(self, name)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        collection = FakeCollection()
        setattr(self, name, collection)
        return collection


class CommunicationAttachmentTests(unittest.TestCase):
    def setUp(self):
        self.database = FakeDatabase()
        self.database.users.docs.extend([
            {"_id": ObjectId(PATIENT_ID), "name": "合成患者", "role": "patient",
             "email": "patient@example.com", "is_active": True,
             "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()},
            {"_id": ObjectId(DOCTOR_ID), "name": "合成医生", "role": "doctor",
             "email": "doctor@example.com", "is_active": True,
             "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()},
        ])
        self.database.conversations.docs.append({
            "_id": ObjectId(CONVERSATION_ID),
            "participant1_id": PATIENT_ID, "participant2_id": DOCTOR_ID,
            "type": "chat", "status": "active",
            "created_at": datetime.utcnow(),
        })
        self.database.conversations.docs.append({
            "_id": ObjectId(OTHER_CONVERSATION_ID),
            "participant1_id": PATIENT_ID, "participant2_id": OUTSIDER_ID,
            "type": "chat", "status": "active",
            "created_at": datetime.utcnow(),
        })

        self.storage_dir = tempfile.mkdtemp(prefix="comm-attachments-test-")
        self.storage_patch = patch("app.services.communication_service.COMMUNICATION_MEDIA_DIR",
                                   Path(self.storage_dir))
        self.storage_patch.start()
        self.index_patch = patch("app.services.communication_service.require_message_write_storage",
                                 new=AsyncMock(return_value=None))
        self.index_patch.start()

        async def fake_database():
            yield self.database

        app.dependency_overrides[get_database] = fake_database
        self.operator = make_operator()
        app.dependency_overrides[get_current_active_user] = lambda: self.operator
        self.client = TestClient(app)

    def tearDown(self):
        self.storage_patch.stop()
        self.index_patch.stop()
        app.dependency_overrides.clear()
        self.client.close()

    def switch_user(self, role, user_id):
        self.operator = make_operator(role=role, user_id=user_id)
        app.dependency_overrides[get_current_active_user] = lambda: self.operator

    def auth_header(self, user_id=None):
        # 认证已由依赖替身承担；此处仅为形式化携带（不会经过真实 JWT 校验）。
        return {}

    def upload(self, filename="photo.png", content=PNG_BYTES,
               content_type="image/png", conversation_id=CONVERSATION_ID):
        return self.client.post(
            f"/api/communications/conversations/{conversation_id}/attachments",
            files={"file": (filename, content, content_type)})

    # ── 上传鉴权与限制 ───────────────────────────────────────────────

    def test_upload_returns_reference_for_participant(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.text)
        ref = response.json()
        self.assertEqual(ref["kind"], "image")
        self.assertEqual(ref["content_type"], "image/png")
        self.assertEqual(ref["name"], "photo.png")
        self.assertEqual(ref["size"], len(PNG_BYTES))
        self.assertEqual(ref["conversation_id"], CONVERSATION_ID)
        self.assertTrue(ref["url"].startswith("/api/communications/attachments/"))
        # 落盘 + 元数据
        stored_name = os.listdir(self.storage_dir)
        self.assertEqual(len(stored_name), 1)
        self.assertEqual(len(self.database.communication_attachments.docs), 1)
        row = self.database.communication_attachments.docs[0]
        self.assertEqual(row["uploader_id"], PATIENT_ID)
        self.assertIsNone(row["bound_message_id"])

    def test_upload_rejects_non_participant(self):
        self.switch_user("doctor", OUTSIDER_ID)
        response = self.upload()
        self.assertEqual(response.status_code, 403, response.text)
        self.assertIn("对话参与者", response.json()["detail"])
        self.assertEqual(self.database.communication_attachments.docs, [])

    def test_upload_rejects_invalid_type_and_oversize(self):
        response = self.upload(filename="payload.bin", content=b"\x00" * 32,
                               content_type="application/octet-stream")
        self.assertEqual(response.status_code, 422, response.text)

        response = self.upload(filename="big.png", content=b"\x89" * (5 * 1024 * 1024 + 1),
                               content_type="image/png")
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("5MB", response.json()["detail"])

        response = self.upload(filename="big.pdf", content=b"\x00" * (10 * 1024 * 1024 + 1),
                               content_type="application/pdf")
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("10MB", response.json()["detail"])
        self.assertEqual(self.database.communication_attachments.docs, [])

    def test_upload_file_kind_and_role_gate(self):
        response = self.upload(filename="report.pdf", content=PDF_BYTES,
                               content_type="application/pdf")
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["kind"], "file")

        # admin 不是会话沟通角色 → 403
        self.switch_user("admin", OUTSIDER_ID)
        response = self.upload()
        self.assertEqual(response.status_code, 403, response.text)

    # ── 消息发送引用归属校验 ─────────────────────────────────────────

    def _send(self, attachments, client_message_id=None, content="请查看附件"):
        body = {"content": content, "attachments": attachments}
        if client_message_id:
            body["client_message_id"] = client_message_id
        return self.client.post(
            f"/api/communications/conversations/{CONVERSATION_ID}/messages",
            json=body)

    def test_send_message_with_own_attachment_end_to_end(self):
        upload = self.upload()
        attachment_id = upload.json()["id"]

        response = self._send([{"id": attachment_id}], client_message_id="cmid-1")
        self.assertEqual(response.status_code, 201, response.text)
        message = response.json()
        self.assertEqual(len(message["attachments"]), 1)
        ref = message["attachments"][0]
        self.assertEqual(ref["id"], attachment_id)
        self.assertEqual(ref["kind"], "image")
        self.assertEqual(ref["url"], f"/api/communications/attachments/{attachment_id}")
        self.assertEqual(ref["name"], "photo.png")

        # 附件绑定消息 id
        row = self.database.communication_attachments.docs[0]
        self.assertEqual(row["bound_message_id"], message["id"])

        # 读取端返回同形引用
        listing = self.client.get(
            f"/api/communications/conversations/{CONVERSATION_ID}/messages")
        self.assertEqual(listing.status_code, 200, listing.text)
        self.assertTrue(listing.json())
        self.assertEqual(listing.json()[0]["attachments"][0]["url"], ref["url"])

    def test_send_rejects_attachment_uploaded_by_others(self):
        upload = self.upload()
        attachment_id = upload.json()["id"]
        # 医生（会话参与者）引用患者上传的附件 → 拒绝
        self.switch_user("doctor", DOCTOR_ID)
        response = self._send([{"id": attachment_id}])
        self.assertEqual(response.status_code, 403, response.text)
        self.assertIn("只能引用自己上传的附件", response.json()["detail"])
        self.assertEqual(self.database.messages.docs, [])

    def test_send_rejects_attachment_from_other_conversation(self):
        # 上传到另一会话（患者是两段会话的共同成员）
        upload = self.upload(conversation_id=OTHER_CONVERSATION_ID)
        attachment_id = upload.json()["id"]
        response = self._send([{"id": attachment_id}])
        self.assertEqual(response.status_code, 403, response.text)
        self.assertIn("附件不属于当前会话", response.json()["detail"])

    def test_send_rejects_reused_attachment_across_messages(self):
        upload = self.upload()
        attachment_id = upload.json()["id"]
        response = self._send([{"id": attachment_id}], client_message_id="cmid-a")
        self.assertEqual(response.status_code, 201, response.text)

        # 同一附件被另一条新消息引用 → 409
        response = self._send([{"id": attachment_id}], client_message_id="cmid-b")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("附件已被其他消息使用", response.json()["detail"])

    def test_send_idempotent_replay_allows_same_attachment(self):
        upload = self.upload()
        attachment_id = upload.json()["id"]
        first = self._send([{"id": attachment_id}], client_message_id="cmid-same")
        self.assertEqual(first.status_code, 201, response.text if False else first.text)
        replay = self._send([{"id": attachment_id}], client_message_id="cmid-same")
        self.assertEqual(replay.status_code, 201, replay.text)
        self.assertEqual(replay.json()["id"], first.json()["id"])
        self.assertEqual(len(self.database.messages.docs), 1)

    def test_download_attachment_scoped_to_conversation(self):
        upload = self.upload()
        attachment_id = upload.json()["id"]
        url = upload.json()["url"]

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertEqual(response.content, PNG_BYTES)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

        # 非会话参与者 → 403
        self.switch_user("doctor", OUTSIDER_ID)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403, response.text)

        # 未知附件 → 404
        self.switch_user("patient", PATIENT_ID)
        response = self.client.get("/api/communications/attachments/" + "0" * 32)
        self.assertEqual(response.status_code, 404, response.text)

    def test_upload_requires_authentication(self):
        # 移除依赖替身，走真实 JWT 认证（token 指向会话患者账号）→ 201
        app.dependency_overrides.pop(get_current_active_user, None)
        token = jwt.encode({"sub": PATIENT_ID, "token_type": "access",
                            "exp": datetime.utcnow() + timedelta(minutes=5)},
                           settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        response = self.client.post(
            f"/api/communications/conversations/{CONVERSATION_ID}/attachments",
            files={"file": ("photo.png", PNG_BYTES, "image/png")},
            headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 201, response.text)

        # 无凭据 → 401
        response = self.client.post(
            f"/api/communications/conversations/{CONVERSATION_ID}/attachments",
            files={"file": ("photo.png", PNG_BYTES, "image/png")})
        self.assertEqual(response.status_code, 401, response.text)


if __name__ == "__main__":
    unittest.main()
