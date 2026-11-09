"""表单平台集成填报契约测试（Slice 2，隔离联调）。

用 httpx.MockTransport 模拟 113.44 远端：覆盖创建/确认/取消流程、患者归属
默认拒绝、凭证与远端错误类型化路径、以及确认证据的一致性核验。
全部使用内存数据与合成引用，不触碰任何真实数据。
"""

import json
import os
import unittest
from copy import deepcopy
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
from followup_transaction_fake import FakeTransactionClient

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


def _doc_matches(doc, query):
    """支持点路径的精确匹配（如 operator.user_id）。"""
    for key, value in query.items():
        current = doc
        for part in key.split("."):
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if isinstance(value, dict):
            if "$in" in value and not (any(item in value["$in"] for item in current)
                                       if isinstance(current, list) else current in value["$in"]):
                return False
            if "$ne" in value and current == value["$ne"]:
                return False
            continue
        if current != value:
            return False
    return True


class FakeCursor:
    """模拟 motor find 游标的 sort/skip/limit 链与异步迭代。"""

    def __init__(self, docs):
        self._docs = list(docs)
        self._skip = 0
        self._limit = None

    def sort(self, key, direction):
        self._docs.sort(key=lambda d: d.get(key) or datetime.min, reverse=direction < 0)
        return self

    def skip(self, n):
        self._skip = n
        return self

    def limit(self, n):
        self._limit = n
        return self

    def __aiter__(self):
        end = None if self._limit is None else self._skip + self._limit
        self._iter = iter(self._docs[self._skip:end])
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class FakeTaskCollection:
    """模拟 motor 集合：内存字典存储，返回值形状与 AsyncIOMotorCollection 对齐。"""

    def __init__(self):
        self.docs = {}

    async def insert_one(self, doc, **kwargs):
        _id = doc.get("_id") or ObjectId()
        doc["_id"] = _id
        if _id in self.docs:
            from pymongo.errors import DuplicateKeyError
            raise DuplicateKeyError("duplicate task")
        self.docs[_id] = deepcopy(doc)
        return SimpleNamespace(inserted_id=_id)

    async def find_one(self, query, **kwargs):
        doc = self.docs.get(query["_id"])
        return deepcopy(doc) if doc and _doc_matches(doc, query) else None

    def find(self, query):
        return FakeCursor([d for d in self.docs.values() if _doc_matches(d, query)])

    async def count_documents(self, query):
        return len([d for d in self.docs.values() if _doc_matches(d, query)])

    async def update_one(self, query, update, **kwargs):
        doc = self.docs.get(query["_id"])
        matched = bool(doc and _doc_matches(doc, query))
        if matched:
            for key, value in update.get("$set", {}).items():
                target = doc
                parts = key.split(".")
                for part in parts[:-1]:
                    target = target.setdefault(part, {})
                target[parts[-1]] = deepcopy(value)
            for key, value in update.get("$inc", {}).items():
                doc[key] = doc.get(key, 0) + value
        return SimpleNamespace(modified_count=int(matched), matched_count=int(matched))


class FakeVisitCollection:
    """模拟 followup_records 集合：仅覆盖节点联动用到的 find_one/update_one。"""

    def __init__(self):
        self.docs = {}

    async def find_one(self, query, **kwargs):
        doc = self.docs.get(query.get("_id"))
        return deepcopy(doc) if doc and _doc_matches(doc, query) else None

    async def update_one(self, query, update, **kwargs):
        doc = self.docs.get(query.get("_id"))
        if not doc or not _doc_matches(doc, query):
            return SimpleNamespace(modified_count=0, matched_count=0)
        for key, value in (update.get("$set") or {}).items():
            doc[key] = value
        for key, value in (update.get("$addToSet") or {}).items():
            items = doc.setdefault(key, [])
            if value not in items:
                items.append(value)
        for key, value in update.get("$inc", {}).items():
            doc[key] = doc.get(key, 0) + value
        return SimpleNamespace(modified_count=1, matched_count=1)


