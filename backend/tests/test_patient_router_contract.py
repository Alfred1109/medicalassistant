"""患者路由统计端点契约测试（2026-11-08 替换 /patients/statistics 存根）。

覆盖 GET /api/patients/statistics：
- 空库：implemented=true + 真实 0 计数（康复计划/训练进度聚合），
  而非存根空对象；
- 命中数据：按 rehab_plans.patient_id / rehab_progress.patient_id 真实聚合，
  完成率 = 已完成记录数 / 总记录数 * 100，无记录时为 0；
- 非患者角色 403。

全部内存打桩 + FastAPI 依赖覆盖，不触碰真实数据库。
"""

import unittest
from datetime import datetime
from bson import ObjectId

import httpx

from app.core.auth import get_current_user
from app.db.mongodb import get_database
from app.main import app
from app.schemas.user import UserResponse

PATIENT_ID = str(ObjectId())


def _get_path(doc, path):
    cur = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _match(doc, filter_):
    for key, cond in filter_.items():
        value = _get_path(doc, key)
        if isinstance(cond, dict) and any(op.startswith("$") for op in cond):
            for op, operand in cond.items():
                if value != operand:
                    return False
            continue
        if value != cond and str(value) != str(cond):
            return False
    return True


class FakeCollection:
    def __init__(self):
        self.docs = {}

    async def count_documents(self, filter_):
        return sum(1 for doc in self.docs.values() if _match(doc, filter_))

    def insert(self, doc):
        self.docs[doc["_id"]] = dict(doc)


class FakeDatabase:
    def __init__(self):
        self._collections = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._collections.setdefault(name, FakeCollection())

    def __getitem__(self, name):
        return getattr(self, name)


def _make_patient():
    return UserResponse(id=PATIENT_ID, email="patient@example.com", name="合成患者",
                        role="patient", is_active=True,
                        createdAt=datetime.utcnow(), updatedAt=datetime.utcnow())


class PatientStatisticsContractTests(unittest.IsolatedAsyncioTestCase):
    def _setup(self, db, user=_make_patient()):
        async def fake_current_user():
            return user

        app.dependency_overrides[get_database] = lambda: db
        app.dependency_overrides[get_current_user] = fake_current_user
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://patient-router-test")

    async def asyncTearDown(self):
        await self._client.aclose()
        app.dependency_overrides.clear()

    async def test_empty_db_returns_real_zeros_not_stub(self):
        """空库：implemented=true + 真实 0，而非存根空对象 {}。"""
        db = FakeDatabase()
        self._setup(db)
        response = await self._client.get("/api/patients/statistics")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["implemented"], True)
        self.assertEqual(body["rehabPlans"], {"total": 0, "active": 0, "completed": 0})
        self.assertEqual(body["progress"],
                         {"totalRecords": 0, "completedRecords": 0, "completionRate": 0})

    async def test_seeded_statistics_aggregated(self):
        """命中数据：计划状态分布与训练进度完成率按真实集合聚合。"""
        db = FakeDatabase()
        db.rehab_plans.insert({"_id": "r1", "patient_id": PATIENT_ID, "status": "active"})
        db.rehab_plans.insert({"_id": "r2", "patient_id": PATIENT_ID, "status": "completed"})
        db.rehab_plans.insert({"_id": "r3", "patient_id": str(ObjectId()), "status": "active"})
        progress = db.rehab_progress
        progress.insert({"_id": "pg1", "patient_id": PATIENT_ID, "completed": True})
        progress.insert({"_id": "pg2", "patient_id": PATIENT_ID, "completed": False})
        progress.insert({"_id": "pg3", "patient_id": PATIENT_ID, "completed": False})

        self._setup(db)
        response = await self._client.get("/api/patients/statistics")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["rehabPlans"], {"total": 2, "active": 1, "completed": 1})
        self.assertEqual(body["progress"]["totalRecords"], 3)
        self.assertEqual(body["progress"]["completedRecords"], 1)
        self.assertEqual(body["progress"]["completionRate"], 33.3)

    async def test_non_patient_forbidden(self):
        other = UserResponse(id=str(ObjectId()), email="d@example.com", name="医生",
                             role="doctor", is_active=True,
                             createdAt=datetime.utcnow(), updatedAt=datetime.utcnow())
        self._setup(FakeDatabase(), other)
        response = await self._client.get("/api/patients/statistics")
        self.assertEqual(response.status_code, 403, response.text)


if __name__ == "__main__":
    unittest.main()
