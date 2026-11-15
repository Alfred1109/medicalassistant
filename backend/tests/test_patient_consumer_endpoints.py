"""T75 患者端功能面的授权契约：宣教/指标/预警患者自取 + Agent 角色守卫。

契约（与 test_rehab_agent_auth_contract 同款打桩方式，不触碰真实 MongoDB）：
1. 患者自取本人数据走共享 self 解析（legacy 同文档 / canonical 链接核验），
   显式请求他人 ID 一律 403；
2. 医护角色沿用工作台 _patient_for 归属/项目校验；
3. 动态 Agent 平台仅医疗角色可用，患者角色一律 403（T75 安全缺口收口）。
"""

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from bson import ObjectId
from jose import jwt

from app.core.config import settings
from app.core.dependencies import get_agent_service, get_database
from app.main import app
from app.schemas.user import UserResponse
from app.services.user_service import UserService
from patient_identity_fake import identity_find_from_lookup, legacy_domain_state

OPERATOR_ID = "507f1f77bcf86cd799439011"
PATIENT_ID = str(ObjectId())
OTHER_PATIENT_ID = str(ObjectId())


def make_operator(role="patient", user_id=PATIENT_ID):
    now = datetime.utcnow()
    return UserResponse(id=user_id, email="actor@example.com", name="合成操作者",
                        role=role, is_active=True, createdAt=now, updatedAt=now)


class FakeCursor:
    """支持 sort/skip/limit/to_list/异步迭代的最小 find 游标。"""

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
        return list(self.rows if length is None else self.rows[:length])

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        if self._index >= len(self.rows):
            raise StopAsyncIteration
        row = self.rows[self._index]
        self._index += 1
        return row


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    async def find_one(self, query, projection=None, **kwargs):
        candidates = query.get("_id")
        if isinstance(candidates, dict) and "$in" in candidates:
            for candidate in candidates["$in"]:
                for doc in self.docs:
                    if doc.get("_id") == candidate:
                        return doc
            return None
        return next((doc for doc in self.docs if doc.get("_id") == query.get("_id")), None)

    def find(self, query, projection=None, **kwargs):
        rows = self.docs
        identifier = query.get("_id")
        if isinstance(identifier, dict) and "$in" in identifier:
            rows = [doc for doc in self.docs if doc.get("_id") in identifier["$in"]]
        else:
            rows = [doc for doc in self.docs
                    if all(doc.get(key) == value for key, value in query.items())]
        if query.get("patient_id") is not None and "_id" not in query:
            rows = [doc for doc in self.docs if doc.get("patient_id") == query["patient_id"]]
        return FakeCursor(rows)

    async def insert_one(self, document):
        self.docs.append(document)
        return SimpleNamespace(inserted_id=document.get("_id"))


def make_fake_database():
    """按属性访问提供集合的内存库；患者域固定 legacy（无状态文档）。"""
    database = MagicMock()
    database.users = FakeCollection()
    database.health_data_alerts = FakeCollection()
    database.education_materials = FakeCollection()
    database.education_assignments = FakeCollection()
    database.clinical_indicator_rules = FakeCollection()
    database.clinical_reports = FakeCollection()
    legacy_domain_state(database)
    return database


class PatientConsumerEndpointTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.database = make_fake_database()
        self.patient_doc = {"_id": ObjectId(PATIENT_ID), "role": "patient",
                            "name": "合成患者", "practitioners": []}
        self.database.users.docs.append(self.patient_doc)
        identity_find_from_lookup(self.database.users)

        async def fake_database():
            yield self.database

        app.dependency_overrides[get_database] = fake_database
        self.operator = make_operator()
        self.get_user_mock = AsyncMock(return_value=self.operator)
        self.lookup = patch.object(UserService, "get_user_by_id", new=self.get_user_mock)
        self.lookup.start()
        self.client = httpx.AsyncClient(app=app, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        self.lookup.stop()
        app.dependency_overrides.clear()

    def set_operator(self, role, user_id=PATIENT_ID):
        self.operator = make_operator(role=role, user_id=user_id)
        self.get_user_mock.return_value = self.operator
        return self.operator

    def auth(self, operator=None):
        actor = operator or self.operator
        token = jwt.encode({"sub": actor.id, "token_type": "access",
                            "exp": datetime.utcnow() + timedelta(minutes=5)},
                           settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return {"Authorization": f"Bearer {token}"}

    def seed_alerts(self):
        self.database.health_data_alerts.docs = [
            {"_id": ObjectId(), "patient_id": PATIENT_ID, "data_type": "blood_pressure",
             "value": {"systolic": 150, "diastolic": 95}, "alert_level": "critical",
             "status": "active", "recorded_at": datetime(2026, 11, 10, tzinfo=timezone.utc)},
            {"_id": ObjectId(), "patient_id": PATIENT_ID, "data_type": "blood_sugar",
             "value": 9.8, "unit": "mmol/L", "alert_level": "warning",
             "status": "resolved", "resolution_notes": "已复测正常",
             "recorded_at": datetime(2026, 11, 12, tzinfo=timezone.utc)},
            {"_id": ObjectId(), "patient_id": OTHER_PATIENT_ID, "data_type": "heart_rate",
             "value": 130, "alert_level": "warning", "status": "active",
             "recorded_at": datetime(2026, 11, 13, tzinfo=timezone.utc)},
        ]

    # ── 患者自取本人数据 ──────────────────────────────────────────────

    async def test_patient_reads_own_alerts_and_never_others(self):
        self.seed_alerts()
        self.set_operator("patient", PATIENT_ID)
        response = await self.client.get(f"/api/clinical/patients/{PATIENT_ID}/alerts",
                                         headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        alerts = response.json()["alerts"]
        self.assertEqual(len(alerts), 2)
        self.assertTrue(all(alert["patient_id"] == PATIENT_ID for alert in alerts))
        # 危急预警不因倒序丢失；最新记录在前（recorded_at 倒序）
        self.assertEqual(alerts[0]["data_type"], "blood_sugar")
        self.assertEqual(alerts[1]["alert_level"], "critical")

        response = await self.client.get(f"/api/clinical/patients/{OTHER_PATIENT_ID}/alerts",
                                         headers=self.auth())
        self.assertEqual(response.status_code, 403, response.text)

    async def test_patient_alerts_read_projection_has_no_write_path(self):
        self.seed_alerts()
        self.set_operator("patient", PATIENT_ID)
        response = await self.client.get(f"/api/clinical/patients/{PATIENT_ID}/alerts",
                                         headers=self.auth())
        alert = response.json()["alerts"][0]
        for field in ("id", "patient_id", "data_type", "value", "alert_level", "status"):
            self.assertIn(field, alert)
        self.assertNotIn("threshold_id", alert)

    async def test_doctor_without_assignment_is_rejected_for_alerts(self):
        self.seed_alerts()
        doctor_id = str(ObjectId())
        self.set_operator("doctor", doctor_id)
        response = await self.client.get(f"/api/clinical/patients/{PATIENT_ID}/alerts",
                                         headers=self.auth())
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["detail"]["code"], "PATIENT_NOT_ASSIGNED")

    async def test_patient_reads_own_indicators_and_education_self_scoped(self):
        self.set_operator("patient", PATIENT_ID)
        response = await self.client.get(f"/api/clinical/patients/{PATIENT_ID}/indicators",
                                         headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["configured"])

        response = await self.client.get("/api/clinical/education", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["materials"], [])

    async def test_alerts_and_indicators_require_authentication(self):
        self.seed_alerts()
        response = await self.client.get(f"/api/clinical/patients/{PATIENT_ID}/alerts")
        self.assertEqual(response.status_code, 401, response.text)
        response = await self.client.get(f"/api/clinical/patients/{PATIENT_ID}/indicators")
        self.assertEqual(response.status_code, 401, response.text)

    # ── Agent 平台角色守卫（T75 安全缺口收口） ─────────────────────────

    async def test_agent_platform_forbids_patient_role(self):
        self.set_operator("patient", PATIENT_ID)
        agent_service = AsyncMock()
        app.dependency_overrides[get_agent_service] = lambda: agent_service
        headers = self.auth()
        for method, path, kwargs in (
                ("get", "/api/agents/", {}),
                ("post", "/api/agents/", {"json": {"name": "合成", "description": "合成"}}),
                ("get", "/api/agents/synthetic", {}),
                ("put", "/api/agents/synthetic", {"json": {"name": "合成"}}),
                ("delete", "/api/agents/synthetic", {}),
                ("post", "/api/agents/synthetic/query", {"json": {"query": "合成"}}),
                ("post", "/api/agents/synthetic/tools", {"json": {}}),
                ("post", "/api/agents/generate-parameters", {"json": {}}),
        ):
            response = await getattr(self.client, method)(path, headers=headers, **kwargs)
            self.assertEqual(response.status_code, 403, f"{method.upper()} {path}: {response.text}")
        agent_service.list_agents.assert_not_awaited()

    async def test_agent_platform_allows_clinical_roles(self):
        agent_service = AsyncMock()
        agent_service.list_agents = AsyncMock(return_value=[])
        now = datetime.utcnow()
        agent_service.get_agent_by_id = AsyncMock(return_value={
            "_id": "synthetic", "name": "合成助手", "description": "合成", "model": "synthetic",
            "system_prompt": "合成", "tools": [], "metadata": {},
            "created_at": now, "updated_at": now})
        app.dependency_overrides[get_agent_service] = lambda: agent_service
        for role, user_id in (("doctor", str(ObjectId())), ("health_manager", str(ObjectId())),
                              ("admin", str(ObjectId()))):
            self.set_operator(role, user_id)
            response = await self.client.get("/api/agents/", headers=self.auth())
            self.assertEqual(response.status_code, 200, f"{role}: {response.text}")
            response = await self.client.get("/api/agents/synthetic", headers=self.auth())
            self.assertEqual(response.status_code, 200, f"{role}: {response.text}")

    async def test_agent_platform_requires_authentication(self):
        response = await self.client.get("/api/agents/")
        self.assertEqual(response.status_code, 401, response.text)


if __name__ == "__main__":
    unittest.main()
