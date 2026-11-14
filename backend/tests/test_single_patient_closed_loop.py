"""单患者跨系统闭环演练（T32）：建档→授权→关联→随访→填报→审阅→发布→反馈→撤权。

两个互补测试类，合成数据、隔离环境、可重复：

- SinglePatientClosedLoopLocalTests：纯 ASGI/测试客户端 + 内存假件，默认套件
  运行，不需要 Mongo/浏览器/真实源端。康复端全链路走真实代码；源端集成 API
  以 httpx.MockTransport 模拟（沿用 test_integration_forms_contract 的假远端），
  浏览器填报环节只覆盖康复端启动半程（launch 凭证校验）。
- SinglePatientClosedLoopSourceTests：继承 test_oidc_fill_interop 的隔离双应用
  夹具（真实源端进程 + 自签 TLS + 单节点副本集 Mongo + 真实 OIDC 登录/consent），
  以 REHAB_TEST_CLOSED_LOOP=1 显式开启；无该变量时整体 skip，不占默认套件。

已知开放缺口的对应处置（docs/embed-credential-contract-gap.md「2026-11-14 复核
状态」条目）：
- 创建超时幂等对账（缺口 2）：创建路径未演练超时分支，不在本测试发明对账语义。
- 跨端撤权恢复类边界（缺口 3）：只断言已实现的拒绝语义（撤销 link/binding 后
  既有任务 confirm 拒绝、新任务创建拒绝），不演练“恢复授权后旧会话处置”。
- outbox/API04 事件推送（缺口 5）：源端确认状态为纯轮询，confirm 即轮询核实。
"""

import json
import os
import unittest
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urljoin, urlsplit
from uuid import uuid4

import httpx
from bson import ObjectId

from followup_transaction_fake import FakeTransactionClient
from tests import test_integration_forms_contract as contract
from tests import test_oidc_fill_interop as fill_base

from app.core.config import settings
from app.db.mongodb import get_database
from app.main import app
from app.services.user_service import UserService


# ---------------------------------------------------------------------------
# 内存假件：覆盖闭环用到的集合读写形状（含事务快照回滚）
# ---------------------------------------------------------------------------


def _matches(doc, query):
    return contract._doc_matches(doc, query)


def _apply_update(doc, update):
    for key, value in (update.get("$set") or {}).items():
        target = doc
        parts = key.split(".")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = deepcopy(value)
    for key, value in (update.get("$inc") or {}).items():
        doc[key] = doc.get(key, 0) + value
    for key, value in (update.get("$addToSet") or {}).items():
        items = doc.setdefault(key, [])
        if value not in items:
            items.append(value)
    for key, value in (update.get("$push") or {}).items():
        doc.setdefault(key, []).append(deepcopy(value))


class ClosedLoopCursor:
    """模拟 motor find 游标：sort/skip/limit/to_list 与异步迭代。"""

    def __init__(self, docs):
        self._docs = list(docs)
        self._skip = 0
        self._limit = None

    def sort(self, spec, direction=1):
        if isinstance(spec, list):
            for field, order in reversed(spec):
                self._docs.sort(key=lambda d: d.get(field) or "", reverse=order < 0)
        else:
            self._docs.sort(key=lambda d: d.get(spec) or "", reverse=direction < 0)
        return self

    def skip(self, n):
        self._skip = n
        return self

    def limit(self, n):
        self._limit = n
        return self

    async def to_list(self, length=None):
        end = None if self._limit is None else self._skip + self._limit
        rows = self._docs[self._skip:end]
        return list(rows if length is None else rows[:length])

    def __aiter__(self):
        end = None if self._limit is None else self._skip + self._limit
        self._iter = iter(self._docs[self._skip:end])
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class ClosedLoopCollection:
    """内存集合：insert/find/find_one/update_one/find_one_and_update/count。"""

    def __init__(self):
        self.docs = {}

    async def insert_one(self, doc, *args, **kwargs):
        doc = deepcopy(dict(doc))
        _id = doc.get("_id") or ObjectId()
        doc["_id"] = _id
        if _id in self.docs:
            from pymongo.errors import DuplicateKeyError
            raise DuplicateKeyError("duplicate key")
        self.docs[_id] = doc
        return SimpleNamespace(inserted_id=_id)

    async def find_one(self, query, *args, **kwargs):
        for doc in self.docs.values():
            if _matches(doc, query or {}):
                return deepcopy(doc)
        return None

    def find(self, query=None, projection=None, **kwargs):
        return ClosedLoopCursor(
            [deepcopy(d) for d in self.docs.values() if _matches(d, query or {})])

    async def update_one(self, query, update, **kwargs):
        for doc in self.docs.values():
            if _matches(doc, query or {}):
                _apply_update(doc, update)
                return SimpleNamespace(modified_count=1, matched_count=1)
        return SimpleNamespace(modified_count=0, matched_count=0)

    async def find_one_and_update(self, query, update, **kwargs):
        for doc in self.docs.values():
            if _matches(doc, query or {}):
                _apply_update(doc, update)
                return deepcopy(doc)
        return None

    async def count_documents(self, query, **kwargs):
        return sum(1 for doc in self.docs.values() if _matches(doc, query or {}))

    async def delete_many(self, query, **kwargs):
        removed = [key for key, doc in self.docs.items() if _matches(doc, query or {})]
        for key in removed:
            del self.docs[key]
        return SimpleNamespace(deleted_count=len(removed))

    def aggregate(self, pipeline, **kwargs):
        return ClosedLoopCursor([])

    async def create_index(self, *args, **kwargs):
        return "synthetic-index"