def make_database(patient_doc):
    database = MagicMock()
    collection = FakeTaskCollection()
    visits = FakeVisitCollection()
    recovery_events = FakeTaskCollection()
    users = MagicMock()
    users.find_one = AsyncMock(return_value=patient_doc)
    users.find = lambda query, projection=None: FakeCursor(
        [patient_doc] if patient_doc and _doc_matches(patient_doc, query) else [])
    database.users = users
    database.command = AsyncMock(return_value={"setName": "test_rs", "logicalSessionTimeoutMinutes": 30})

    def getitem(name):
        if name == task_models.COLLECTION_NAME:
            return collection
        if name == "followup_records":
            return visits
        if name == "integration_recovery_events":
            return recovery_events
        return MagicMock()

    database.__getitem__.side_effect = getitem
    database.client = FakeTransactionClient({task_models.COLLECTION_NAME: collection,
                                             "followup_records": visits,
                                             "integration_recovery_events": recovery_events})
    return database, collection, visits


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
        fill_feature = patch.dict(os.environ, {"FORM_PLATFORM_FILL_ENABLED": "true"})
        fill_feature.start()
        self.addCleanup(fill_feature.stop)
        self.operator = make_operator()
        self.patient_doc = make_patient_doc()
        self.remote = FakeRemote()
        self.database, self.collection, self.visit_collection = make_database(self.patient_doc)

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

    def make_visit(self, visit_code="V1", status="awaiting_fill", patient_id=PATIENT_ID):
        """在内存 followup_records 里落一个随访节点，返回其字符串 ID。"""
        vid = ObjectId()
        self.visit_collection.docs[vid] = {
            "_id": vid, "patient_id": patient_id, "status": status,
            "visit_code": visit_code,
        }
        return str(vid)

    def visit_doc(self, visit_id):
        return self.visit_collection.docs[ObjectId(visit_id)]

    async def fetch_task(self, task_id):
        return await self.client.get(
            f"/api/integrations/forms/fill-tasks/{task_id}", headers=self.auth())

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

    async def test_list_scoped_to_creator_with_filters(self):
        first = await self.client.post("/api/integrations/forms/fill-tasks",
                                       json=self.payload(), headers=self.auth())
        second = await self.client.post("/api/integrations/forms/fill-tasks",
                                        json=self.payload(), headers=self.auth())
        # 取消第二个任务，验证状态过滤
        await self.client.post(
            f"/api/integrations/forms/fill-tasks/{second.json()['id']}/cancel",
            headers=self.auth())

        response = await self.client.get("/api/integrations/forms/fill-tasks",
                                         headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["total"], 2)
        self.assertEqual(len(body["items"]), 2)
        # 倒序：最新的在前
        self.assertEqual(body["items"][0]["id"], second.json()["id"])
        # 输出不含令牌材料
        self.assertNotIn("embedToken", json.dumps(body))

        # 状态过滤
        filtered = await self.client.get(
            "/api/integrations/forms/fill-tasks?status=cancelled", headers=self.auth())
        self.assertEqual(filtered.json()["total"], 1)
        self.assertEqual(filtered.json()["items"][0]["id"], second.json()["id"])

        # 非法状态过滤被拒绝
        bad = await self.client.get(
            "/api/integrations/forms/fill-tasks?status=bogus", headers=self.auth())
        self.assertEqual(bad.status_code, 422)
        self.assertEqual(bad.json()["detail"]["error"], "INVALID_STATUS_FILTER")

    async def test_list_forbidden_tasks_hidden_from_other_operator(self):
        await self.client.post("/api/integrations/forms/fill-tasks",
                               json=self.payload(), headers=self.auth())
        other = make_operator(role="doctor", user_id="507f1f77bcf86cd799439099")
        response = await self.client.get("/api/integrations/forms/fill-tasks",
                                         headers=self.auth(user=other))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 0)
        self.assertEqual(response.json()["items"], [])

        # admin 可以看到全部
        admin = make_operator(role="admin", user_id="507f1f77bcf86cd7994390aa")
        admin_view = await self.client.get("/api/integrations/forms/fill-tasks",
                                           headers=self.auth(user=admin))
        self.assertEqual(admin_view.json()["total"], 1)

    async def test_patient_assignment_revocation_blocks_all_task_access_before_remote_calls(self):
        created = await self.client.post("/api/integrations/forms/fill-tasks",
                                        json=self.payload(), headers=self.auth())
        task_id = created.json()["id"]
        self.patient_doc["practitioners"] = []
        self.remote.requests.clear()
        for method, suffix in (("get", ""), ("get", "/embed-url"),
                               ("post", "/confirm"), ("post", "/cancel")):
            with self.subTest(method=method, suffix=suffix):
                response = await getattr(self.client, method)(
                    f"/api/integrations/forms/fill-tasks/{task_id}{suffix}", headers=self.auth())
                self.assertEqual(response.status_code, 403, response.text)
                self.assertEqual(response.json()["detail"]["error"], "PATIENT_NOT_ASSIGNED")
        listed = await self.client.get("/api/integrations/forms/fill-tasks", headers=self.auth())
        self.assertEqual(listed.json()["items"], [])
        self.assertEqual(listed.json()["total"], 0)
        explicit = await self.client.get("/api/integrations/forms/fill-tasks",
            params={"patient_id": PATIENT_ID}, headers=self.auth())
        self.assertEqual(explicit.status_code, 403)
        self.assertEqual(self.remote.requests, [])
        self.assertEqual(self.collection.docs[ObjectId(task_id)]["status"], "session_created")

    async def test_patient_role_cannot_reuse_previous_medical_task_identity(self):
        created = await self.client.post("/api/integrations/forms/fill-tasks",
                                        json=self.payload(), headers=self.auth())
        task_id = created.json()["id"]
        downgraded = make_operator(role="patient")
        self.remote.requests.clear()
        for path in (f"/api/integrations/forms/fill-tasks/{task_id}", "/api/integrations/forms/fill-tasks"):
            response = await self.client.get(path, headers=self.auth(user=downgraded))
            self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.remote.requests, [])

    async def test_admin_retains_existing_task_access_after_local_assignment_removed(self):
        created = await self.client.post("/api/integrations/forms/fill-tasks",
                                        json=self.payload(), headers=self.auth())
        self.patient_doc["practitioners"] = []
        admin = make_operator(role="admin", user_id="507f1f77bcf86cd7994390aa")
        response = await self.client.get(f"/api/integrations/forms/fill-tasks/{created.json()['id']}",
                                         headers=self.auth(user=admin))
        self.assertEqual(response.status_code, 200, response.text)

    # ---- FU01 S4：节点联动（followup_visit_id） ----

    async def test_create_with_visit_link_binds_node_and_inherits_visit_code(self):
        visit_id = self.make_visit(visit_code="V1")
        response = await self.client.post(
            "/api/integrations/forms/fill-tasks",
            # 不传 visit_code：应从节点继承（设计稿 §3.3 第 1 步）
            json=self.payload(visit_code=None, followup_visit_id=visit_id),
            headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["followupVisitId"], visit_id)
        self.assertEqual(body["visitCode"], "V1")

        stored = list(self.collection.docs.values())[0]
        self.assertEqual(stored["followup_visit_id"], visit_id)
        # 节点反向索引 fill_task_ids 追加任务 ID
        node = self.visit_doc(visit_id)
        self.assertEqual([str(t) for t in node["fill_task_ids"]], [body["id"]])

    async def test_create_rejects_missing_or_malformed_visit(self):
        missing = await self.client.post(
            "/api/integrations/forms/fill-tasks",
            json=self.payload(followup_visit_id=str(ObjectId())), headers=self.auth())
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["detail"]["error"], "FOLLOWUP_VISIT_NOT_FOUND")

        malformed = await self.client.post(
            "/api/integrations/forms/fill-tasks",
            json=self.payload(followup_visit_id="not-an-objectid"), headers=self.auth())
        self.assertEqual(malformed.status_code, 422)
        self.assertEqual(malformed.json()["detail"]["error"], "INVALID_FOLLOWUP_VISIT")
        self.assertEqual(len(self.collection.docs), 0)

    async def test_create_rejects_visit_of_another_patient(self):
        visit_id = self.make_visit(patient_id=str(ObjectId()))  # 节点属于其他患者
        response = await self.client.post(
            "/api/integrations/forms/fill-tasks",
            json=self.payload(followup_visit_id=visit_id), headers=self.auth())
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["error"],
                         "FOLLOWUP_VISIT_PATIENT_MISMATCH")
        self.assertEqual(len(self.collection.docs), 0)

    async def test_confirm_linked_task_writes_node_in_review(self):
        visit_id = self.make_visit(visit_code="V1", status="awaiting_fill")
        created = await self.client.post(
            "/api/integrations/forms/fill-tasks",
            json=self.payload(followup_visit_id=visit_id), headers=self.auth())
        task_id = created.json()["id"]
        self.remote.session_body["status"] = "submitted"
        self.remote.session_body["response_id"] = RESPONSE_ID

        response = await self.client.post(
            f"/api/integrations/forms/fill-tasks/{task_id}/confirm", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "confirmed")

        node = self.visit_doc(visit_id)
        # 节点状态 → in_review（schemas/followup.FollowUpStatus.IN_REVIEW）
        self.assertEqual(node["status"], "in_review")
        # effective_response 指向该任务
        effective = node["effective_response"]
        self.assertEqual(effective["task_id"], task_id)
        self.assertEqual(effective["response_id"], RESPONSE_ID)
        self.assertEqual(effective["visit_code"], "V1")
        self.assertIn("confirmed_at", effective)
        # 反向索引含任务 ID（创建时已追加，确认后不重复）
        self.assertEqual([str(t) for t in node["fill_task_ids"]], [task_id])

    async def test_confirm_rejects_visit_code_mismatch_and_keeps_task_unconfirmed(self):
        visit_id = self.make_visit(visit_code="V2")  # 节点与任务/答卷访视不一致
        created = await self.client.post(
            "/api/integrations/forms/fill-tasks",
            json=self.payload(followup_visit_id=visit_id), headers=self.auth())
        task_id = created.json()["id"]
        self.remote.session_body["status"] = "submitted"
        self.remote.session_body["response_id"] = RESPONSE_ID

        response = await self.client.post(
            f"/api/integrations/forms/fill-tasks/{task_id}/confirm", headers=self.auth())
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["error"], "RESPONSE_MISMATCH")

        # 任务未落 confirmed、节点未被回写
        task = await self.fetch_task(task_id)
        self.assertNotEqual(task.json()["status"], "confirmed")
        self.assertIsNone(task.json()["confirmation"])
        node = self.visit_doc(visit_id)
        self.assertEqual(node["status"], "awaiting_fill")
        self.assertIsNone(node.get("effective_response"))

    async def test_confirm_rejects_remote_response_from_another_visit(self):
        visit_id = self.make_visit(visit_code="V1")
        created = await self.client.post(
            "/api/integrations/forms/fill-tasks",
            json=self.payload(followup_visit_id=visit_id), headers=self.auth())
        task_id = created.json()["id"]
        self.remote.session_body["status"] = "submitted"
        self.remote.session_body["response_id"] = RESPONSE_ID
        self.remote.response_body["visit_code"] = "V9"  # 远端答卷串访视

        response = await self.client.post(
            f"/api/integrations/forms/fill-tasks/{task_id}/confirm", headers=self.auth())
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["error"], "RESPONSE_MISMATCH")
        self.assertEqual(self.visit_doc(visit_id)["status"], "awaiting_fill")

    async def test_confirm_rejects_terminal_visit(self):
        visit_id = self.make_visit()
        created = await self.client.post(
            "/api/integrations/forms/fill-tasks",
            json=self.payload(followup_visit_id=visit_id), headers=self.auth())
        task_id = created.json()["id"]
        self.visit_doc(visit_id)["status"] = "completed"
        self.remote.session_body["status"] = "submitted"
        self.remote.session_body["response_id"] = RESPONSE_ID

        response = await self.client.post(
            f"/api/integrations/forms/fill-tasks/{task_id}/confirm", headers=self.auth())
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["error"], "FOLLOWUP_VISIT_TERMINAL")
        self.assertNotEqual(self.visit_doc(visit_id)["status"], "in_review")

    async def test_confirm_without_visit_link_keeps_legacy_behavior(self):
        # 无 followup_visit_id 的任务（试点调用形态）不触发任何节点状态转换
        visit_id = self.make_visit()
        created = await self.client.post(
            "/api/integrations/forms/fill-tasks",
            json=self.payload(), headers=self.auth())
        task_id = created.json()["id"]
        self.remote.session_body["status"] = "submitted"
        self.remote.session_body["response_id"] = RESPONSE_ID

        response = await self.client.post(
            f"/api/integrations/forms/fill-tasks/{task_id}/confirm", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "confirmed")
        self.assertIsNone(response.json()["followupVisitId"])
        node = self.visit_doc(visit_id)
        self.assertEqual(node["status"], "awaiting_fill")
        self.assertIsNone(node.get("effective_response"))
        self.assertNotIn("fill_task_ids", node)

    async def test_create_terminal_visit_rejected_before_remote_session(self):
        visit_id = self.make_visit(status="canceled")
        response = await self.client.post(
            "/api/integrations/forms/fill-tasks",
            json=self.payload(followup_visit_id=visit_id), headers=self.auth())
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.remote.requests, [])
        self.assertEqual(self.collection.docs, {})

    async def test_linked_creation_failure_rolls_back_link_and_cancels_remote(self):
        from pymongo.errors import OperationFailure
        visit_id = self.make_visit()
        original_insert = self.collection.insert_one
        attempts = 0

        async def fail_first_insert(doc, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OperationFailure("injected insert failure")
            return await original_insert(doc, **kwargs)

        self.collection.insert_one = fail_first_insert
        response = await self.client.post(
            "/api/integrations/forms/fill-tasks",
            json=self.payload(followup_visit_id=visit_id), headers=self.auth())
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(self.remote.session_body["status"], "cancelled")
        self.assertFalse(self.visit_doc(visit_id).get("fill_task_ids"))
        audit = next(iter(self.collection.docs.values()))
        self.assertEqual(audit["status"], "failed")
        self.assertFalse(audit["cleanup_required"])
        self.assertNotIn("fs_demo_token_value", repr(audit))

    async def test_unlinked_creation_failure_records_audit_and_cancels_remote(self):
        from pymongo.errors import OperationFailure
        original_insert = self.collection.insert_one

        async def fail_transaction_insert(doc, **kwargs):
            if kwargs.get("session") is not None:
                raise OperationFailure("injected independent task insert failure")
            return await original_insert(doc, **kwargs)

        self.collection.insert_one = fail_transaction_insert
        response = await self.client.post("/api/integrations/forms/fill-tasks",
            json=self.payload(), headers=self.auth())
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(self.remote.session_body["status"], "cancelled")
        audit = next(iter(self.collection.docs.values()))
        self.assertEqual(audit["status"], "failed")
        self.assertFalse(audit["cleanup_required"])
        self.assertIsNone(audit["followup_visit_id"])
        self.assertNotIn("fs_demo_token_value", repr(audit))

    async def test_unlinked_unknown_commit_retains_remote_and_records_recovery(self):
        from app.core.exceptions import AppBaseException
        unknown = AppBaseException("unknown", status_code=503,
                                   details={"commit_result_unknown": True})
        self.remote_client.cancel_fill_session = AsyncMock()
        with patch("app.db.transactions.run_followup_transaction", AsyncMock(side_effect=unknown)):
            response = await self.client.post("/api/integrations/forms/fill-tasks",
                json=self.payload(), headers=self.auth())
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["detail"]["error"], "FILL_TASK_COMMIT_UNCERTAIN")
        self.remote_client.cancel_fill_session.assert_not_awaited()
        recovery = next(iter(self.database["integration_recovery_events"].docs.values()))
        self.assertIsNone(recovery["followup_visit_id"])
        self.assertEqual(recovery["session_uuid"], SESSION_UUID)
        self.assertEqual(self.remote.session_body["status"], "created")
        self.assertEqual(self.collection.docs, {})

    async def test_standalone_rejected_before_any_remote_creation(self):
        self.database.command.return_value = {"logicalSessionTimeoutMinutes": 30}
        response = await self.client.post("/api/integrations/forms/fill-tasks",
            json=self.payload(), headers=self.auth())
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["detail"]["error"], "FOLLOWUP_TRANSACTION_UNAVAILABLE")
        self.assertEqual(self.remote.requests, [])
        self.assertEqual(self.collection.docs, {})

    async def test_linked_creation_cleanup_failure_is_durable_and_explicit(self):
        from pymongo.errors import OperationFailure
        from app.integrations.forms.client import FormPlatformUnavailable
        visit_id = self.make_visit()
        original_insert = self.collection.insert_one
        attempts = 0

        async def fail_first_insert(doc, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OperationFailure("injected insert failure")
            return await original_insert(doc, **kwargs)

        self.collection.insert_one = fail_first_insert
        self.remote_client.cancel_fill_session = AsyncMock(side_effect=FormPlatformUnavailable("offline"))
        response = await self.client.post(
            "/api/integrations/forms/fill-tasks",
            json=self.payload(followup_visit_id=visit_id), headers=self.auth())
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["detail"]["error"], "FILL_TASK_CLEANUP_REQUIRED")
        audit = next(iter(self.collection.docs.values()))
        self.assertTrue(audit["cleanup_required"])
        self.assertFalse(self.visit_doc(visit_id).get("fill_task_ids"))

    async def test_unknown_creation_commit_keeps_remote_and_records_recovery(self):
        from app.core.exceptions import AppBaseException
        visit_id = self.make_visit()
        unknown = AppBaseException("unknown", status_code=503,
                                   details={"commit_result_unknown": True})
        self.remote_client.cancel_fill_session = AsyncMock()
        with patch("app.db.transactions.run_followup_transaction", AsyncMock(side_effect=unknown)):
            response = await self.client.post(
                "/api/integrations/forms/fill-tasks",
                json=self.payload(followup_visit_id=visit_id), headers=self.auth())
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["detail"]["error"], "FILL_TASK_COMMIT_UNCERTAIN")
        self.remote_client.cancel_fill_session.assert_not_awaited()
        recovery = next(iter(self.database["integration_recovery_events"].docs.values()))
        self.assertEqual(recovery["status"], "pending_commit_verification")
        self.assertEqual(recovery["session_uuid"], SESSION_UUID)
        self.assertNotIn("fs_demo_token_value", repr(recovery))
        self.assertEqual(self.collection.docs, {})

    async def test_linked_confirmation_failure_rolls_back_both_documents(self):
        from pymongo.errors import OperationFailure
        visit_id = self.make_visit()
        created = await self.client.post("/api/integrations/forms/fill-tasks",
            json=self.payload(followup_visit_id=visit_id), headers=self.auth())
        task_id = created.json()["id"]
        self.remote.session_body.update(status="submitted", response_id=RESPONSE_ID)
        original_update = self.collection.update_one

        async def fail_confirmation(query, update, **kwargs):
            if update.get("$set", {}).get("status") == "confirmed":
                raise OperationFailure("injected task failure")
            return await original_update(query, update, **kwargs)

        self.collection.update_one = fail_confirmation
        response = await self.client.post(
            f"/api/integrations/forms/fill-tasks/{task_id}/confirm", headers=self.auth())
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(self.visit_doc(visit_id)["status"], "awaiting_fill")
        self.assertIsNone(self.visit_doc(visit_id).get("effective_response"))
        self.assertNotEqual(self.collection.docs[ObjectId(task_id)]["status"], "confirmed")

    async def test_cancel_during_remote_confirmation_cannot_resurrect_visit(self):
        visit_id = self.make_visit()
        created = await self.client.post("/api/integrations/forms/fill-tasks",
            json=self.payload(followup_visit_id=visit_id), headers=self.auth())
        task_id = created.json()["id"]
        self.remote.session_body.update(status="submitted", response_id=RESPONSE_ID)
        original_response = self.remote_client.get_response

        async def cancel_before_response(response_id):
            body = await original_response(response_id)
            self.visit_doc(visit_id).update(status="canceled", mutation_version=2)
            return body

        self.remote_client.get_response = cancel_before_response
        response = await self.client.post(
            f"/api/integrations/forms/fill-tasks/{task_id}/confirm", headers=self.auth())
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.visit_doc(visit_id)["status"], "canceled")
        self.assertNotEqual(self.collection.docs[ObjectId(task_id)]["status"], "confirmed")

    async def test_legacy_single_session_doc_confirm_compatibility(self):
        # 存量文档形状：只有旧单 session 字段、无 fill_sessions，确认路径照常工作
        legacy = {
            "_id": ObjectId(),
            "patient_id": PATIENT_ID,
            "operator": {"user_id": OPERATOR_ID, "role": "doctor", "remote_user_id": 7},
            "remote_refs": {"project_id": 1, "center_id": 2, "subject_id": 3,
                            "questionnaire_id": 4, "remote_operator_user_id": 7},
            "allowed_origin": ORIGIN,
            "visit_code": "V1", "visit_name": None, "ma_task_ref": "ma-legacy",
            "status": "submitted",
            "session": {"session_uuid": SESSION_UUID, "embed_token_hash": "legacy-hash",
                        "embed_url": "https://form.example/integration/embed/fs_demo",
                        "response_id": None, "expires_at": None},
            "confirmation": None, "last_error": None,
            "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
            "confirmed_at": None,
        }
        self.collection.docs[legacy["_id"]] = legacy
        self.remote.session_body["status"] = "submitted"
        self.remote.session_body["response_id"] = RESPONSE_ID

        response = await self.client.post(
            f"/api/integrations/forms/fill-tasks/{legacy['_id']}/confirm",
            headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "confirmed")

        stored = self.collection.docs[legacy["_id"]]
        # 旧字段镜像被推进（旧字段优先），fill_sessions 渐进补建
        self.assertEqual(stored["session"]["response_id"], RESPONSE_ID)
        self.assertEqual(len(stored["fill_sessions"]), 1)
        self.assertEqual(stored["fill_sessions"][-1]["confirmation"]["response_id"],
                         RESPONSE_ID)
        # 兼容读取：旧字段优先 / 数组回退两条路径均可取到活动会话
        self.assertEqual(task_models.active_session(stored)["session_uuid"], SESSION_UUID)
        array_only = {"session": {}, "fill_sessions": [{"session_uuid": "sess-new"}]}
        self.assertEqual(task_models.active_session(array_only)["session_uuid"], "sess-new")


if __name__ == "__main__":
    unittest.main()
