"""T44：康复端源端创建幂等与对账对齐契约测试（源端 0d28031 / T36 语义）。

用 httpx.MockTransport 复刻源端 T36 之后的创建语义：
- 可选 Idempotency-Key 绑定请求体指纹，失败响应不消费键，同键同体重放；
- ma_task_ref 同客户端活跃唯一（进行中判定 created/embedded），重复创建
  409 task_ref_conflict + existing_session_uuid/existing_status 指针；
- GET /v1/fill-sessions/by-task-ref 对账端点（404 session_not_found）。
全部合成数据，不触碰真实远端。
"""

import json
import hashlib
from urllib.parse import unquote

import httpx
from bson import ObjectId

from app.main import app
from app.integrations.forms import service
from app.integrations.forms.router import get_form_platform_client

from test_integration_forms_contract import (
    FormsContractFixture,
    FakeRemote,
    make_operator,
    make_remote_client,
    reviewed_documents,
)

SOURCE_OPERATOR_ID = 7


def source_fingerprint(payload):
    """与源端 FillSessionIdempotencyService.request_fingerprint 相同的规范化。"""
    canonical = json.dumps(
        {"payload": payload, "operator_user_id": SOURCE_OPERATOR_ID},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class T36FillSource(FakeRemote):
    """在 FakeRemote 目录能力之上复刻源端 0d28031 的创建/对账语义。"""

    def __init__(self):
        super().__init__()
        self.sessions = []            # 已创建会话（创建顺序，即对账 data 顺序）
        self.sessions_by_uuid = {}
        self.idempotency = {}         # key -> {"fingerprint": ..., "session": ...}
        self.replays = []             # 以重放响应返回的 session_uuid
        self.fail_next_create = 0     # 前 N 次创建在远端处理前断连（未创建）
        self.lose_response_next = 0   # 前 N 次创建已落库但 201 响应丢失
        self.conflict_next = False    # 下一次创建直接 409 idempotency_conflict

    def seed_live_session(self, *, ma_task_ref, session_uuid="sess-orphan", status="created"):
        """预置一个既有会话（模拟此前创建成功但康复端未拿到 201 的孤儿）。"""
        session = {
            "session_uuid": session_uuid, "status": status,
            "project_id": 1, "center_id": 2, "subject_id": 3, "questionnaire_id": 4,
            "ma_task_ref": ma_task_ref, "operator_user_id": SOURCE_OPERATOR_ID,
            "response_id": None, "expires_at": "2026-11-07T12:00:00Z",
            "created_at": "2026-11-07T10:00:00Z", "submitted_at": None,
        }
        self.sessions.append(session)
        self.sessions_by_uuid[session_uuid] = session
        return session

    def _live_by_ref(self, ref):
        if not ref:
            return None
        for session in self.sessions:
            if (session.get("ma_task_ref") == ref
                    and session["status"] in ("created", "embedded")):
                return session
        return None

    def _create_session(self, payload, key, fingerprint):
        session = {
            "session_uuid": f"sess-{len(self.sessions) + 1:04d}", "status": "created",
            "project_id": payload.get("project_id"), "center_id": payload.get("center_id"),
            "subject_id": payload.get("subject_id"),
            "questionnaire_id": payload.get("questionnaire_id"),
            "questionnaire_version_ref": payload.get("questionnaire_version_ref"),
            "visit_code": payload.get("visit_code"), "visit_name": payload.get("visit_name"),
            "ma_task_ref": payload.get("ma_task_ref"),
            "operator_user_id": SOURCE_OPERATOR_ID, "response_id": None,
            "expires_at": "2026-11-07T12:00:00Z",
            "created_at": "2026-11-07T10:00:00Z", "submitted_at": None,
        }
        self.sessions.append(session)
        self.sessions_by_uuid[session["session_uuid"]] = session
        if key:
            self.idempotency[key] = {"fingerprint": fingerprint, "session": dict(session)}
        return session

    def _create(self, request):
        payload = json.loads(request.content)
        key = (request.headers.get("Idempotency-Key") or "").strip()
        if self.fail_next_create:
            self.fail_next_create -= 1
            raise httpx.ReadError("simulated timeout", request=request)
        if self.conflict_next:
            self.conflict_next = False
            return httpx.Response(409, json={"code": "idempotency_conflict",
                                             "message": "该 Idempotency-Key 已用于不同的请求体"})
        fingerprint = source_fingerprint(payload)
        if key:
            record = self.idempotency.get(key)
            if record is not None:
                if record["fingerprint"] != fingerprint:
                    return httpx.Response(409, json={"code": "idempotency_conflict",
                                                     "message": "该 Idempotency-Key 已用于不同的请求体"})
                self.replays.append(record["session"]["session_uuid"])
                return httpx.Response(201, json=dict(record["session"], idempotent_replay=True),
                                      headers={"Idempotency-Replayed": "true"})
        ref = payload.get("ma_task_ref")
        ref = ref.strip() if isinstance(ref, str) else None
        live = self._live_by_ref(ref)
        if live is not None:
            return httpx.Response(409, json={
                "code": "task_ref_conflict",
                "message": "该 ma_task_ref 已存在进行中的填报会话",
                "details": {"existing_session_uuid": live["session_uuid"],
                            "existing_status": live["status"]}})
        if self.lose_response_next:
            self.lose_response_next -= 1
            self._create_session(payload, key, fingerprint)  # 已落库，响应丢失
            raise httpx.ReadError("simulated lost 201 response", request=request)
        session = self._create_session(payload, key, fingerprint)
        return httpx.Response(201, json=dict(session))

    def _by_task_ref(self, ref):
        matches = [s for s in self.sessions if s.get("ma_task_ref") == ref]
        if not matches:
            return httpx.Response(404, json={"code": "session_not_found",
                                             "message": "该任务引用下不存在填报会话"})
        return httpx.Response(200, json={"ma_task_ref": ref, "latest": matches[-1],
                                         "data": matches})

    def handler(self, request: httpx.Request) -> httpx.Response:
        is_catalog = request.url.path.endswith("/patient-reference") or request.url.path.endswith("/definition")
        (self.catalog_requests if is_catalog else self.requests).append(request)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer pilot-client.pilot-secret"):
            return httpx.Response(401, json={"code": "invalid_client"})
        path = request.url.path
        link, binding = reviewed_documents()
        if path == "/integration/v1/projects/1/centers/2/subjects/3/patient-reference":
            return httpx.Response(200, json=link["reference"])
        if path == "/integration/v1/forms/4/definition":
            return httpx.Response(200, json={"source": binding["source"], "version": binding["version_ref"],
                "form": {"form_id": 4, "project_id": 1, "title": "Synthetic form", "status": "active",
                         "current_version": binding["version_ref"]}})
        if path == "/integration/v1/fill-sessions" and request.method == "POST":
            return self._create(request)
        if path.startswith("/integration/v1/fill-sessions/by-task-ref/"):
            return self._by_task_ref(unquote(path.rsplit("/", 1)[1]))
        if path.startswith("/integration/v1/fill-sessions/") and request.method == "GET":
            session = self.sessions_by_uuid.get(path.rsplit("/", 1)[1])
            if session:
                return httpx.Response(200, json=dict(session))
            return httpx.Response(404, json={"code": "session_not_found"})
        return httpx.Response(404, json={"code": "not_found"})


class FillCreationIdempotencyContractTests(FormsContractFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.remote = T36FillSource()
        self.remote_client = make_remote_client(self.remote)
        app.dependency_overrides[get_form_platform_client] = lambda: self.remote_client

    def create_calls(self):
        return [r for r in self.remote.requests
                if r.url.path == "/integration/v1/fill-sessions" and r.method == "POST"]

    # ---- 对齐清单 1/6：统一幂等键 + 超时重试同键同体 ----

    async def test_timeout_retry_reuses_same_key_and_body(self):
        self.remote.fail_next_create = 1
        response = await self.client.post("/api/integrations/forms/fill-tasks",
                                          json=self.payload(), headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["session"]["sessionUuid"], "sess-0001")
        creates = self.create_calls()
        self.assertEqual(len(creates), 2)
        key = creates[0].headers.get("Idempotency-Key")
        self.assertTrue(key)
        self.assertLessEqual(len(key), 128)
        self.assertEqual(creates[1].headers.get("Idempotency-Key"), key)
        self.assertEqual(json.loads(creates[0].content), json.loads(creates[1].content))
        self.assertEqual(len(self.remote.sessions), 1)
        self.assertEqual(len(self.collection.docs), 1)

    async def test_lost_201_response_replays_same_session_via_key(self):
        # 第一次创建已在源端落库但响应丢失：同键重试 → 重放同一会话
        self.remote.lose_response_next = 1
        response = await self.client.post("/api/integrations/forms/fill-tasks",
                                          json=self.payload(), headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["session"]["sessionUuid"], "sess-0001")
        creates = self.create_calls()
        self.assertEqual(len(creates), 2)
        self.assertEqual(creates[0].headers.get("Idempotency-Key"),
                         creates[1].headers.get("Idempotency-Key"))
        self.assertEqual(self.remote.replays, ["sess-0001"])
        self.assertEqual(len(self.remote.sessions), 1)
        self.assertEqual(len(self.collection.docs), 1)

    # ---- 对齐清单 2：键冲突（改体重试）不重试、不落任务 ----

    async def test_idempotency_conflict_is_mapped_without_retry_or_task(self):
        self.remote.conflict_next = True
        response = await self.client.post("/api/integrations/forms/fill-tasks",
                                          json=self.payload(), headers=self.auth())
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["error"], "FORM_PLATFORM_REJECTED")
        self.assertEqual(response.json()["detail"]["details"]["remote_code"],
                         "idempotency_conflict")
        self.assertEqual(len(self.create_calls()), 1)  # 不重试
        self.assertEqual(len(self.remote.sessions), 0)
        self.assertEqual(self.collection.docs, {})

    # ---- 对齐清单 3：task_ref 409 指针找回 ----

    async def test_task_ref_conflict_pointer_adopts_orphan_session(self):
        self.remote.seed_live_session(ma_task_ref="ma-task-0001", session_uuid="sess-orphan")
        response = await self.client.post("/api/integrations/forms/fill-tasks",
                                          json=self.payload(), headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["session"]["sessionUuid"], "sess-orphan")
        self.assertEqual(body["maTaskRef"], "ma-task-0001")
        self.assertEqual(len(self.create_calls()), 1)  # 409 指针直接找回，不重试创建
        self.assertEqual(len(self.remote.sessions), 1)  # 未创建新会话
        stored = list(self.collection.docs.values())
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["session"]["session_uuid"], "sess-orphan")

    async def test_task_ref_conflict_returns_existing_local_task(self):
        first = await self.client.post("/api/integrations/forms/fill-tasks",
                                       json=self.payload(), headers=self.auth())
        self.assertEqual(first.status_code, 200, first.text)
        second = await self.client.post("/api/integrations/forms/fill-tasks",
                                        json=self.payload(), headers=self.auth())
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["id"], first.json()["id"])
        self.assertEqual(second.json()["session"]["sessionUuid"], "sess-0001")
        self.assertEqual(len(self.create_calls()), 2)
        self.assertEqual(len(self.remote.sessions), 1)
        self.assertEqual(len(self.collection.docs), 1)

    async def test_task_ref_conflict_across_operators_rejected_without_leak(self):
        first = await self.client.post("/api/integrations/forms/fill-tasks",
                                       json=self.payload(), headers=self.auth())
        self.assertEqual(first.status_code, 200, first.text)
        other = make_operator(user_id="507f1f77bcf86cd799439099")
        self.patient_doc["practitioners"].append(other.id)
        second = await self.client.post("/api/integrations/forms/fill-tasks",
                                        json=self.payload(), headers=self.auth(user=other))
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["detail"]["error"], "TASK_REF_CONFLICT")
        # 不泄露他人任务与会话标识
        self.assertNotIn(first.json()["id"], json.dumps(second.json()))
        self.assertNotIn("sess-0001", json.dumps(second.json()))
        self.assertEqual(len(self.collection.docs), 1)
        self.assertEqual(len(self.remote.sessions), 1)

    async def test_pointer_to_failed_task_surfaces_recovery_uncertainty(self):
        # 指针指向失败任务保留的远端会话（撤销/核查未收尾）→ 禁止重新发起，如实上报
        created = await self.client.post("/api/integrations/forms/fill-tasks",
                                         json=self.payload(), headers=self.auth())
        task_id = created.json()["id"]
        self.collection.docs[ObjectId(task_id)]["status"] = "failed"
        response = await self.client.post("/api/integrations/forms/fill-tasks",
                                          json=self.payload(), headers=self.auth())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["error"], "FILL_TASK_RECOVERY_UNCERTAIN")
        self.assertEqual(response.json()["detail"]["details"]["task_id"], task_id)
        self.assertEqual(response.json()["detail"]["details"]["session_uuid"], "sess-0001")
        self.assertEqual(len(self.remote.sessions), 1)
        self.assertEqual(len(self.collection.docs), 1)

    # ---- 对齐清单 4：by-task-ref 对账（超时后找回 / 404 处理） ----

    async def test_by_task_ref_recovers_session_after_repeated_timeouts(self):
        self.remote.seed_live_session(ma_task_ref="ma-task-0001", session_uuid="sess-orphan")
        self.remote.fail_next_create = 2
        response = await self.client.post("/api/integrations/forms/fill-tasks",
                                          json=self.payload(), headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["session"]["sessionUuid"], "sess-orphan")
        self.assertEqual(len(self.create_calls()), 2)
        self.assertTrue(any("by-task-ref" in r.url.path for r in self.remote.requests))
        self.assertEqual(len(self.remote.sessions), 1)
        self.assertEqual(len(self.collection.docs), 1)

    async def test_by_task_ref_404_keeps_unavailable_error_without_local_task(self):
        self.remote.fail_next_create = 2
        response = await self.client.post("/api/integrations/forms/fill-tasks",
                                          json=self.payload(), headers=self.auth())
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["error"], "FORM_PLATFORM_UNAVAILABLE")
        self.assertTrue(any("by-task-ref" in r.url.path for r in self.remote.requests))
        self.assertEqual(self.collection.docs, {})
        self.assertEqual(len(self.remote.sessions), 0)

    # ---- 对齐清单 5：终态会话不复活，同一引用可开新一轮 ----

    async def test_terminal_session_is_not_adopted_and_new_round_creates_new_session(self):
        self.remote.seed_live_session(ma_task_ref="ma-task-0001", session_uuid="sess-old",
                                      status="submitted")
        response = await self.client.post("/api/integrations/forms/fill-tasks",
                                          json=self.payload(), headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotEqual(response.json()["session"]["sessionUuid"], "sess-old")
        self.assertEqual(len(self.remote.sessions), 2)
        self.assertEqual(len(self.collection.docs), 1)

    async def test_adopted_session_validated_against_task_refs(self):
        # 指针指向的会话与当前任务引用不一致 → 拒绝收养，不误绑
        self.remote.seed_live_session(ma_task_ref="ma-task-0001", session_uuid="sess-orphan")
        self.remote.sessions[-1]["subject_id"] = 999
        response = await self.client.post("/api/integrations/forms/fill-tasks",
                                          json=self.payload(), headers=self.auth())
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["error"], "TASK_REF_SESSION_MISMATCH")
        self.assertEqual(self.collection.docs, {})

    # ---- 对齐清单 7：ma_task_ref 作为任务侧唯一引用 ----

    async def test_derived_task_ref_enables_dedup_for_callers_without_ref(self):
        first = await self.client.post("/api/integrations/forms/fill-tasks",
                                       json=self.payload(ma_task_ref=None), headers=self.auth())
        self.assertEqual(first.status_code, 200, first.text)
        derived = first.json()["maTaskRef"]
        self.assertTrue(derived.startswith("auto-"))
        self.assertLessEqual(len(derived), 160)
        second = await self.client.post("/api/integrations/forms/fill-tasks",
                                        json=self.payload(ma_task_ref=None), headers=self.auth())
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["id"], first.json()["id"])
        self.assertEqual(len(self.remote.sessions), 1)
        self.assertEqual(len(self.collection.docs), 1)

    async def test_derived_task_ref_deterministic_and_discriminates_operator(self):
        binding = {"_id": ObjectId(), "purpose": "followup"}
        refs = {"project_id": 1, "center_id": 2, "subject_id": 3, "questionnaire_id": 4}
        kwargs = dict(patient_id="p-1", refs=refs, binding=binding,
                      followup_visit_id=None, visit_code="V1")
        first = service._resolve_task_ref({"ma_task_ref": None}, operator_id="op-1", **kwargs)
        again = service._resolve_task_ref({"ma_task_ref": None}, operator_id="op-1", **kwargs)
        other = service._resolve_task_ref({"ma_task_ref": None}, operator_id="op-2", **kwargs)
        self.assertEqual(first, again)
        self.assertNotEqual(first, other)
        self.assertLessEqual(len(first), 160)
        # 显式引用原样透传（去首尾空白）
        self.assertEqual(service._resolve_task_ref({"ma_task_ref": " ref-1 "},
                        operator_id="op-1", **kwargs), "ref-1")

    async def test_explicit_task_ref_validated_for_reconcilability(self):
        for bad in ("x" * 161, "   ", 12345):
            with self.subTest(bad=bad):
                response = await self.client.post("/api/integrations/forms/fill-tasks",
                                                  json=self.payload(ma_task_ref=bad),
                                                  headers=self.auth())
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["detail"]["error"], "INVALID_TASK_REF")
        self.assertEqual(self.create_calls(), [])
        self.assertEqual(self.collection.docs, {})


if __name__ == "__main__":
    import unittest
    unittest.main()
