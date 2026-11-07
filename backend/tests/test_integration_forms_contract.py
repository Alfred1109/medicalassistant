"""表单平台集成填报契约测试（Slice 2，隔离联调）。

用 httpx.MockTransport 模拟 113.44 远端：覆盖创建/确认/取消流程、患者归属
默认拒绝、凭证与远端错误类型化路径、以及确认证据的一致性核验。
全部使用内存数据与合成引用，不触碰任何真实数据。
"""

import json
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
from bson import ObjectId
from unittest.mock import patch

from app.core.config import settings
from app.db.mongodb import get_database
from app.main import app
from app.schemas.user import UserResponse
from app.services.user_service import UserService
from app.integrations.forms import models as task_models
from app.integrations.forms.client import FormPlatformClient
from app.integrations.forms.router import get_form_platform_client

ORIGIN = "https://127.0.0.1:5502"
OPERATOR_ID = "507f1f77bcf86cd799439011"
PATIENT_ID = str(ObjectId())
SESSION_UUID = "sess-0001"
RESPONSE_ID = 42


def make_operator(role="doctor", user_id=OPERATOR_ID):
    now = datetime.utcnow()
    return UserResponse(id=user_id, email="actor@example.com", name="合成医生",
                        role=role, is_active=True, createdAt=now, updatedAt=now)


def make_patient_doc(practitioners=(OPERATOR_ID,)):
    return {"_id": ObjectId(PATIENT_ID), "role": "patient",
            "name": "合成患者", "practitioners": list(practitioners)}


class FakeTaskCollection:
    """模拟 motor 集合：内存字典存储，返回值形状与 AsyncIOMotorCollection 对齐。"""

    def __init__(self):
        self.docs = {}

    async def insert_one(self, doc):
        _id = ObjectId()
        doc["_id"] = _id
        self.docs[_id] = doc
        return SimpleNamespace(inserted_id=_id)

    async def find_one(self, query):
        return self.docs.get(query["_id"])

    async def update_one(self, query, update):
        doc = self.docs.get(query["_id"])
        if doc:
            doc.update(update["$set"])
        return SimpleNamespace(modified_count=1 if doc else 0)


def make_database(patient_doc):
    database = MagicMock()
    collection = FakeTaskCollection()
    users = MagicMock()
    users.find_one = AsyncMock(return_value=patient_doc)
    database.users = users

    def getitem(name):
        return collection if name == task_models.COLLECTION_NAME else MagicMock()

    database.__getitem__.side_effect = getitem
    return database, collection