class ClosedLoopDatabase:
    """dict 载体内存库：patient_domain_state 为空 → 患者域自动 legacy。"""

    def __init__(self):
        self._collections = {}
        self.command = AsyncMock(return_value={
            "setName": "closed_loop_rs", "logicalSessionTimeoutMinutes": 30})

    @property
    def client(self):
        # FakeTransactionClient 持有的是活动 dict 引用：事务期间新建的集合
        # 也会进入快照/回滚范围。
        return FakeTransactionClient(self._collections)

    def __getitem__(self, name):
        return self._collections.setdefault(name, ClosedLoopCollection())

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._collections.setdefault(name, ClosedLoopCollection())

    async def list_collection_names(self):
        return list(self._collections)


class ClosedLoopRemote(contract.FakeRemote):
    """在 forms contract 假远端上补充 launch 端点（康复端启动半程）。"""

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == f"/integration/v1/fill-sessions/{contract.SESSION_UUID}/launch":
            return httpx.Response(200, json={
                "session_uuid": contract.SESSION_UUID,
                "action": f"https://form.example/integration/embed/{contract.SESSION_UUID}",
                "token": "b" * 24, "mode": "launch",
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5))
                    .isoformat().replace("+00:00", "Z")})
        return super().handler(request)


# ---------------------------------------------------------------------------
# 类 1：纯 ASGI/内存闭环（默认套件）
# ---------------------------------------------------------------------------


