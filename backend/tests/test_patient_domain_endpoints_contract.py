"""患者域桩端点真实化契约测试（2026-11-08）。

覆盖 GET /api/patients/health-records、GET/POST/DELETE /api/patients/devices、
GET/POST /api/patients/communications 从存根到真实 service 复用的行为契约：

- 患者本人 200 真实形状（devices / health_records / conversations 集合真实形状）；
- 患者查他人 403（本人语义不暴露他人数据存在性）；
- 医护无归属 403 PATIENT_NOT_ASSIGNED / 有归属 200（ensure_patient_access）；
- admin 豁免归属校验；患者不存在 404 PATIENT_NOT_FOUND；
- 空库空态如实返回空列表，不留吞异常假空；
- 设备解绑属主语义（他人设备/不存在/畸形 ID 一律 404）；
- 会话消息写路径复用 CommunicationService（不存在 404 / 非参与者 403 / 422）。

全部内存打桩 + FastAPI 依赖覆盖，不触碰真实数据库。
"""

import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from bson import ObjectId

from app.core.auth import get_current_user
from app.db.mongodb import get_database
from app.main import app
from app.schemas.user import UserResponse
from app.services import device_service as device_service_module
from app.services.communication_service import CommunicationService
from app.services.user_service import UserService

PATIENT_ID = str(ObjectId())
DOCTOR_ID = str(ObjectId())
ADMIN_ID = str(ObjectId())
OTHER_PATIENT_ID = str(ObjectId())
CONVERSATION_ID = str(ObjectId())
DEVICE_ID = "64b0f1c2a3b4c5d6e7f80901"


def _get_path(doc, path):
    cur = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _match(doc, filter_):
    """极简内存匹配：等值 / $ne / $in / $or，_id 兼容 ObjectId 与 str 形态。"""
    for key, cond in (filter_ or {}).items():
        if key == "$or":
            if not any(_match(doc, sub) for sub in cond):
                return False
            continue
        value = _get_path(doc, key)
        if isinstance(cond, dict) and any(op.startswith("$") for op in cond):
            for op, operand in cond.items():
                if op == "$ne":
                    if str(value) == str(operand):
                        return False
                elif op == "$in":
                    if not any(str(value) == str(item) for item in operand):
                        return False
                else:
                    if value != operand and str(value) != str(operand):
                        return False
            continue
        if value != cond and str(value) != str(cond):
            return False
    return True


class FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)
        self._sort = None
        self._skip = 0
        self._limit = None

    def sort(self, key, direction):
        self._sort = (key, direction)
        return self

    def skip(self, n):
        self._skip = n
        return self

    def limit(self, n):
        self._limit = n
        return self

    async def to_list(self, length=None):
        docs = self._docs
        if self._sort:
            key, direction = self._sort
            docs = sorted(
                docs,
                key=lambda d: d.get(key) or datetime.min,
                reverse=direction < 0,
            )
        docs = docs[self._skip:]
        size = self._limit if self._limit is not None else length
        if size is not None:
            docs = docs[:size]
        return [dict(doc) for doc in docs]


class FakeCollection:
    def __init__(self):
        self.docs = {}

    def insert(self, doc):
        self.docs[doc["_id"]] = dict(doc)

    async def find_one(self, query):
        for doc in self.docs.values():
            if _match(doc, query):
                return dict(doc)
        return None

    def find(self, query=None):
        return FakeCursor([d for d in self.docs.values() if _match(d, query or {})])

    async def insert_one(self, doc):
        doc = dict(doc)
        doc.setdefault("_id", ObjectId())
        self.docs[doc["_id"]] = doc
        return MagicMock(inserted_id=doc["_id"])

    async def update_one(self, query, update):
        matched = [d for d in self.docs.values() if _match(d, query)]
        for doc in matched:
            doc.update(update.get("$set", {}))
        return MagicMock(matched_count=len(matched), modified_count=len(matched))

    async def count_documents(self, query):
        return sum(1 for doc in self.docs.values() if _match(doc, query))


class FakeDatabase:
    def __init__(self):
        self._collections = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._collections.setdefault(name, FakeCollection())

    def __getitem__(self, name):
        return getattr(self, name)


def make_user(role="patient", user_id=None):
    now = datetime.utcnow()
    return UserResponse(id=user_id or PATIENT_ID, email="actor@example.com",
                        name="合成用户", role=role, is_active=True,
                        createdAt=now, updatedAt=now)


