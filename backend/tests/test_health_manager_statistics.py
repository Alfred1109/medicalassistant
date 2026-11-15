"""健康管理师工作统计契约测试（2026-11-15 替换存根空对象）。

覆盖 GET /api/health-managers/statistics：
- 健康管理师角色可见，返回真实聚合（患者数、康复方案状态分布、随访状态
  分布），响应体非空字典且带 implemented 标记；
- 无数据时如实为 0（不再返回存根空对象 {}）；
- 归属判定与对象授权同源（health_managers 归属字段），非归属患者的
  方案/随访不计入；
- 非健康管理师角色 403（医生/患者均被拒）；
- 账号不存在 404；患者标识歧义按 PATIENT_IDENTITY_AMBIGUOUS/503 透传。

全部内存打桩 + FastAPI 依赖覆盖，不触碰真实数据库。
"""

import unittest
from datetime import datetime, timedelta

import httpx
from bson import ObjectId

from app.core.auth import get_current_user
from app.db.mongodb import get_database
from app.main import app
from app.schemas.user import UserResponse

MANAGER_ID = str(ObjectId())
OTHER_MANAGER_ID = str(ObjectId())
PATIENT_ID = str(ObjectId())
OTHER_PATIENT_ID = str(ObjectId())


# ---------------------------------------------------------------------------
# 内存版 Mongo 桩：仅实现本端点用到的最小查询能力
# ---------------------------------------------------------------------------

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
                if op == "$in":
                    values = value if isinstance(value, list) else [value]
                    if not any(str(item) in [str(o) for o in operand] for item in values):
                        return False
                elif op == "$ne":
                    # 字段缺失视为不等于（与 MongoDB $ne 语义一致）
                    if operand is not None and value == operand:
                        return False
                elif op == "$gte":
                    try:
                        if not (value is not None and value >= operand):
                            return False
                    except TypeError:
                        # 类型括号语义：字符串与 datetime 不参与范围比较
                        return False
                elif op == "$lte":
                    try:
                        if not (value is not None and value <= operand):
                            return False
                    except TypeError:
                        return False
                elif op == "$lt":
                    try:
                        if not (value is not None and value < operand):
                            return False
                    except TypeError:
                        return False
                else:
                    if value != operand:
                        return False
            continue
        if value != cond and str(value) != str(cond):
            return False
    return True


class FakeCursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, key, direction=1):
        return self

    def skip(self, count):
        self.docs = self.docs[count:]
        return self

    def limit(self, count):
        self.docs = self.docs[:count]
        return self

    async def to_list(self, length=None):
        return list(self.docs if length is None else self.docs[:length])

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for doc in self.docs:
            yield dict(doc)


class FakeCollection:
    def __init__(self):
        self.docs = {}

    async def find_one(self, filter_, *args, **kwargs):
        for doc in self.docs.values():
            if _match(doc, filter_):
                return dict(doc)
        return None

    def find(self, filter_, projection=None, **kwargs):
        return FakeCursor([doc for doc in self.docs.values() if _match(doc, filter_)])

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


def _make_user(role="health_manager", user_id=MANAGER_ID):
    return UserResponse(id=user_id, email="user@example.com", name="合成用户",
                        role=role, is_active=True,
                        createdAt=datetime.utcnow(), updatedAt=datetime.utcnow())


class HealthManagerStatisticsContractTestBase(unittest.IsolatedAsyncioTestCase):
    def _setup(self, db, user):
        async def fake_current_user():
            return user

        app.dependency_overrides[get_database] = lambda: db
        app.dependency_overrides[get_current_user] = fake_current_user
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://health-manager-statistics-test")

    async def asyncTearDown(self):
        await self._client.aclose()
        app.dependency_overrides.clear()

    def _seed_manager(self, db):
        db.users.insert({"_id": ObjectId(MANAGER_ID), "role": "health_manager", "name": "管理师"})

    def _seed_assigned_patient(self, db, patient_id=PATIENT_ID, manager_id=MANAGER_ID):
        db.users.insert({"_id": ObjectId(patient_id), "role": "patient", "name": "张三",
                         "health_managers": [manager_id], "age": 40, "gender": "女",
                         "diagnosis": "膝骨关节炎", "status": "在管理"})