class SinglePatientClosedLoopLocalTests(unittest.IsolatedAsyncioTestCase):
    """无 Mongo/浏览器依赖的单患者闭环主链 + 撤权拒绝语义。"""

    def setUp(self):
        self.fixtures = ExitStack()
        self.addCleanup(self.fixtures.close)
        self.fixtures.enter_context(patch.dict(
            os.environ, {"FORM_PLATFORM_FILL_ENABLED": "true"}))

        async def passthrough_csrf(middleware, request, call_next):
            return await call_next(request)

        for target, kwargs in (
            ("app.integrations.identity.access.IdentityCsrfMiddleware.dispatch",
             {"new": passthrough_csrf}),
            ("app.integrations.identity.access.unified_authentication",
             {"return_value": True}),
            ("app.integrations.identity.service.OidcClient.fill_delegation",
             {"new": AsyncMock(side_effect=lambda sid, actor: contract.synthetic_delegation(actor))}),
            ("app.integrations.identity.service.FillDelegation.revalidate", {"new": AsyncMock()}),
            ("app.integrations.identity.service.FillDelegation.lock", {"new": AsyncMock()}),
        ):
            self.fixtures.enter_context(patch(target, **kwargs))

        self.operator = contract.make_operator()
        # 1) 建档：legacy 模式患者=users 文档，直接落库并授权责任医护
        self.patient_doc = contract.make_patient_doc()
        self.patient_doc["is_active"] = True
        self.database = ClosedLoopDatabase()
        self.database.users.docs[ObjectId(contract.PATIENT_ID)] = deepcopy(self.patient_doc)
        self.remote = ClosedLoopRemote()
        self.source = contract.make_remote_client(self.remote)

        async def fake_actor():
            return self.operator

        async def fake_database():
            yield self.database

        self.get_user_mock = AsyncMock(return_value=self.operator)
        lookup = patch.object(UserService, "get_user_by_id", new=self.get_user_mock)
        lookup.start()
        self.addCleanup(lookup.stop)
        # 随访路由用 get_current_user，集成路由用 get_current_active_user：
        # 两个依赖键都按同一合成操作者覆盖（沿两条既有测试的做法）。
        from app.core.auth import get_current_active_user, get_current_user
        app.dependency_overrides[get_current_active_user] = fake_actor
        app.dependency_overrides[get_current_user] = fake_actor
        app.dependency_overrides[get_database] = fake_database
        from app.integrations.forms.router import get_form_platform_client
        app.dependency_overrides[get_form_platform_client] = lambda: self.source
        app.middleware_stack = None
        self.client = httpx.AsyncClient(app=app, base_url="http://closed-loop-local")

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        app.middleware_stack = None

    async def test_single_patient_closed_loop_local(self):
        db = self.database
        admin_actor = SimpleNamespace(id=str(ObjectId()), role="admin")
        followup_payload = {
            "patient_id": contract.PATIENT_ID, "provider_id": self.operator.id,
            "follow_up_type": "phone",
            "scheduled_date": (datetime.utcnow() + timedelta(days=2)).isoformat(),
            "description": "闭环演练随访节点"}

        # 步骤 1-2：legacy 建档即 users 文档 + 医护授权（practitioners 归属）
        patient = await db.users.find_one(
            {"_id": ObjectId(contract.PATIENT_ID), "role": "patient"})
        self.assertTrue(patient["is_active"])
        self.assertIn(self.operator.id, {str(x) for x in patient["practitioners"]})

        # 步骤 3：人工身份关联（verified patient link）+ 问卷表单绑定审核。
        # 走真实 service（bind_reviewed_patient/bind_form），远端为 MockTransport。
        bind_actor = SimpleNamespace(id=str(ObjectId()), role="admin")
        link = await bind_reviewed_patient(db, self.source, bind_actor,
            link_request())
        version = await form_version(self.source, 1, 4)
        binding = await bind_form(db, self.source, bind_actor, binding_request(version))
        self.assertEqual(link["status"], "verified")
        self.assertEqual(binding["status"], "active")
        link_id = (await db.external_patient_links.find_one(
            {"local_patient_id": contract.PATIENT_ID}))["_id"]

        # 步骤 4：随访节点创建（医护 → 患者授权校验经 ensure_followup_patient_access）
        node = await self.client.post("/api/health-records/followups",
                                      json=followup_payload, headers=self.auth())
        self.assertEqual(node.status_code, 200, node.text)
        self.assertEqual(node.json()["status"], "scheduled")
        self.assertEqual(node.json()["mutation_version"], 0)
        node_id = node.json()["id"]

        # 步骤 5：关联填报任务创建（已审核上下文：link verified + binding active）
        payload = contract_fill_payload(binding["id"], followup_visit_id=node_id)
        created = await self.client.post("/api/integrations/forms/fill-tasks",
                                         json=payload, headers=self.auth())
        self.assertEqual(created.status_code, 200, created.text)
        body = created.json()
        self.assertEqual(body["status"], "session_created")
        self.assertEqual(body["session"]["sessionUuid"], contract.SESSION_UUID)
        self.assertNotIn("embedToken", body)
        self.assertNotIn("token", body)
        task_id = body["id"]
        stored = await db.integration_fill_tasks.find_one({"_id": ObjectId(task_id)})
        self.assertEqual(stored["operator"]["remote_user_id"], 7)
        self.assertEqual(stored["followup_visit_id"], node_id)

        # 步骤 6（康复端启动半程）：launch 短期凭证校验；浏览器消费/填报由
        # 带门控的全链路类覆盖（MockTransport 无法模拟源端浏览器表单流）。
        launched = await self.client.post(
            f"/api/integrations/forms/fill-tasks/{task_id}/launch", headers=self.auth())
        self.assertEqual(launched.status_code, 200, launched.text)
        opening = launched.json()
        self.assertEqual(opening["mode"], "launch")
        self.assertEqual(opening["sessionUuid"], contract.SESSION_UUID)
        self.assertIn(f"/integration/embed/{contract.SESSION_UUID}", opening["action"])

        # 步骤 7（源端填报模拟）：MockTransport 无法承载浏览器填报，故按已提交
        # 语义翻转远端会话/答卷状态（等价于受试者已提交），再走康复端核实。
        self.remote.session_body["status"] = "submitted"
        self.remote.session_body["response_id"] = contract.RESPONSE_ID
        confirmed = await self.client.post(
            f"/api/integrations/forms/fill-tasks/{task_id}/confirm", headers=self.auth())
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["status"], "confirmed")
        node_now = await self.client.get(
            f"/api/health-records/followups/{node_id}", headers=self.auth())
        self.assertEqual(node_now.status_code, 200, node_now.text)
        self.assertEqual(node_now.json()["status"], "in_review")
        self.assertEqual(node_now.json()["effective_response"]["task_id"], task_id)
        # 创建联动（$addToSet fill_task_ids）已 +1，confirm 回写再 +1
        self.assertEqual(node_now.json()["mutation_version"], 2)

        # 步骤 8：随访审阅批准 → completed（唯一置 completed 路径）
        reviewed = await self.client.post(
            f"/api/health-records/followups/{node_id}/review",
            json={"expected_version": node_now.json()["mutation_version"],
                  "decision": "approved", "comment": "闭环演练审阅通过"},
            headers=self.auth())
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        self.assertEqual(reviewed.json()["status"], "completed")

        # 步骤 9（撤权演练 A）：表单绑定撤销 → 既有任务复核拒绝、新任务拒绝。
        node2 = await self.client.post("/api/health-records/followups", json=dict(
            followup_payload, description="撤权演练第二节点"), headers=self.auth())
        self.assertEqual(node2.status_code, 200, node2.text)
        task2 = await self.client.post("/api/integrations/forms/fill-tasks", json=dict(
            payload, followup_visit_id=node2.json()["id"]), headers=self.auth())
        self.assertEqual(task2.status_code, 200, task2.text)
        revoked_binding = await revoke_form_binding(
            binding["id"], binding_revoke_request(), admin_actor, db)
        self.assertEqual(revoked_binding["status"], "revoked")
        rejected = await self.client.post(
            f"/api/integrations/forms/fill-tasks/{task2.json()['id']}/confirm",
            headers=self.auth())
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertEqual(rejected.json()["detail"]["error"], "TASK_REVIEW_REVOKED")
        blocked = await self.client.post("/api/integrations/forms/fill-tasks",
                                         json=dict(payload, followup_visit_id=node2.json()["id"]),
                                         headers=self.auth())
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertEqual(blocked.json()["detail"]["error"], "REVIEWED_CONTEXT_REQUIRED")

        # 步骤 10（撤权演练 B）：患者关联撤销 → 新任务创建拒绝（跨端恢复类
        # 边界见缺口文档条目 3，不在此发明恢复语义）。
        revoked_link = await revoke_patient_link(
            str(link_id), link_revoke_request(), admin_actor, db)
        self.assertEqual(revoked_link["status"], "revoked")
        node3 = await self.client.post("/api/health-records/followups", json=dict(
            followup_payload, description="撤权演练第三节点"), headers=self.auth())
        self.assertEqual(node3.status_code, 200, node3.text)
        blocked_again = await self.client.post("/api/integrations/forms/fill-tasks", json=dict(
            payload, followup_visit_id=node3.json()["id"]), headers=self.auth())
        self.assertEqual(blocked_again.status_code, 409, blocked_again.text)
        self.assertEqual(blocked_again.json()["detail"]["error"], "REVIEWED_CONTEXT_REQUIRED")

    def auth(self):
        token = jwt_encode()
        return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 类 2：隔离双应用全链路（REHAB_TEST_CLOSED_LOOP=1 显式开启）