def make_patient_doc(patient_id=PATIENT_ID, practitioners=()):
    return {"_id": patient_id, "role": "patient", "name": "合成患者",
            "practitioners": list(practitioners)}


def make_device_doc(patient_id=PATIENT_ID, device_id=DEVICE_ID):
    now = datetime.utcnow()
    return {
        "_id": device_id, "device_id": device_id, "device_type": "血压计",
        "name": "合成设备", "manufacturer": None, "model": None,
        "connection_type": "bluetooth", "firmware_version": "1.0.0",
        "settings": {}, "patient_id": patient_id, "status": "active",
        "last_connected": now, "battery_level": 80,
        "created_at": now, "updated_at": now,
    }


class PatientDomainEndpointTests(unittest.IsolatedAsyncioTestCase):
    def _setup(self, user):
        async def fake_current_user():
            return user

        self.db = FakeDatabase()
        app.dependency_overrides[get_database] = lambda: self.db
        app.dependency_overrides[get_current_user] = fake_current_user
        self.get_user_mock = AsyncMock(return_value=user)
        self.lookup = patch.object(UserService, "get_user_by_id", new=self.get_user_mock)
        self.lookup.start()
        # 一个测试可切换多次操作者；每次获取的 patch/client 均须单独释放。
        # cleanup 逆序执行，避免后一层 patch 停止后留下先前的认证 mock。
        self.addCleanup(self.lookup.stop)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://patient-domain-test")
        self.addAsyncCleanup(self.client.aclose)

    async def asyncTearDown(self):
        app.dependency_overrides.clear()


# ── GET /patients/devices ────────────────────────────────────────────────────

class PatientDevicesListTests(PatientDomainEndpointTests):
    async def test_patient_empty_devices_returns_real_empty_list(self):
        """空库空态：真实查询 devices 集合，无设备时如实返回 []。"""
        self._setup(make_user())
        with patch.object(device_service_module, "get_db", AsyncMock(return_value=self.db)):
            response = await self.client.get("/api/patients/devices")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [])

    async def test_patient_devices_real_shape(self):
        """患者本人 200 真实形状：devices by patient_id，id 规范化输出。"""
        self._setup(make_user())
        self.db.devices.insert(make_device_doc(patient_id=PATIENT_ID, device_id=DEVICE_ID))
        self.db.devices.insert(make_device_doc(
            patient_id=OTHER_PATIENT_ID, device_id="64b0f1c2a3b4c5d6e7f80902"))
        with patch.object(device_service_module, "get_db", AsyncMock(return_value=self.db)):
            response = await self.client.get("/api/patients/devices")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["id"], DEVICE_ID)
        self.assertEqual(body[0]["patient_id"], PATIENT_ID)
        self.assertEqual(body[0]["name"], "合成设备")

    async def test_patient_cannot_query_other_patient(self):
        """患者查他人 403（本人语义，不暴露他人数据存在性）。"""
        self._setup(make_user())
        self.db.devices.insert(make_device_doc(patient_id=OTHER_PATIENT_ID))
        with patch.object(device_service_module, "get_db", AsyncMock(return_value=self.db)):
            response = await self.client.get(
                f"/api/patients/devices?patient_id={OTHER_PATIENT_ID}")
        self.assertEqual(response.status_code, 403, response.text)

    async def test_doctor_without_assignment_403(self):
        """医护无归属 403 PATIENT_NOT_ASSIGNED。"""
        self._setup(make_user(role="doctor", user_id=DOCTOR_ID))
        self.db.users.insert(make_patient_doc(
            patient_id=OTHER_PATIENT_ID, practitioners=[str(ObjectId())]))
        self.db.devices.insert(make_device_doc(patient_id=OTHER_PATIENT_ID))
        with patch.object(device_service_module, "get_db", AsyncMock(return_value=self.db)):
            response = await self.client.get(
                f"/api/patients/devices?patient_id={OTHER_PATIENT_ID}")
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["error"], "PATIENT_NOT_ASSIGNED")

    async def test_doctor_with_assignment_200(self):
        """医护有归属 200：查看归属患者真实设备列表。"""
        self._setup(make_user(role="doctor", user_id=DOCTOR_ID))
        self.db.users.insert(make_patient_doc(
            patient_id=OTHER_PATIENT_ID, practitioners=[DOCTOR_ID]))
        self.db.devices.insert(make_device_doc(patient_id=OTHER_PATIENT_ID))
        with patch.object(device_service_module, "get_db", AsyncMock(return_value=self.db)):
            response = await self.client.get(
                f"/api/patients/devices?patient_id={OTHER_PATIENT_ID}")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["patient_id"], OTHER_PATIENT_ID)

    async def test_admin_exempt_from_assignment(self):
        """admin 豁免归属校验：可指定任意 patient_id 查看设备。"""
        self._setup(make_user(role="admin", user_id=ADMIN_ID))
        self.db.users.insert(make_patient_doc(
            patient_id=OTHER_PATIENT_ID, practitioners=[]))
        self.db.devices.insert(make_device_doc(patient_id=OTHER_PATIENT_ID))
        with patch.object(device_service_module, "get_db", AsyncMock(return_value=self.db)):
            response = await self.client.get(
                f"/api/patients/devices?patient_id={OTHER_PATIENT_ID}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()), 1)

    async def test_missing_patient_404(self):
        """患者不存在 404 PATIENT_NOT_FOUND（先于归属判断）。"""
        self._setup(make_user(role="doctor", user_id=DOCTOR_ID))
        with patch.object(device_service_module, "get_db", AsyncMock(return_value=self.db)):
            response = await self.client.get(
                f"/api/patients/devices?patient_id={OTHER_PATIENT_ID}")
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json()["error"], "PATIENT_NOT_FOUND")