class HealthManagerStatisticsContractTests(HealthManagerStatisticsContractTestBase):
    async def test_seeded_statistics_are_real_aggregation(self):
        """命中数据：患者数、方案状态、随访状态真实聚合，不读取旧执行集合。"""
        db = FakeDatabase()
        self._seed_manager(db)
        self._seed_assigned_patient(db)
        self._seed_assigned_patient(db, OTHER_PATIENT_ID)

        db.rehab_plans.insert({"_id": "r1", "patient_id": PATIENT_ID, "status": "active"})
        db.rehab_plans.insert({"_id": "r2", "patient_id": PATIENT_ID, "status": "active"})
        db.rehab_plans.insert({"_id": "r3", "patient_id": OTHER_PATIENT_ID, "status": "completed"})
        # 非归属患者的方案不计入
        db.rehab_plans.insert({"_id": "r4", "patient_id": str(ObjectId()), "status": "active"})

        db.followup_records.insert({"_id": "f1", "patient_id": PATIENT_ID,
                                    "created_by": MANAGER_ID, "status": "completed",
                                    "scheduled_date": datetime.utcnow()})
        db.followup_records.insert({"_id": "f2", "patient_id": PATIENT_ID,
                                    "created_by": MANAGER_ID, "status": "scheduled",
                                    "scheduled_date": datetime.utcnow()})
        db.followup_records.insert({"_id": "f3", "patient_id": OTHER_PATIENT_ID,
                                    "created_by": MANAGER_ID, "status": "scheduled",
                                    "scheduled_date": datetime.utcnow()})
        db.followup_records.insert({"_id": "f4", "patient_id": PATIENT_ID,
                                    "created_by": MANAGER_ID, "status": "canceled",
                                    "scheduled_date": datetime.utcnow()})
        # 已删除节点不计入（与 FollowupService 口径同源）
        db.followup_records.insert({"_id": "f5", "patient_id": PATIENT_ID,
                                    "created_by": MANAGER_ID, "status": "scheduled",
                                    "scheduled_date": datetime.utcnow(), "deleted": True})

        # 历史集合虽有记录，也不应进入新的自报统计。
        db.rehab_progress.insert({"_id": "pg1", "patient_id": PATIENT_ID, "completed": True,
                                  "date": datetime.utcnow() - timedelta(days=1)})
        db.rehab_execution_events.insert({"_id": "ev1", "patient_id": PATIENT_ID,
            "event_type": "patient_report", "schema_version": 1, "source": "patient_self_report",
            "execution_status": "not_done", "performed_at": datetime.utcnow() - timedelta(days=1)})
        db.rehab_execution_events.insert({"_id": "ev2", "patient_id": str(ObjectId()),
            "event_type": "patient_report", "schema_version": 1, "source": "patient_self_report",
            "execution_status": "completed", "performed_at": datetime.utcnow()})

        self._setup(db, _make_user())
        response = await self._client.get("/api/health-managers/statistics")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body)
        self.assertEqual(body["implemented"], True)
        self.assertEqual(body["patientCount"], 2)
        self.assertEqual(body["rehabPlans"], {"total": 3, "active": 2, "completed": 1})
        self.assertEqual(body["followUps"], {"total": 4, "completed": 1, "pending": 2})
        self.assertEqual(body["patientSelfReportsThisMonth"]["total"], 1)
        self.assertEqual(body["patientSelfReportsThisMonth"]["not_done"], 1)

    async def test_empty_scope_returns_real_zeros_not_stub(self):
        """无数据：implemented=true + 真实 0 计数，而非存根空对象。"""
        db = FakeDatabase()
        self._seed_manager(db)
        self._setup(db, _make_user())
        response = await self._client.get("/api/health-managers/statistics")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body)
        self.assertEqual(body["implemented"], True)
        self.assertEqual(body["patientCount"], 0)
        self.assertEqual(body["rehabPlans"], {"total": 0, "active": 0, "completed": 0})
        self.assertEqual(body["followUps"], {"total": 0, "completed": 0, "pending": 0})
        self.assertEqual(body["patientSelfReportsThisMonth"]["total"], 0)

    async def test_other_manager_patients_not_counted(self):
        """归属隔离：其他健康管理师的患者不计入本人的统计。"""
        db = FakeDatabase()
        self._seed_manager(db)
        db.users.insert({"_id": ObjectId(OTHER_MANAGER_ID), "role": "health_manager", "name": "他人"})
        db.users.insert({"_id": ObjectId(PATIENT_ID), "role": "patient", "name": "他人患者",
                         "health_managers": [OTHER_MANAGER_ID]})
        db.rehab_plans.insert({"_id": "r1", "patient_id": PATIENT_ID, "status": "active"})

        self._setup(db, _make_user())
        response = await self._client.get("/api/health-managers/statistics")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["patientCount"], 0)
        self.assertEqual(body["rehabPlans"]["total"], 0)

    async def test_doctor_role_forbidden(self):
        """医生角色访问健管师统计端点：403。"""
        db = FakeDatabase()
        db.users.insert({"_id": ObjectId(MANAGER_ID), "role": "doctor", "name": "医生"})
        self._setup(db, _make_user(role="doctor"))
        response = await self._client.get("/api/health-managers/statistics")
        self.assertEqual(response.status_code, 403, response.text)

    async def test_patient_role_forbidden(self):
        db = FakeDatabase()
        self._setup(db, _make_user(role="patient", user_id=PATIENT_ID))
        response = await self._client.get("/api/health-managers/statistics")
        self.assertEqual(response.status_code, 403, response.text)

    async def test_unknown_manager_returns_404(self):
        db = FakeDatabase()
        self._setup(db, _make_user())
        response = await self._client.get("/api/health-managers/statistics")
        self.assertEqual(response.status_code, 404, response.text)

    async def test_ambiguous_patient_identity_returns_503(self):
        """同一患者标识双文档：适配器 PATIENT_IDENTITY_AMBIGUOUS/503 透传，
        不被降级为 500（与医生端同一修法）。"""
        db = FakeDatabase()
        self._seed_manager(db)
        db.users.insert({"_id": ObjectId(PATIENT_ID), "role": "patient",
                         "name": "患者A", "health_managers": [MANAGER_ID]})
        db.users.insert({"_id": PATIENT_ID, "role": "patient",
                         "name": "患者B", "health_managers": [MANAGER_ID]})
        self._setup(db, _make_user())
        response = await self._client.get("/api/health-managers/statistics")
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["error"], "PATIENT_IDENTITY_AMBIGUOUS")


if __name__ == "__main__":
    unittest.main()
