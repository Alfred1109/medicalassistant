"""FU01 S2 路由收敛回归测试（唯一服务入口与路由收敛）。

覆盖设计稿 docs/wp3-fu01-domain-design-draft-2026-11-07.md §五 S2 验收标准：

1. /api/doctors/follow-ups GET 与唯一正典入口 /api/health-records/followups
   同源（同一 FollowupService、同一集合）同形状（FollowUpRecordResponse 契约）；
2. /api/doctors/follow-ups 与 /api/health-managers/follow-ups POST 转调
   FollowupService，返回真实记录 ID（删除 new_follow_up_id 假 ID 存根）；
3. 回归 grep：全代码库无 new_follow_up_id 假 ID；路由层无直连
   followup_records / follow_ups 集合；随访集合唯一服务入口为 FollowupService；
   cancel 拼写归一 canceled（存储模型不再产生 cancelled）。

全部内存打桩 + FastAPI 依赖覆盖，不触碰真实数据库。
"""

import re
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import httpx
from bson import ObjectId
from followup_transaction_fake import FakeTransactionClient

from app.core.auth import get_current_user
from app.db.mongodb import get_database
from app.main import app
from app.models.health_record import FollowUpRecord
from app.schemas.followup import FollowUpRecordResponse
from app.schemas.user import UserResponse
from tests.test_followup_service_contract import _match as _base_match

def _match(doc, query):
    for field, condition in query.items():
        if isinstance(doc.get(field), list) and isinstance(condition, dict) and "$in" in condition:
            if not any(item in condition["$in"] for item in doc[field]):
                return False
        elif not _base_match(doc, {field: condition}):
            return False
    return True

BACKEND_DIR = Path(__file__).resolve().parent.parent

DOCTOR_ID = str(ObjectId())
MANAGER_ID = str(ObjectId())
PATIENT_ID = str(ObjectId())


# ---------------------------------------------------------------------------
# 内存版 Mongo 桩
# ---------------------------------------------------------------------------

class FakeCursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = list(docs)

    def sort(self, *args, **kwargs):
        return self

    def skip(self, n: int):
        self._docs = self._docs[n:]
        return self

    def limit(self, n: int):
        self._docs = self._docs[:n]
        return self

    def __aiter__(self):
        async def iterate():
            for doc in self._docs:
                yield doc
        return iterate()

    async def to_list(self, length: Optional[int] = None):
        return list(self._docs[:length] if length is not None else self._docs)


class FakeCollection:
    def __init__(self):
        self.docs: Dict[Any, Dict[str, Any]] = {}

    async def insert_one(self, doc, *args, **kwargs):
        doc = dict(doc)
        _id = doc.get("_id") or ObjectId()
        doc["_id"] = _id
        self.docs[_id] = doc
        return SimpleNamespace(inserted_id=_id)

    async def find_one(self, query, *args, **kwargs):
        return next((dict(doc) for doc in self.docs.values() if _match(doc, query)), None)

    async def update_one(self, query, update, **kwargs):
        _id = query.get("_id")
        if _id in self.docs:
            self.docs[_id].update(update.get("$set", {}))
            for key, value in update.get("$inc", {}).items():
                self.docs[_id][key] = self.docs[_id].get(key, 0) + value
            return SimpleNamespace(modified_count=1, matched_count=1)
        return SimpleNamespace(modified_count=0, matched_count=0)

    async def count_documents(self, query):
        return len(self.docs)

    def find(self, query, *args):
        return FakeCursor([dict(doc) for doc in self.docs.values() if _match(doc, query)])

    def aggregate(self, pipeline):
        return FakeCursor([])


class FakeDatabase:
    def __init__(self):
        self._collections = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._collections.setdefault(name, FakeCollection())

    @property
    def client(self):
        return FakeTransactionClient(self._collections)

    def __getitem__(self, name):
        return getattr(self, name)


def _make_user(role, user_id):
    now = datetime.utcnow()
    return UserResponse(id=user_id, email="actor@example.com", name="合成操作者",
                        role=role, is_active=True, createdAt=now, updatedAt=now)