# ── POST /patients/devices ───────────────────────────────────────────────────

class PatientDeviceBindTests(PatientDomainEndpointTests):
    def _patch_service_db(self):
        return patch.object(device_service_module, "get_db", AsyncMock(return_value=self.db))

    async def test_bind_returns_real_device_document(self):
        """患者绑定设备 201：真实落库形状（patient_id 即本人），非假 ID。"""
        self._setup(make_user())
        with self._patch_service_db():
            response = await self.client.post("/api/patients/devices", json={
                "device_type": "血压计", "name": "家用血压计"})
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["patient_id"], PATIENT_ID)
        self.assertEqual(body["status"], "active")
        self.assertTrue(body["id"])
        self.assertTrue(any(str(key) == body["id"] for key in self.db.devices.docs))

    async def test_bind_invalid_device_type_400(self):
        """service 层设备类型校验失败如实 400，不落假绑定。"""
        self._setup(make_user())
        with self._patch_service_db():
            response = await self.client.post("/api/patients/devices", json={
                "device_type": "不存在的类型", "name": "合成设备"})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.db.devices.docs, {})

    async def test_bind_forbidden_for_doctor(self):
        """非患者角色 403：绑定目标是操作者本人，仅患者语义。"""
        self._setup(make_user(role="doctor", user_id=DOCTOR_ID))
        with self._patch_service_db():
            response = await self.client.post("/api/patients/devices", json={
                "device_type": "血压计", "name": "家用血压计"})
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.db.devices.docs, {})


# ── DELETE /patients/devices/{device_id} ─────────────────────────────────────

class PatientDeviceUnbindTests(PatientDomainEndpointTests):
    def _patch_service_db(self):
        return patch.object(device_service_module, "get_db", AsyncMock(return_value=self.db))

    async def test_unbind_own_device_204(self):
        """属主本人解绑 204，集合中状态置 deleted。"""
        self._setup(make_user())
        self.db.devices.insert(make_device_doc(patient_id=PATIENT_ID))
        with self._patch_service_db():
            response = await self.client.delete(f"/api/patients/devices/{DEVICE_ID}")
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(self.db.devices.docs[DEVICE_ID]["status"], "deleted")

    async def test_unbind_other_patient_device_404(self):
        """他人设备一律 404（属主语义对象级隔离，不区分不存在与无权）。"""
        self._setup(make_user())
        self.db.devices.insert(make_device_doc(patient_id=OTHER_PATIENT_ID))
        with self._patch_service_db():
            response = await self.client.delete(f"/api/patients/devices/{DEVICE_ID}")
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(self.db.devices.docs[DEVICE_ID]["status"], "active")

    async def test_unbind_missing_or_malformed_id_404(self):
        """不存在与畸形 ID 语义一致：404。"""
        self._setup(make_user())
        with self._patch_service_db():
            response = await self.client.delete("/api/patients/devices/not-an-objectid")
            self.assertEqual(response.status_code, 404, response.text)
            missing = str(ObjectId())
            response = await self.client.delete(f"/api/patients/devices/{missing}")
            self.assertEqual(response.status_code, 404, response.text)