# ---------------------------------------------------------------------------


CLOSED_LOOP_SOURCE_SCRIPT = fill_base.SCRIPT.replace(
    "db.session.add(PatientArchive(patient_id=ids['patient_a'],"
    "organization_id=ids['org'],status='active'));db.session.commit();ids['user']=uid",
    "db.session.add(PatientArchive(patient_id=ids['patient_a'],"
    "organization_id=ids['org'],status='active'));db.session.commit();ids['user']=uid\n"
    "    from app.models import User as SourceUser\n"
    "    subject_account=SourceUser(username='loop_subject',"
    "email='loop-subject@example.com',role=SourceUser.ROLE_USER,is_active=True)\n"
    "    subject_account.set_password('Synthetic-Loop-Subject-Password-42');"
    "db.session.add(subject_account);db.session.commit();ids['subject_account']=subject_account.id")

PATIENT_SOURCE_PASSWORD = "Synthetic-Loop-Subject-Password-42"


class SinglePatientClosedLoopSourceTests(fill_base.OidcFillInterop):
    """真实源端 + 副本集 Mongo 的单患者全链路（浏览器草稿/提交/恢复）。"""

    __unittest_skip__ = os.environ.get("REHAB_TEST_CLOSED_LOOP") != "1"
    test_real_reviewed_fill_identity = None

    @classmethod
    def setUpClass(cls):
        with patch.object(fill_base, "SCRIPT", CLOSED_LOOP_SOURCE_SCRIPT):
            super().setUpClass()

    async def login_as(self, http, browser, username, password):
        """参数化的 OIDC 登录+consent（基线版本绑定在医生凭据上）。"""
        start = await http.get("/api/auth/oidc/start")
        self.assertEqual(start.status_code, 303, start.text)
        target = start.headers["location"]
        consent = await browser.get(target)
        if consent.status_code == 302:
            login_url = self.origin + consent.headers["location"]
            login = await browser.get(login_url)
            csrf = fill_base.base.Inputs(login.text).values["csrf_token"]
            self.assertEqual(
                (await browser.get(self.origin + "/auth/captcha")).status_code, 200)
            signed = await browser.post(login_url, data={
                "username": username, "password": password, "captcha": "A123",
                "csrf_token": csrf}, headers={"Referer": login_url})
            self.assertEqual(signed.status_code, 302, signed.text)
            consent = await browser.get(target)
        self.assertEqual(consent.status_code, 200, consent.text)
        allowed = await browser.post(target, data={
            "decision": "allow",
            "csrf_token": fill_base.base.Inputs(consent.text).values["csrf_token"]},
            headers={"Referer": target})
        self.assertEqual(allowed.status_code, 302, allowed.text)
        result = await http.get("/api/auth/oidc/callback?" +
                                urlsplit(allowed.headers["location"]).query)
        self.assertEqual(result.status_code, 303, result.text)
        return await http.get("/api/auth/session")

    async def test_single_patient_closed_loop_with_source_fill(self):
        with self.application() as app, \
                patch.dict(os.environ, {"FORM_PLATFORM_FILL_ENABLED": "true"}), \
                patch("app.integrations.identity.config.oidc_settings", self.config), \
                patch("app.integrations.identity.service.OidcClient", return_value=self.service):
            self.http = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="https://rp.synthetic")
            patient_http = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="https://rp.synthetic")
            patient_browser = httpx.AsyncClient(verify=self.context, follow_redirects=False)
            try:
                await self._run_closed_loop(patient_http, patient_browser)
            finally:
                await patient_http.aclose()
                await patient_browser.aclose()

    async def _run_closed_loop(self, patient_http, patient_browser):
        db = self.db
        headers = {"Origin": "https://rp.synthetic"}

        # 步骤 1：康复端建档（legacy users 文档）+ 医生 OIDC 登录与人工绑定
        pending = await self.login_and_consent()
        self.assertEqual(pending.status_code, 200, pending.text)
        self.assertEqual(pending.json()["identity_state"], "pending_binding")
        actor_id = ObjectId()
        patient_id = ObjectId()
        now = datetime.utcnow()
        await db.users.insert_one({"_id": actor_id, "name": "闭环责任医生",
            "email": "loop-doctor@example.com", "role": "doctor", "is_active": True,
            "created_at": now, "updated_at": now})
        await db.users.insert_one({"_id": patient_id, "role": "patient",
            "is_active": True, "name": "闭环患者", "email": "loop-patient@example.com",
            "practitioners": [str(actor_id)], "created_at": now, "updated_at": now})
        await manage_binding(db, issuer=self.origin, subject=pending.json()["subject"],
            actor_id=str(actor_id), reviewer="closed-loop-reviewer",
            evidence_reference="review/doctor-account", approved_role="doctor", apply=True)
        identity = await self.login_and_consent()
        self.assertEqual(identity.status_code, 200, identity.text)
        self.assertEqual(identity.json()["actor_id"], str(actor_id))
        headers["X-CSRF-Token"] = self.http.cookies.get("__Host-rehab_csrf")
        source = fill_source_client(self)
        # 与基线 fill interop 相同：隔离源客户端经依赖覆盖注入（本地无部署配置）
        from app.integrations.forms.router import get_form_platform_client
        app.dependency_overrides[get_form_platform_client] = lambda: source

        # 步骤 2：人工身份关联（verified）+ 表单绑定审核
        bind_actor = SimpleNamespace(id=str(actor_id), role="admin")
        await bind_reviewed_patient(db, source, bind_actor, link_request(
            local_patient_id=str(patient_id), project_id=self.ids["project"],
            center_id=self.ids["center"], subject_id=self.ids["subject"]))
        version = await form_version(source, self.ids["project"], self.ids["questionnaire"])
        binding = await bind_form(db, source, bind_actor, binding_request(
            version, project_id=self.ids["project"], form_id=self.ids["questionnaire"]))
        link_id = (await db.external_patient_links.find_one(
            {"local_patient_id": str(patient_id)}))["_id"]

        # 步骤 3：随访节点创建
        followup_payload = {"patient_id": str(patient_id), "provider_id": str(actor_id),
            "follow_up_type": "phone",
            "scheduled_date": (datetime.utcnow() + timedelta(days=2)).isoformat(),
            "description": "闭环演练随访节点"}
        node = await self.http.post("/api/health-records/followups",
                                    json=followup_payload, headers=headers)
        self.assertEqual(node.status_code, 200, node.text)
        self.assertEqual(node.json()["status"], "scheduled")
        node_id = node.json()["id"]

        # 步骤 4：关联填报任务创建（已审核上下文 + 节点联动）
        payload = {"patient_id": str(patient_id),
            "remote_project_id": self.ids["project"], "remote_center_id": self.ids["center"],
            "remote_subject_id": self.ids["subject"],
            "remote_questionnaire_id": self.ids["questionnaire"],
            "form_binding_id": binding["id"], "form_purpose": "followup",
            "allowed_origin": "https://rp.synthetic", "visit_code": "V1",
            "followup_visit_id": node_id}
        created = await self.http.post("/api/integrations/forms/fill-tasks",
                                       json=payload, headers=headers)
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()["status"], "session_created")
        self.assertNotIn("embedToken", created.json())
        task_id = created.json()["id"]
        stored = await db.integration_fill_tasks.find_one({"_id": ObjectId(task_id)})
        self.assertEqual(stored["operator"]["remote_user_id"], self.ids["user"])
        self.assertEqual(stored["followup_visit_id"], node_id)

        # 步骤 5：源端填报——launch 单次凭证消费 → 草稿 → 同一草稿恢复 → 正式提交
        launched = await self.http.post(
            f"/api/integrations/forms/fill-tasks/{task_id}/launch", headers=headers)
        self.assertEqual(launched.status_code, 200, launched.text)
        opening = launched.json()
        self.assertEqual(opening["mode"], "launch")
        consumed = await self.browser.post(opening["action"],
            data={"token": opening["token"]}, headers={"Origin": "https://rp.synthetic"})
        self.assertEqual(consumed.status_code, 303, consumed.text)
        fill_url = urljoin(self.origin, consumed.headers["Location"])
        page = await self.browser.get(fill_url)
        self.assertEqual(page.status_code, 200, page.text)
        inputs = fill_base.base.Inputs(page.text).values
        submit_url = fill_url.rsplit("/fill", 1)[0] + "/submit"
        question_field = f"question_{self.ids['question']}"
        # 访视标识必须在草稿与正式提交中与会话一致，否则源端委托绑定按
        # 答卷↔任务访视不一致拒绝（409 答卷与当前填报任务不一致）。
        draft = await self.browser.post(submit_url, data={
            "submit_type": "draft", "visit_code": "V1",
            "questionnaire_version_presentation": inputs["questionnaire_version_presentation"],
            "csrf_token": inputs["csrf_token"], question_field: "闭环演练草稿"},
            headers={"Origin": self.origin, "Referer": fill_url})
        self.assertEqual(draft.status_code, 302, draft.text)
        resumed = await self.http.post(
            f"/api/integrations/forms/fill-tasks/{task_id}/launch", headers=headers)
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["mode"], "resume")
        restored = await self.browser.get(resumed.json()["url"])
        self.assertEqual(restored.status_code, 303, restored.text)
        draft_id = parse_qs(urlsplit(restored.headers["Location"]).query)["response_id"][0]
        recovered = await self.browser.get(urljoin(self.origin, restored.headers["Location"]))
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertIn("闭环演练草稿", recovered.text)
        resumed_inputs = fill_base.base.Inputs(recovered.text).values
        final_data = {
            "submit_type": "submit", "visit_code": "V1",
            "questionnaire_version_presentation":
                resumed_inputs["questionnaire_version_presentation"],
            "csrf_token": resumed_inputs["csrf_token"],
            question_field: "闭环演练正式提交"}
        # 恢复页的隐藏 response_id 必须随正式提交回传，否则会新建答卷并与
        # 会话已绑定的草稿冲突（409 答卷与当前填报任务不一致）。
        if resumed_inputs.get("response_id"):
            final_data["response_id"] = resumed_inputs["response_id"]
        submitted = await self.browser.post(submit_url, data=final_data,
            headers={"Origin": self.origin, "Referer": fill_url})
        self.assertEqual(submitted.status_code, 302, submitted.text)
        self.assertIn("submission-success", submitted.headers["Location"])

        # 步骤 6：康复端审阅——confirm 向远端轮询核实 → 节点 in_review → 批准 completed
        confirmed = await self.http.post(
            f"/api/integrations/forms/fill-tasks/{task_id}/confirm", headers=headers)
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["status"], "confirmed")
        node_now = await self.http.get(
            f"/api/health-records/followups/{node_id}", headers=headers)
        self.assertEqual(node_now.status_code, 200, node_now.text)
        self.assertEqual(node_now.json()["status"], "in_review")
        self.assertEqual(node_now.json()["effective_response"]["task_id"], task_id)
        reviewed = await self.http.post(
            f"/api/health-records/followups/{node_id}/review",
            json={"expected_version": node_now.json()["mutation_version"],
                  "decision": "approved"}, headers=headers)
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        self.assertEqual(reviewed.json()["status"], "completed")

        # 步骤 7：康复方案草稿 → 发布版本
        plan_id = ObjectId()
        await db.rehab_plans.insert_one({"_id": plan_id, "patient_id": str(patient_id),
            "status": "active", "content_revision": 0, "notes": "internal note",
            "metadata": {"private": "do not leak"}, "exercises": []})
        saved = await self.http.put(
            f"/api/rehabilitation/publications/plans/{plan_id}/draft", json={
                "request_id": uuid4().hex,
                "content": {"name": "闭环康复方案", "description": "审阅后的方案内容",
                            "goal": "阶段目标", "start_date": "2026-11-20T08:00:00+08:00"},
                "items": [{"intervention_type": "exercise", "name": "闭环训练",
                           "schedule": {"sets": 2}},
                          {"intervention_type": "diet", "name": "闭环饮食",
                           "diet_fields": {"food_restrictions": ["低盐"]}}]},
            headers=headers)
        self.assertEqual(saved.status_code, 200, saved.text)
        published = await self.http.post(
            f"/api/rehabilitation/publications/plans/{plan_id}/publish", json={
                "request_id": uuid4().hex, "draft_id": saved.json()["draft"]["id"],
                "expected_draft_revision": saved.json()["draft"]["revision"],
                "expected_publication_id": None, "confirmed": True,
                "confirmation_note": "闭环演练发布确认"}, headers=headers)
        self.assertEqual(published.status_code, 200, published.text)
        version_id = published.json()["version_id"]
        item_id = published.json()["items"][0]["item_id"]

        # 步骤 8：患者反馈——患者源账号独立 OIDC 会话 + 本人提交执行反馈
        pending_patient = await self.login_as(
            patient_http, patient_browser, "loop_subject", PATIENT_SOURCE_PASSWORD)
        self.assertEqual(pending_patient.status_code, 200, pending_patient.text)
        await manage_binding(db, issuer=self.origin,
            subject=pending_patient.json()["subject"], actor_id=str(patient_id),
            reviewer="closed-loop-reviewer", evidence_reference="review/patient-account",
            approved_role="patient", apply=True)
        patient_identity = await self.login_as(
            patient_http, patient_browser, "loop_subject", PATIENT_SOURCE_PASSWORD)
        self.assertEqual(patient_identity.status_code, 200, patient_identity.text)
        self.assertEqual(patient_identity.json()["actor_id"], str(patient_id))
        patient_headers = {"Origin": "https://rp.synthetic",
                           "X-CSRF-Token": patient_http.cookies.get("__Host-rehab_csrf")}
        detail = await patient_http.get(
            f"/api/rehabilitation/publications/my-plans/{plan_id}", headers=patient_headers)
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["version_id"], version_id)
        feedback = await patient_http.post(
            f"/api/rehabilitation/plans/{plan_id}/patient-feedback", json={
                "event_id": str(uuid4()), "version_id": version_id,
                "prescription_item_id": item_id, "execution_status": "completed",
                "feelings": "闭环演练的患者执行反馈",
                "performed_at": datetime.now(timezone.utc).isoformat()},
            headers=patient_headers)
        self.assertEqual(feedback.status_code, 201, feedback.text)
        listed = await self.http.get(
            f"/api/rehabilitation/plans/{plan_id}/patient-feedback", headers=headers)
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()["total"], 1)

        # 步骤 9：撤权演练——本地患者关联撤销 → 既有任务复核拒绝 + 新任务拒绝
        node2 = await self.http.post("/api/health-records/followups", json=dict(
            followup_payload, description="撤权演练第二节点"), headers=headers)
        self.assertEqual(node2.status_code, 200, node2.text)
        task2 = await self.http.post("/api/integrations/forms/fill-tasks", json=dict(
            payload, followup_visit_id=node2.json()["id"]), headers=headers)
        self.assertEqual(task2.status_code, 200, task2.text)
        revoked = await revoke_patient_link(str(link_id),
            link_revoke_request(), SimpleNamespace(id=str(actor_id), role="admin"), db)
        self.assertEqual(revoked["status"], "revoked")
        rejected = await self.http.post(
            f"/api/integrations/forms/fill-tasks/{task2.json()['id']}/confirm",
            headers=headers)
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertEqual(rejected.json()["detail"]["error"], "TASK_REVIEW_REVOKED")
        blocked = await self.http.post("/api/integrations/forms/fill-tasks",
            json=dict(payload, followup_visit_id=node2.json()["id"]), headers=headers)
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertEqual(blocked.json()["detail"]["error"], "REVIEWED_CONTEXT_REQUIRED")

        # 步骤 10：源账号停用 → 康复端会话失效（fail-closed）
        (self.store / "disable-account").touch()
        me = await self.http.get("/api/users/me")
        self.assertEqual(me.status_code, 401, me.text)