def _seed_followup_doc(db, created_by=DOCTOR_ID, patient_id=PATIENT_ID):
    doc = FollowUpRecord(
        patient_id=patient_id, created_by=created_by,
        follow_up_type="phone",
        scheduled_date=datetime.utcnow() + timedelta(days=1),
        notes="术后电话随访").to_mongo()
    doc["provider_id"] = created_by
    db["followup_records"].docs[doc["_id"]] = doc
    return doc


class FollowupRouteConvergenceTests(unittest.IsolatedAsyncioTestCase):
    """doctor / health-manager 随访入口与 canonical 入口同源同形状。"""

    async def asyncSetUp(self):
        self.db = FakeDatabase()
        self.doc = _seed_followup_doc(self.db)
        self.db.users.docs[ObjectId(PATIENT_ID)] = {"_id": ObjectId(PATIENT_ID), "role": "patient", "practitioners": [DOCTOR_ID], "health_managers": [MANAGER_ID]}

        async def fake_current_user():
            return self.user

        async def fake_database():
            return self.db

        app.dependency_overrides[get_current_user] = fake_current_user
        app.dependency_overrides[get_database] = fake_database
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://followup-convergence-test")

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()

    async def test_doctor_followups_same_source_same_shape_as_canonical(self):
        """/api/doctors/follow-ups 与 /api/health-records/followups 同源同形状。"""
        self.user = _make_user("doctor", DOCTOR_ID)

        doctor_resp = await self.client.get("/api/doctors/follow-ups")
        self.assertEqual(doctor_resp.status_code, 200, doctor_resp.text)
        canonical_resp = await self.client.get(
            "/api/health-records/followups", params={"patient_id": PATIENT_ID})
        self.assertEqual(canonical_resp.status_code, 200, canonical_resp.text)

        doctor_body = doctor_resp.json()
        canonical_body = canonical_resp.json()
        self.assertEqual(len(doctor_body), 1)
        self.assertEqual(len(canonical_body), 1)

        # 同形状：响应键集合与 FollowUpRecordResponse 契约字段完全一致，
        # 且同一文档映射出同一记录（同源）
        contract_fields = set(FollowUpRecordResponse.model_fields.keys())
        self.assertEqual(set(doctor_body[0].keys()), contract_fields)
        self.assertEqual(set(canonical_body[0].keys()), contract_fields)
        self.assertEqual(doctor_body[0]["id"], str(self.doc["_id"]))
        self.assertEqual(doctor_body[0]["id"], canonical_body[0]["id"])
        self.assertEqual(doctor_body[0]["status"], canonical_body[0]["status"])
        self.assertEqual(doctor_body[0]["patient_id"], canonical_body[0]["patient_id"])
        self.assertEqual(doctor_body[0]["created_by"], canonical_body[0]["created_by"])
        self.assertEqual(doctor_body[0]["description"], canonical_body[0]["description"])

    async def test_doctor_create_follow_up_returns_real_record(self):
        """POST /api/doctors/follow-ups 转调服务层，返回真实 ID（无 new_follow_up_id）。"""
        self.user = _make_user("doctor", DOCTOR_ID)
        payload = {
            "patient_id": PATIENT_ID,
            "provider_id": DOCTOR_ID,
            "follow_up_type": "phone",
            "scheduled_date": (datetime.utcnow() + timedelta(days=2)).isoformat(),
            "description": "收敛后创建的随访",
        }

        response = await self.client.post("/api/doctors/follow-ups", json=payload)

        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        # 真实记录 ID（24 位十六进制 ObjectId），不再是 new_follow_up_id 假 ID
        self.assertRegex(body["id"], r"^[0-9a-f]{24}$")
        self.assertEqual(body["description"], "收敛后创建的随访")
        # 文档真实落库，created_by 缺省为当前医生
        self.assertEqual(len(self.db["followup_records"].docs), 2)
        created = self.db["followup_records"].docs[ObjectId(body["id"])]
        self.assertEqual(created["created_by"], DOCTOR_ID)
        self.assertEqual(created["provider_id"], DOCTOR_ID)

    async def test_health_manager_followups_delegated_to_service(self):
        """health-manager 随访 GET/POST 转调 FollowupService（同形状、真实 ID）。"""
        self.user = _make_user("health_manager", MANAGER_ID)

        got = await self.client.get("/api/health-managers/follow-ups")
        self.assertEqual(got.status_code, 200, got.text)
        body = got.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(set(body[0].keys()),
                         set(FollowUpRecordResponse.model_fields.keys()))
        self.assertEqual(body[0]["id"], str(self.doc["_id"]))

        payload = {
            "patient_id": PATIENT_ID,
            "provider_id": MANAGER_ID,
            "follow_up_type": "onsite",
            "scheduled_date": (datetime.utcnow() + timedelta(days=3)).isoformat(),
            "description": "管理师创建的随访",
        }
        created = await self.client.post("/api/health-managers/follow-ups", json=payload)
        self.assertEqual(created.status_code, 201, created.text)
        self.assertRegex(created.json()["id"], r"^[0-9a-f]{24}$")
        self.assertEqual(len(self.db["followup_records"].docs), 2)

    async def test_manager_patient_list_uses_manager_assignment_and_revocation(self):
        self.user = _make_user("health_manager", MANAGER_ID)
        patient = self.db.users.docs[ObjectId(PATIENT_ID)]
        patient["health_managers"] = [ObjectId(MANAGER_ID)]
        patient["name"] = "管理患者"
        other_id = ObjectId()
        self.db.users.docs[other_id] = {
            "_id": other_id, "role": "patient", "name": "错误角色关系",
            "practitioners": [MANAGER_ID], "health_managers": [],
        }
        got = await self.client.get("/api/health-managers/patients")
        self.assertEqual(got.status_code, 200, got.text)
        self.assertEqual([item["id"] for item in got.json()], [PATIENT_ID])
        self.assertEqual(got.json()[0]["name"], "管理患者")
        detail = await self.client.get(f"/api/health-records/followups/{self.doc['_id']}")
        self.assertEqual(detail.status_code, 200, detail.text)
        patient["health_managers"] = []
        revoked = await self.client.get("/api/health-managers/patients")
        self.assertEqual(revoked.json(), [])
        detail = await self.client.get(f"/api/health-records/followups/{self.doc['_id']}")
        self.assertEqual(detail.status_code, 403, detail.text)

    async def test_manager_patient_list_does_not_grant_other_roles(self):
        for role in ("doctor", "patient", "admin"):
            with self.subTest(role=role):
                self.user = _make_user(role, MANAGER_ID)
                response = await self.client.get("/api/health-managers/patients")
                self.assertEqual(response.status_code, 403, response.text)

    async def test_assigned_manager_can_submit_and_review_own_followup(self):
        self.user = _make_user("health_manager", MANAGER_ID)
        self.doc["provider_id"] = MANAGER_ID
        self.doc["created_by"] = MANAGER_ID
        node_id = str(self.doc["_id"])
        submitted = await self.client.post(
            f"/api/health-records/followups/{node_id}/complete",
            json={"expected_version": 0, "notes": "电话核实"})
        self.assertEqual(submitted.status_code, 200, submitted.text)
        reviewed = await self.client.post(
            f"/api/health-records/followups/{node_id}/review",
            json={"expected_version": submitted.json()["mutation_version"], "decision": "approved"})
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        self.assertEqual(reviewed.json()["status"], "completed")

    async def test_doctor_followups_rejects_non_doctor(self):
        self.user = _make_user("patient", PATIENT_ID)
        response = await self.client.get("/api/doctors/follow-ups")
        self.assertEqual(response.status_code, 403, response.text)


    async def test_patient_cannot_write_any_followup(self):
        self.user = _make_user("patient", PATIENT_ID)
        paths = [
            ("POST", "/api/health-records/followups", {"patient_id": PATIENT_ID, "provider_id": DOCTOR_ID, "follow_up_type": "phone", "scheduled_date": datetime.utcnow().isoformat(), "description": "x"}),
            ("PUT", f"/api/health-records/followups/{self.doc['_id']}", {"description": "changed"}),
            ("POST", f"/api/health-records/followups/{self.doc['_id']}/complete", {"expected_version": 0}),
            ("POST", f"/api/health-records/followups/{self.doc['_id']}/cancel", {"cancel_reason": "x"}),
            ("POST", f"/api/health-records/followups/{self.doc['_id']}/reschedule", {"new_date": datetime.utcnow().isoformat(), "reason": "x"}),
            ("POST", f"/api/health-records/followups/{self.doc['_id']}/review", {"expected_version": 0, "decision": "approved"}),
            ("POST", f"/api/health-records/followups/{self.doc['_id']}/re-evaluate", {"scheduled_date": datetime.utcnow().isoformat()}),
        ]
        original = dict(self.doc)
        for method, path, body in paths:
            with self.subTest(path=path):
                result = await self.client.request(method, path, json=body)
                self.assertEqual(result.status_code, 403, result.text)
        self.assertEqual(self.db["followup_records"].docs[self.doc['_id']], original)

    async def test_unassigned_doctor_cannot_read_or_write_node(self):
        self.user = _make_user("doctor", str(ObjectId()))
        node_id = str(self.doc['_id'])
        calls = [
            ("GET", f"/api/health-records/followups/{node_id}", None),
            ("GET", f"/api/health-records/followups?patient_id={PATIENT_ID}", None),
            ("GET", f"/api/health-records/followups/upcoming?patient_id={PATIENT_ID}", None),
            ("PUT", f"/api/health-records/followups/{node_id}", {"description": "changed"}),
            ("POST", f"/api/health-records/followups/{node_id}/complete", {"expected_version": 0}),
            ("POST", f"/api/health-records/followups/{node_id}/cancel", {"cancel_reason": "x"}),
            ("POST", f"/api/health-records/followups/{node_id}/reschedule", {"new_date": datetime.utcnow().isoformat(), "reason": "x"}),
            ("POST", f"/api/health-records/followups/{node_id}/review", {"expected_version": 0, "decision": "approved"}),
            ("POST", f"/api/health-records/followups/{node_id}/re-evaluate", {"scheduled_date": datetime.utcnow().isoformat()}),
        ]
        for method, path, body in calls:
            with self.subTest(path=path):
                result = await self.client.request(method, path, json=body)
                self.assertEqual(result.status_code, 403, result.text)

    async def test_unassigned_creators_rejected_across_aliases(self):
        payload = {"patient_id": PATIENT_ID, "provider_id": DOCTOR_ID, "follow_up_type": "phone", "scheduled_date": datetime.utcnow().isoformat(), "description": "x"}
        for role, path in [("doctor", "/api/doctors/follow-ups"), ("health_manager", "/api/health-managers/follow-ups"), ("doctor", "/api/health-records/followups")]:
            self.user = _make_user(role, str(ObjectId()))
            with self.subTest(path=path):
                response = await self.client.post(path, json=payload)
                self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(len(self.db["followup_records"].docs), 1)

    async def test_unfiltered_lists_only_include_assigned_patients(self):
        other_patient = str(ObjectId())
        _seed_followup_doc(self.db, patient_id=other_patient)
        for role, actor, path in [("doctor", DOCTOR_ID, "/api/doctors/follow-ups"), ("health_manager", MANAGER_ID, "/api/health-managers/follow-ups"), ("doctor", DOCTOR_ID, "/api/health-records/followups/upcoming")]:
            self.user = _make_user(role, actor)
            with self.subTest(path=path):
                response = await self.client.get(path)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual([doc["patient_id"] for doc in response.json()], [PATIENT_ID])
        self.user = _make_user("doctor", str(ObjectId()))
        response = await self.client.get("/api/health-records/followups/upcoming")
        self.assertEqual(response.json(), [])

    async def test_creator_and_cancellation_actor_are_authenticated_identity(self):
        self.user = _make_user("doctor", DOCTOR_ID)
        payload = {"patient_id": PATIENT_ID, "provider_id": DOCTOR_ID, "created_by": str(ObjectId()), "follow_up_type": "phone", "scheduled_date": datetime.utcnow().isoformat(), "description": "x"}
        response = await self.client.post("/api/health-records/followups", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["created_by"], DOCTOR_ID)
        node_id = response.json()["id"]
        response = await self.client.post(f"/api/health-records/followups/{node_id}/cancel", json={"cancel_reason": "x", "canceled_by": str(ObjectId())})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["cancellation_data"]["canceled_by"], DOCTOR_ID)

    async def test_review_endpoint_reaches_completed_only_via_approval(self):
        """FU01 S5 路由：手工录入转 in_review；completed 只能由审阅通过置达。"""
        self.user = _make_user("doctor", DOCTOR_ID)
        node_id = str(self.doc["_id"])
        current = await self.client.get(f"/api/health-records/followups/{node_id}")
        self.assertEqual(current.json()["mutation_version"], 0)
        entry = await self.client.post(f"/api/health-records/followups/{node_id}/complete",
                                       json={"expected_version": 0, "notes": "电话随访结果"})
        self.assertEqual(entry.status_code, 200, entry.text)
        self.assertEqual(entry.json()["status"], "in_review")
        self.assertEqual(entry.json()["mutation_version"], 1)
        doc = self.db["followup_records"].docs[self.doc["_id"]]
        self.assertEqual(doc["completion_data"]["source"], "manual_entry")
        # 手工录入审计已落库
        self.assertEqual(len(self.db["audit_logs"].docs), 1)

        approved = await self.client.post(f"/api/health-records/followups/{node_id}/review",
                                          json={"expected_version": entry.json()["mutation_version"], "decision": "approved", "comment": "核实通过"})
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["status"], "completed")
        self.assertEqual(approved.json()["mutation_version"], 2)
        self.assertEqual(approved.json()["review"]["decision"], "approved")
        self.assertEqual(len(self.db["audit_logs"].docs), 2)

        # 已完成节点再录入/再审阅 → 状态机冲突 409
        for path, body in [("complete", {"expected_version": approved.json()["mutation_version"], "notes": "x"}),
                           ("review", {"expected_version": approved.json()["mutation_version"], "decision": "returned"})]:
            with self.subTest(path=path):
                conflict = await self.client.post(
                    f"/api/health-records/followups/{node_id}/{path}", json=body)
                self.assertEqual(conflict.status_code, 409, conflict.text)

    async def test_manual_entry_and_review_require_observed_version(self):
        self.user = _make_user("doctor", DOCTOR_ID)
        node_id = str(self.doc["_id"])
        for path, body in (("complete", {}), ("review", {"decision": "approved"})):
            with self.subTest(path=path):
                response = await self.client.post(
                    f"/api/health-records/followups/{node_id}/{path}", json=body)
                self.assertEqual(response.status_code, 422, response.text)

    async def test_review_endpoint_requires_provider_or_admin(self):
        """已分配医护但非该节点责任人审阅 → 服务层 403（admin 豁免在服务层，
        路由层患者归属策略仍要求 doctor/health_manager）。"""
        other_doctor = str(ObjectId())
        self.db.users.docs[ObjectId(PATIENT_ID)]["practitioners"].append(other_doctor)
        node_id = str(self.doc["_id"])
        self.db["followup_records"].docs[self.doc["_id"]]["status"] = "in_review"
        self.db["followup_records"].docs[self.doc["_id"]]["completion_data"] = {
            "source": "manual_entry", "result": "电话核实结果"}
        self.db["followup_records"].docs[self.doc["_id"]]["completion_data"] = {
            "source": "manual_entry", "result": "已记录的随访结果"
        }

        self.user = _make_user("doctor", other_doctor)
        denied = await self.client.post(f"/api/health-records/followups/{node_id}/review",
                                        json={"expected_version": 0, "decision": "approved"})
        self.assertEqual(denied.status_code, 403, denied.text)
        self.assertEqual(
            self.db["followup_records"].docs[self.doc["_id"]]["status"], "in_review")

        # 路由层写权限策略（需医疗人员）先于服务层 admin 豁免生效
        self.user = _make_user("admin", str(ObjectId()))
        admin = await self.client.post(f"/api/health-records/followups/{node_id}/review",
                                       json={"expected_version": 0, "decision": "approved"})
        self.assertEqual(admin.status_code, 403, admin.text)
        self.assertEqual(
            self.db["followup_records"].docs[self.doc["_id"]]["status"], "in_review")

        # 责任医护本人可审阅
        self.user = _make_user("doctor", DOCTOR_ID)
        allowed = await self.client.post(f"/api/health-records/followups/{node_id}/review",
                                         json={"expected_version": 0, "decision": "approved"})
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertEqual(allowed.json()["status"], "completed")

    async def test_re_evaluate_endpoint_creates_linked_node(self):
        """FU01 S6 路由：复评新建节点并双向关联；重试幂等返回同一后继。"""
        self.user = _make_user("doctor", DOCTOR_ID)
        node_id = str(self.doc["_id"])
        self.db["followup_records"].docs[self.doc["_id"]]["status"] = "completed"
        next_date = (datetime.utcnow() + timedelta(days=14)).isoformat()

        first = await self.client.post(f"/api/health-records/followups/{node_id}/re-evaluate",
                                       json={"scheduled_date": next_date, "reason": "按计划复评"})
        self.assertEqual(first.status_code, 200, first.text)
        child_id = first.json()["id"]
        self.assertNotEqual(child_id, node_id)
        self.assertEqual(str(first.json()["previous_visit_id"]), node_id)
        original = self.db["followup_records"].docs[self.doc["_id"]]
        self.assertEqual(original["next_visit_id"], child_id)
        self.assertEqual(len(self.db["followup_records"].docs), 2)

        retry = await self.client.post(f"/api/health-records/followups/{node_id}/re-evaluate",
                                       json={"scheduled_date": next_date, "reason": "按计划复评"})
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()["id"], child_id)
        self.assertEqual(len(self.db["followup_records"].docs), 2)