class FakeRemote:
    """模拟 113.44 集成 API 的最小路由表。"""

    def __init__(self):
        self.requests = []
        self.session_body = {
            "session_uuid": SESSION_UUID, "status": "created",
            "embed_url": f"https://form.example/integration/embed/fs_demo",
            "embed_token": "fs_demo_token_value",
            "expires_at": "2026-11-07T12:00:00Z",
            "response_id": None,
        }
        self.response_body = {
            "response_id": RESPONSE_ID, "status": "submitted",
            "project_id": 1, "subject_id": 3, "questionnaire_id": 4,
            "operator_user_id": 7, "visit_code": "V1",
            "submitted_at": "2026-11-07T11:00:00Z",
            "answers": [{"question_id": 10, "answer_text": "训练已完成"}],
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer pilot-client.pilot-secret"):
            return httpx.Response(401, json={"code": "invalid_client"})
        path = request.url.path
        if path == "/integration/v1/fill-sessions" and request.method == "POST":
            return httpx.Response(201, json=self.session_body)
        if path == f"/integration/v1/fill-sessions/{SESSION_UUID}" and request.method == "GET":
            return httpx.Response(200, json=self.session_body)
        if path == f"/integration/v1/fill-sessions/{SESSION_UUID}/cancel":
            self.session_body["status"] = "cancelled"
            return httpx.Response(200, json=self.session_body)
        if path == f"/integration/v1/responses/{RESPONSE_ID}" and request.method == "GET":
            return httpx.Response(200, json=self.response_body)
        return httpx.Response(404, json={"code": "not_found"})


class UnreachableRemote:
    def handler(self, request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)


def make_remote_client(remote):
    return FormPlatformClient(
        base_url="https://form.example", client_id="pilot-client",
        client_secret="pilot-secret", timeout_seconds=5,
        transport=httpx.MockTransport(remote.handler),
    )


class IntegrationFormsContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.operator = make_operator()
        self.patient_doc = make_patient_doc()
        self.remote = FakeRemote()
        self.database, self.collection = make_database(self.patient_doc)

        async def fake_database():
            yield self.database

        self.remote_client = make_remote_client(self.remote)
        app.dependency_overrides[get_database] = fake_database
        app.dependency_overrides[get_form_platform_client] = lambda: self.remote_client
        # get_current_user 内部通过 UserService 查库；按 test_auth_contract 的模式打桩
        self.get_user_mock = AsyncMock(return_value=self.operator)
        self.lookup = patch.object(UserService, "get_user_by_id", new=self.get_user_mock)
        self.lookup.start()
        self.client = httpx.AsyncClient(app=app, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        self.lookup.stop()
        app.dependency_overrides.clear()

    def auth(self, user=None):
        from jose import jwt
        user = user or self.operator
        # get_current_user 的打桩返回值跟随令牌主体，保证角色/身份一致
        self.get_user_mock.return_value = user
        token = jwt.encode({"sub": user.id, "token_type": "access",
                            "exp": datetime.utcnow() + timedelta(minutes=5)},
                           settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return {"Authorization": f"Bearer {token}"}

    def payload(self, **overrides):
        body = {
            "patient_id": PATIENT_ID,
            "remote_project_id": 1,
            "remote_center_id": 2,
            "remote_subject_id": 3,
            "remote_questionnaire_id": 4,
            "remote_operator_user_id": 7,
            "allowed_origin": ORIGIN,
            "visit_code": "V1",
            "ma_task_ref": "ma-task-0001",
        }
        body.update(overrides)
        return body

    async def test_create_requires_authentication(self):
        response = await self.client.post("/api/integrations/forms/fill-tasks",
                                          json=self.payload())
        self.assertEqual(response.status_code, 401)

    async def test_create_rejects_operator_without_patient_assignment(self):
        self.patient_doc["practitioners"] = ["someone-else"]
        response = await self.client.post("/api/integrations/forms/fill-tasks",
                                          json=self.payload(), headers=self.auth())
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["error"], "PATIENT_NOT_ASSIGNED")
        self.assertEqual(self.remote.requests, [])

    async def test_create_rejects_patient_role_operator(self):
        response = await self.client.post(
            "/api/integrations/forms/fill-tasks", json=self.payload(),
            headers=self.auth(user=make_operator(role="patient")))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["error"], "OPERATOR_ROLE_NOT_ALLOWED")

    async def test_create_success_returns_embed_token_once_and_stores_hash(self):
        response = await self.client.post("/api/integrations/forms/fill-tasks",
                                          json=self.payload(), headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "session_created")
        self.assertEqual(body["embedToken"], "fs_demo_token_value")
        task_id = body["id"]

        stored = list(self.collection.docs.values())[0]
        # 明文令牌不落库；只存哈希
        self.assertNotIn("fs_demo_token_value", json.dumps(stored, default=str))
        self.assertEqual(stored["session"]["embed_token_hash"],
                         task_models.hash_embed_token("fs_demo_token_value"))

        # embed-url 可取（不含明文令牌）
        embed = await self.client.get(f"/api/integrations/forms/fill-tasks/{task_id}/embed-url",
                                      headers=self.auth())
        self.assertEqual(embed.status_code, 200)
        self.assertEqual(embed.json()["embedUrl"], self.remote.session_body["embed_url"])
        self.assertNotIn("embedToken", embed.json())

        # 再次创建的新任务不能复用旧令牌语义（这里只验证远端请求带凭证）
        self.assertTrue(self.remote.requests[0].headers["Authorization"]
                        .startswith("Bearer pilot-client."))

    async def test_create_maps_remote_authorization_rejection(self):
        # 凭证错误 → 远端 401 → 映射为 FORM_PLATFORM_AUTH_REJECTED
        self.remote_client = FormPlatformClient(
            base_url="https://form.example", client_id="pilot-client",
            client_secret="wrong-secret", timeout_seconds=5,
            transport=httpx.MockTransport(self.remote.handler))
        app.dependency_overrides[get_form_platform_client] = lambda: self.remote_client
        response = await self.client.post("/api/integrations/forms/fill-tasks",
                                          json=self.payload(), headers=self.auth())
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["error"], "FORM_PLATFORM_AUTH_REJECTED")
        # 远端失败不落任务
        self.assertEqual(len(self.collection.docs), 0)

    async def test_create_maps_unreachable_platform(self):
        self.remote_client = FormPlatformClient(
            base_url="https://form.example", client_id="pilot-client",
            client_secret="pilot-secret", timeout_seconds=1,
            transport=httpx.MockTransport(UnreachableRemote().handler))
        app.dependency_overrides[get_form_platform_client] = lambda: self.remote_client
        response = await self.client.post("/api/integrations/forms/fill-tasks",
                                          json=self.payload(), headers=self.auth())
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["error"], "FORM_PLATFORM_UNAVAILABLE")
        self.assertEqual(len(self.collection.docs), 0)

    async def test_get_task_forbidden_for_unrelated_operator(self):
        created = await self.client.post("/api/integrations/forms/fill-tasks",
                                         json=self.payload(), headers=self.auth())
        task_id = created.json()["id"]
        other = make_operator(role="doctor", user_id="507f1f77bcf86cd799439099")
        self.get_user_mock.return_value = other
        response = await self.client.get(f"/api/integrations/forms/fill-tasks/{task_id}",
                                         headers=self.auth(user=other))
        self.assertEqual(response.status_code, 403)

    async def test_confirm_not_yet_submitted_keeps_task_waiting(self):
        created = await self.client.post("/api/integrations/forms/fill-tasks",
                                         json=self.payload(), headers=self.auth())
        task_id = created.json()["id"]
        self.remote.session_body["status"] = "embedded"
        response = await self.client.post(
            f"/api/integrations/forms/fill-tasks/{task_id}/confirm", headers=self.auth())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "waiting_fill")
        self.assertNotEqual(body["status"], "confirmed")
        self.assertIsNone(body["confirmation"])

    async def test_confirm_submitted_verifies_evidence_and_updates_state(self):
        created = await self.client.post("/api/integrations/forms/fill-tasks",
                                         json=self.payload(), headers=self.auth())
        task_id = created.json()["id"]
        self.remote.session_body["status"] = "submitted"
        self.remote.session_body["response_id"] = RESPONSE_ID
        response = await self.client.post(
            f"/api/integrations/forms/fill-tasks/{task_id}/confirm", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "confirmed")
        self.assertEqual(body["confirmation"]["response_id"], RESPONSE_ID)
        self.assertEqual(body["confirmation"]["answers"],
                         [{"question_id": 10, "answer_text": "训练已完成"}])

    async def test_confirm_rejects_response_from_another_context(self):
        created = await self.client.post("/api/integrations/forms/fill-tasks",
                                         json=self.payload(), headers=self.auth())
        task_id = created.json()["id"]
        self.remote.session_body["status"] = "submitted"
        self.remote.session_body["response_id"] = RESPONSE_ID
        self.remote.response_body["subject_id"] = 999  # 答卷与任务引用不一致
        response = await self.client.post(
            f"/api/integrations/forms/fill-tasks/{task_id}/confirm", headers=self.auth())
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["error"], "RESPONSE_MISMATCH")

    async def test_cancel_updates_local_and_remote(self):
        created = await self.client.post("/api/integrations/forms/fill-tasks",
                                         json=self.payload(), headers=self.auth())
        task_id = created.json()["id"]
        response = await self.client.post(
            f"/api/integrations/forms/fill-tasks/{task_id}/cancel", headers=self.auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "cancelled")
        cancel_calls = [r for r in self.remote.requests
                        if r.url.path.endswith("/cancel")]
        self.assertEqual(len(cancel_calls), 1)


if __name__ == "__main__":
    unittest.main()