# ---------------------------------------------------------------------------
# 共享小工具（延迟导入保持模块导入轻量）
# ---------------------------------------------------------------------------


def jwt_encode():
    from jose import jwt as jose_jwt
    return jose_jwt.encode(
        {"sub": contract.OPERATOR_ID, "token_type": "access",
         "exp": datetime.utcnow() + timedelta(minutes=5)},
        settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def link_request(**overrides):
    from app.integrations.forms.patient_links import PatientLinkRequest
    body = {"local_patient_id": contract.PATIENT_ID, "project_id": 1,
            "center_id": 2, "subject_id": 3,
            "evidence_reference": "review/closed-loop-patient", "identity_verified": True}
    body.update(overrides)
    return PatientLinkRequest.model_validate(body)


def binding_request(version, **overrides):
    from app.integrations.forms.form_bindings import FormBindingRequest
    body = {"project_id": 1, "form_id": 4, "version": version["version"]["version"],
            "purpose": "followup", "confirmed": True,
            "evidence_reference": "review/closed-loop-form"}
    body.update(overrides)
    return FormBindingRequest.model_validate(body)


def binding_revoke_request():
    from app.integrations.forms.form_bindings import RevokeFormBindingRequest
    return RevokeFormBindingRequest(reason="闭环演练：撤销表单绑定")


def link_revoke_request():
    from app.integrations.forms.patient_links import RevokePatientLinkRequest
    return RevokePatientLinkRequest(reason="闭环演练：撤销患者关联")


def contract_fill_payload(binding_id, **overrides):
    body = {"patient_id": contract.PATIENT_ID, "form_binding_id": binding_id,
            "form_purpose": "followup", "remote_project_id": 1, "remote_center_id": 2,
            "remote_subject_id": 3, "remote_questionnaire_id": 4,
            "allowed_origin": contract.ORIGIN, "visit_code": "V1",
            "ma_task_ref": "ma-task-0001"}
    body.update(overrides)
    return body


def bind_reviewed_patient(db, client, actor, payload):
    from app.integrations.forms.patient_links import bind_reviewed_patient as bind
    return bind(db, client, actor, payload)


def bind_form(db, client, actor, payload):
    from app.integrations.forms.form_bindings import bind_form as bind
    return bind(db, client, actor, payload)


def form_version(client, project_id, form_id):
    from app.integrations.forms.catalog_service import form_version as fetch
    return fetch(client, project_id, form_id)


def manage_binding(db, **kwargs):
    from app.integrations.identity.bindings import manage_binding as manage
    return manage(db, **kwargs)


def revoke_patient_link(link_id, payload, actor, db):
    from app.integrations.forms.patient_links import revoke_patient_link as revoke
    return revoke(link_id, payload, actor, db)


def revoke_form_binding(binding_id, payload, actor, db):
    from app.integrations.forms.form_bindings import revoke_form_binding as revoke
    return revoke(binding_id, payload, actor, db)


def fill_source_client(test):
    from app.integrations.forms.client import FormPlatformClient
    return FormPlatformClient(test.origin, "test-catalog-client",
                              "catalog-client-secret", 5, verify_tls=test.context)