# ── GET /patients/health-records ─────────────────────────────────────────────

def make_health_record_doc(patient_id=PATIENT_ID, record_type="general"):
    now = datetime.utcnow()
    return {
        "_id": str(ObjectId()), "patient_id": patient_id,
        "record_type": record_type, "title": "合成档案",
        "content": "主诉：测试（生效 schema 中 content 为文本）", "created_by": DOCTOR_ID,
        "created_at": now, "updated_at": now,
    }


class PatientHealthRecordsTests(PatientDomainEndpointTests):
    async def test_patient_empty_records_returns_real_empty_list(self):
        """空库空态：无档案时如实返回 []（存根时代的 {} 假对象已移除）。"""
        self._setup(make_user())
        response = await self.client.get("/api/patients/health-records")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [])

    async def test_patient_records_real_shape(self):
        """患者本人 200 真实形状：health_records by patient_id（复用 service 映射）。"""
        self._setup(make_user())
        self.db["health_records"].insert(make_health_record_doc(PATIENT_ID))
        self.db["health_records"].insert(make_health_record_doc(OTHER_PATIENT_ID))
        response = await self.client.get("/api/patients/health-records")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["patient_id"], PATIENT_ID)
        self.assertEqual(body[0]["title"], "合成档案")
        self.assertIsInstance(body[0]["content"], str)
        self.assertTrue(body[0]["id"])

    async def test_record_type_filter_and_pagination(self):
        """record_type 过滤与 skip/limit 分页为 service 层真实行为。"""
        self._setup(make_user())
        records = self.db["health_records"]
        records.insert(make_health_record_doc(PATIENT_ID, "diagnostic"))
        records.insert(make_health_record_doc(PATIENT_ID, "general"))
        response = await self.client.get(
            "/api/patients/health-records?record_type=diagnostic")
        self.assertEqual(len(response.json()), 1)
        response = await self.client.get("/api/patients/health-records?limit=1&skip=1")
        self.assertEqual(len(response.json()), 1)

    async def test_patient_cannot_query_other_patient(self):
        """患者查他人 403。"""
        self._setup(make_user())
        self.db["health_records"].insert(make_health_record_doc(OTHER_PATIENT_ID))
        response = await self.client.get(
            f"/api/patients/health-records?patient_id={OTHER_PATIENT_ID}")
        self.assertEqual(response.status_code, 403, response.text)

    async def test_doctor_without_assignment_403(self):
        """医护无归属 403 PATIENT_NOT_ASSIGNED。"""
        self._setup(make_user(role="doctor", user_id=DOCTOR_ID))
        self.db.users.insert(make_patient_doc(
            patient_id=OTHER_PATIENT_ID, practitioners=[str(ObjectId())]))
        self.db["health_records"].insert(make_health_record_doc(OTHER_PATIENT_ID))
        response = await self.client.get(
            f"/api/patients/health-records?patient_id={OTHER_PATIENT_ID}")
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["error"], "PATIENT_NOT_ASSIGNED")

    async def test_doctor_with_assignment_200(self):
        """医护有归属 200：查看归属患者真实档案。"""
        self._setup(make_user(role="doctor", user_id=DOCTOR_ID))
        self.db.users.insert(make_patient_doc(
            patient_id=OTHER_PATIENT_ID, practitioners=[DOCTOR_ID]))
        self.db["health_records"].insert(make_health_record_doc(OTHER_PATIENT_ID))
        response = await self.client.get(
            f"/api/patients/health-records?patient_id={OTHER_PATIENT_ID}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()), 1)

    async def test_admin_exempt_and_missing_patient_404(self):
        """admin 豁免归属校验；患者不存在 404 PATIENT_NOT_FOUND。"""
        self._setup(make_user(role="admin", user_id=ADMIN_ID))
        self.db["health_records"].insert(make_health_record_doc(OTHER_PATIENT_ID))
        response = await self.client.get(
            f"/api/patients/health-records?patient_id={OTHER_PATIENT_ID}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()), 1)

        self._setup(make_user(role="doctor", user_id=DOCTOR_ID))
        response = await self.client.get(
            f"/api/patients/health-records?patient_id={OTHER_PATIENT_ID}")
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json()["error"], "PATIENT_NOT_FOUND")


# ── GET /patients/communications ─────────────────────────────────────────────

def make_conversation_doc(participant1, participant2, conv_id=CONVERSATION_ID):
    return {
        "_id": conv_id, "participant1_id": participant1,
        "participant2_id": participant2, "status": "active",
        "last_message_time": datetime.utcnow(), "created_at": datetime.utcnow(),
    }


def make_message_doc(conversation_id=CONVERSATION_ID, recipient=None, read=False):
    return {
        "_id": str(ObjectId()), "conversation_id": conversation_id,
        "sender_id": DOCTOR_ID, "recipient_id": recipient or PATIENT_ID,
        "content": "合成消息", "type": "text", "timestamp": datetime.utcnow(),
        "read": read, "deleted": False, "attachments": [], "metadata": {},
    }


class PatientCommunicationsTests(PatientDomainEndpointTests):
    async def test_patient_empty_conversations_returns_real_empty_list(self):
        """空库空态：无会话时如实返回 []。"""
        self._setup(make_user())
        response = await self.client.get("/api/patients/communications")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [])

    async def test_patient_conversations_with_unread_count(self):
        """本人会话列表真实形状：参与者任一匹配本人 + 真实未读计数 + 对方信息。"""
        self._setup(make_user())
        self.db.conversations.insert(
            make_conversation_doc(PATIENT_ID, DOCTOR_ID))
        self.db.conversations.insert(make_conversation_doc(
            OTHER_PATIENT_ID, str(ObjectId()), conv_id=str(ObjectId())))
        self.db.messages.insert(make_message_doc(recipient=PATIENT_ID))
        self.db.messages.insert(make_message_doc(recipient=PATIENT_ID))
        self.db.messages.insert(make_message_doc(recipient=PATIENT_ID, read=True))
        self.db.users.insert({"_id": DOCTOR_ID, "name": "合成医生", "role": "doctor"})
        response = await self.client.get("/api/patients/communications")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["id"], CONVERSATION_ID)
        self.assertEqual(body[0]["unread_count"], 2)
        self.assertEqual(body[0]["other_user"]["name"], "合成医生")

    async def test_forbidden_for_non_patient(self):
        """非患者角色 403：本端点为患者自助语义。"""
        self._setup(make_user(role="doctor", user_id=DOCTOR_ID))
        response = await self.client.get("/api/patients/communications")
        self.assertEqual(response.status_code, 403, response.text)


