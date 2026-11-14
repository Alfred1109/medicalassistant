"""健康管理师路由契约测试（患者档案架构第一波段 T7）。

覆盖 GET /api/health-managers/patients：
- 归属列表经 PatientCRUD.find_assigned_patients（与对象授权同源的
  LegacyPatientRepository 路径），响应形状与医生列表一致；
- 同一患者标识存在 ObjectId/字符串双文档时，适配器歧义防护
  （PATIENT_IDENTITY_AMBIGUOUS/503）经路由层透传全局处理器，
  不被 except Exception 降级为 500（与 doctor_router 同一修法）；
- 非健康管理师角色 403。

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

MANAGER_ID = str(ObjectId())
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
                if op == "$in":
                    values = value if isinstance(value, list) else [value]
                    if not any(str(item) in [str(o) for o in operand] for item in values):
                        return False
                elif value != operand:
                    return False
            continue
        if value != cond and str(value) != str(cond):
            return False
    return True


class FakeCursor:
    def __init__(self, docs):
        self.docs = docs

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
        # 域模式读取（patient_domain_state 单例）需要 find_one；
        # 未播种状态文档时返回 None，即按 legacy 域处理。
        for doc in self.docs.values():
            if _match(doc, filter_):
                return dict(doc)
        return None

    def find(self, filter_, projection=None, **kwargs):
        return FakeCursor([doc for doc in self.docs.values() if _match(doc, filter_)])

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


class HealthManagerRouterContractTestBase(unittest.IsolatedAsyncioTestCase):
    def _setup(self, db, user):
        async def fake_current_user():
            return user

        app.dependency_overrides[get_database] = lambda: db
        app.dependency_overrides[get_current_user] = fake_current_user
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://health-manager-router-test")

    async def asyncTearDown(self):
        await self._client.aclose()
        app.dependency_overrides.clear()


class ManagerPatientsContractTests(HealthManagerRouterContractTestBase):
    async def test_assigned_patients_returned(self):
        """命中归属：返回真实患者（id/name 形状与医生列表一致）。"""
        db = FakeDatabase()
        db.users.insert({"_id": ObjectId(MANAGER_ID), "role": "health_manager", "name": "管理师"})
        db.users.insert({"_id": ObjectId(PATIENT_ID), "role": "patient", "name": "张三",
                         "health_managers": [MANAGER_ID], "age": 40, "gender": "女",
                         "diagnosis": "膝骨关节炎", "status": "在管理"})
        self._setup(db, _make_user())
        response = await self._client.get("/api/health-managers/patients")
        self.assertEqual(response.status_code, 200, response.text)
        patients = response.json()
        self.assertEqual(len(patients), 1)
        self.assertEqual(patients[0]["id"], PATIENT_ID)
        self.assertEqual(patients[0]["name"], "张三")

    async def test_no_assigned_patients_returns_empty_list(self):
        db = FakeDatabase()
        db.users.insert({"_id": ObjectId(MANAGER_ID), "role": "health_manager", "name": "管理师"})
        self._setup(db, _make_user())
        response = await self._client.get("/api/health-managers/patients")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [])

    async def test_ambiguous_patient_identity_returns_503(self):
        """同一患者标识 ObjectId/字符串双文档：适配器 PATIENT_IDENTITY_AMBIGUOUS/503
        透传，不得被 except Exception 降级为 500。"""
        db = FakeDatabase()
        db.users.insert({"_id": ObjectId(MANAGER_ID), "role": "health_manager", "name": "管理师"})
        db.users.insert({"_id": ObjectId(PATIENT_ID), "role": "patient",
                         "name": "患者A", "health_managers": [MANAGER_ID]})
        db.users.insert({"_id": PATIENT_ID, "role": "patient",
                         "name": "患者B", "health_managers": [MANAGER_ID]})
        self._setup(db, _make_user())
        response = await self._client.get("/api/health-managers/patients")
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["error"], "PATIENT_IDENTITY_AMBIGUOUS")

    async def test_non_health_manager_forbidden(self):
        self._setup(FakeDatabase(), _make_user(role="patient", user_id=PATIENT_ID))
        response = await self._client.get("/api/health-managers/patients")
        self.assertEqual(response.status_code, 403, response.text)


if __name__ == "__main__":
    unittest.main()