# ---------------------------------------------------------------------------
# 回归 grep：全代码库无假 ID / 无路由层直连随访集合 / 拼写归一
# ---------------------------------------------------------------------------

def _iter_py_files(relative_dir):
    base = BACKEND_DIR / relative_dir
    for path in sorted(base.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def _code_lines(path):
    """去掉纯注释行后的源码行（回归门只认可执行代码，不认注释说明）。"""
    kept = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            continue
        kept.append(line)
    return "\n".join(kept)


class FollowupSourceRegressionTests(unittest.TestCase):
    """以源码文本为断言对象的回归门（设计稿 §五 S2 验收）。"""

    def test_no_fake_follow_up_id_anywhere(self):
        """全代码库（backend/app 代码行）无 new_follow_up_id 假 ID 逻辑。"""
        offenders = []
        for path in _iter_py_files("app"):
            if "new_follow_up_id" in _code_lines(path):
                offenders.append(str(path))
        self.assertEqual(offenders, [], f"残留 new_follow_up_id 假 ID: {offenders}")

    def test_no_router_direct_followup_collection_access(self):
        """路由层不直连 followup_records / follow_ups 集合（唯一入口 FollowupService）。

        断言对象是「直连集合」的真实代码模式：db[...] 取随访集合、
        FollowUpRecord.collection_name 引用、raw find 游标；schema 类名
        （FollowUpRecordResponse 等）是响应契约，合法出现不算直连。
        """
        patterns = (
            re.compile(r"""db\[\s*['"](followup_records|follow_ups)['"]"""),
            re.compile(r"FollowUpRecord\.collection_name"),
            re.compile(r"follow_up_collection\s*="),
        )
        offenders = []
        for path in _iter_py_files("app/api/routers"):
            code = _code_lines(path)
            for pattern in patterns:
                if pattern.search(code):
                    offenders.append(f"{path}: {pattern.pattern}")
        self.assertEqual(offenders, [], f"路由层直连随访集合: {offenders}")

    def test_followup_collection_single_service_entry(self):
        """app/services 内仅 followup_service.py 访问 followup_records 集合。"""
        offenders = []
        for path in _iter_py_files("app/services"):
            text = path.read_text(encoding="utf-8")
            if "followup_records" in text and path.name != "followup_service.py":
                offenders.append(str(path))
        self.assertEqual(offenders, [], f"随访集合服务入口未收敛: {offenders}")

    def test_storage_model_cancel_spelling_normalized(self):
        """存储模型不再产生 cancelled 状态（拼写归一 canceled，§2.2）。"""
        models_text = (BACKEND_DIR / "app" / "models" / "health_record.py").read_text(
            encoding="utf-8")
        self.assertNotIn('"cancelled"', models_text)
        # 服务层取消写入状态为 canceled
        service_text = (BACKEND_DIR / "app" / "services" / "followup_service.py").read_text(
            encoding="utf-8")
        self.assertIn('"status": "canceled"', service_text)

    def test_followup_service_is_registered_dependency(self):
        """FollowupService 已注册为 FastAPI 依赖（唯一随访服务入口可用）。"""
        deps_text = (BACKEND_DIR / "app" / "core" / "dependencies.py").read_text(
            encoding="utf-8")
        self.assertIn("get_followup_service", deps_text)


if __name__ == "__main__":
    unittest.main()