class PatientSendMessageTests(PatientDomainEndpointTests):
    async def test_send_returns_real_message_shape(self):
        """发送消息 201：真实消息形状（服务端 id/时间戳/接收者推导）。"""
        self._setup(make_user())
        self.db.conversations.insert(make_conversation_doc(PATIENT_ID, DOCTOR_ID))
        response = await self.client.post("/api/patients/communications", json={
            "conversation_id": CONVERSATION_ID, "content": "你好医生"})
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["conversation_id"], CONVERSATION_ID)
        self.assertEqual(body["sender_id"], PATIENT_ID)
        self.assertEqual(body["recipient_id"], DOCTOR_ID)
        self.assertEqual(body["content"], "你好医生")
        self.assertFalse(body["read"])
        self.assertTrue(any(str(key) == body["id"] for key in self.db.messages.docs))

    async def test_send_missing_conversation_404(self):
        """会话不存在 404，不落库。"""
        self._setup(make_user())
        response = await self.client.post("/api/patients/communications", json={
            "conversation_id": str(ObjectId()), "content": "你好"})
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(self.db.messages.docs, {})

    async def test_send_non_participant_403(self):
        """非会话参与者 403。"""
        self._setup(make_user())
        self.db.conversations.insert(
            make_conversation_doc(OTHER_PATIENT_ID, DOCTOR_ID))
        response = await self.client.post("/api/patients/communications", json={
            "conversation_id": CONVERSATION_ID, "content": "你好"})
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.db.messages.docs, {})

    async def test_send_malformed_conversation_id_422(self):
        """畸形会话 ID 422。"""
        self._setup(make_user())
        response = await self.client.post("/api/patients/communications", json={
            "conversation_id": "not-an-objectid", "content": "你好"})
        self.assertEqual(response.status_code, 422, response.text)

    async def test_send_forbidden_for_doctor(self):
        """非患者角色 403。"""
        self._setup(make_user(role="doctor", user_id=DOCTOR_ID))
        response = await self.client.post("/api/patients/communications", json={
            "conversation_id": CONVERSATION_ID, "content": "你好"})
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.db.messages.docs, {})


if __name__ == "__main__":
    unittest.main()
