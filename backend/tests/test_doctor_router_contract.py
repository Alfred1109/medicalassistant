"""医生路由诚实数据契约测试（2026-11-08 修复模拟患者与存根端点）。

覆盖 GET /api/doctors：
- /patients：空库/无关联患者如实返回空列表（绝不返回 mock_i 模拟患者）；
  数据库异常如实 500；命中数据返回真实患者。
- /statistics：真实聚合（患者数、康复计划状态分布、本月完成训练记录数），
  空库返回真实 0 而非存根空对象。
- /patient-monitoring/{id}：真实聚合快照（绑定设备数、康复计划状态分布、
  近 30 天完成训练记录数）；患者不存在 404、不属于当前医生 403。

全部内存打桩 + FastAPI 依赖覆盖，不触碰真实数据库。
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
from bson import ObjectId

from app.core.auth import get_current_user
from app.db.mongodb import get_database
from app.main import app
from app.schemas.user import UserResponse

DOCTOR_ID = str(ObjectId())
PATIENT_ID = str(ObjectId())
OTHER_PATIENT_ID = str(ObjectId())


# ---------------------------------------------------------------------------
# 内存版 Mongo 桩：仅实现本路由用到的最小查询能力
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
                try:
                    if op == "$gte" and not (value is not None and value >= operand):
                        return False
                    if op == "$lt" and not (value is not None and value < operand):
                        return False
                except TypeError:
                    # 类型括号语义：类型不匹配（字符串 vs datetime）不命中
                    return False
                if op == "$in":
                    values = value if isinstance(value, list) else [value]
                    if not any(str(item) in [str(o) for o in operand] for item in values):
                        return False
            continue
        if value != cond and str(value) != str(cond):
            return False
    return True


class FakeCursor:
    def __init__(self, docs):
        self.docs = docs

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for doc in self.docs:
            yield dict(doc)


class FakeCollection:
    def __init__(self):
        self.docs = {}
        self.find_one_error = None

    async def find_one(self, filter_):
        if self.find_one_error is not None:
            raise self.find_one_error
        for doc in self.docs.values():
            if _match(doc, filter_):
                return dict(doc)
        return None

    def find(self, filter_, projection=None):
        if self.find_one_error is not None:
            raise self.find_one_error
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


def _make_user(role="doctor", user_id=DOCTOR_ID):
    return UserResponse(id=user_id, email="user@example.com", name="合成用户",
                        role=role, is_active=True,
                        createdAt=datetime.utcnow(), updatedAt=datetime.utcnow())


class DoctorRouterContractTestBase(unittest.IsolatedAsyncioTestCase):
    def _setup(self, db, user):
        async def fake_current_user():
            return user

        app.dependency_overrides[get_database] = lambda: db
        app.dependency_overrides[get_current_user] = fake_current_user
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://doctor-router-test")

    async def asyncTearDown(self):
        await self._client.aclose()
        app.dependency_overrides.clear()


class DoctorPatientsContractTests(DoctorRouterContractTestBase):
    async def test_empty_db_returns_empty_list_not_mock(self):
        """空库：如实返回空列表，绝不返回 mock_i 模拟患者。"""
        db = FakeDatabase()
        db.users.insert({"_id": ObjectId(DOCTOR_ID), "role": "doctor", "name": "医生"})
        self._setup(db, _make_user())
        response = await self._client.get("/api/doctors/patients")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [])

    async def test_no_linked_patients_returns_empty_list(self):
        """医生存在但无关联患者：返回空列表。"""
        db = FakeDatabase()
        db.users.insert({"_id": ObjectId(DOCTOR_ID), "role": "doctor",
                         "name": "医生", "patients": []})
        self._setup(db, _make_user())
        response = await self._client.get("/api/doctors/patients")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [])

    async def test_seeded_patients_returned(self):
        """命中数据：返回真实患者（含 id/name 等字段，无 mock 前缀）。"""
        db = FakeDatabase()
        db.users.insert({"_id": ObjectId(DOCTOR_ID), "role": "doctor", "name": "医生",
                         "patients": [PATIENT_ID]})
        db.users.insert({"_id": ObjectId(PATIENT_ID), "role": "patient", "name": "张三", "practitioners": [DOCTOR_ID],
                         "age": 40, "gender": "男", "diagnosis": "腰椎间盘突出",
                         "status": "在治疗"})
        self._setup(db, _make_user())
        response = await self._client.get("/api/doctors/patients")
        self.assertEqual(response.status_code, 200, response.text)
        patients = response.json()
        self.assertEqual(len(patients), 1)
        self.assertEqual(patients[0]["id"], PATIENT_ID)
        self.assertEqual(patients[0]["name"], "张三")
        self.assertFalse(str(patients[0]["id"]).startswith("mock_"))

    async def test_db_error_returns_500_not_mock(self):
        """数据库异常：如实 500，绝不回退模拟患者。"""
        db = FakeDatabase()
        db.users.find_one_error = RuntimeError("db down")
        self._setup(db, _make_user())
        response = await self._client.get("/api/doctors/patients")
        self.assertEqual(response.status_code, 500, response.text)
        self.assertNotIn("mock", response.text)

    async def test_non_doctor_forbidden(self):
        self._setup(FakeDatabase(), _make_user(role="patient", user_id=PATIENT_ID))
        response = await self._client.get("/api/doctors/patients")
        self.assertEqual(response.status_code, 403, response.text)


class DoctorStatisticsContractTests(DoctorRouterContractTestBase):
    async def test_empty_db_returns_real_zeros_not_stub(self):
        """空库：implemented=true + 真实 0 计数，而非存根空对象。"""
        db = FakeDatabase()
        db.users.insert({"_id": ObjectId(DOCTOR_ID), "role": "doctor", "name": "医生"})
        self._setup(db, _make_user())
        response = await self._client.get("/api/doctors/statistics")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["implemented"], True)
        self.assertEqual(body["patientCount"], 0)
        self.assertEqual(body["rehabPlans"], {"total": 0, "active": 0, "completed": 0})
        self.assertEqual(body["completedSessionsThisMonth"], 0)

    async def test_seeded_statistics_aggregated(self):
        """命中数据：患者数、计划状态分布、本月完成训练记录数按真实集合聚合。"""
        db = FakeDatabase()
        db.users.insert({"_id": ObjectId(DOCTOR_ID), "role": "doctor", "name": "医生",
                         "patients": [PATIENT_ID, OTHER_PATIENT_ID]})
        for patient_id in [PATIENT_ID, OTHER_PATIENT_ID]:
            db.users.insert({"_id": ObjectId(patient_id), "role": "patient",
                             "practitioners": [DOCTOR_ID]})
        plans = db.rehab_plans
        plans.insert({"_id": "r1", "practitioner_id": DOCTOR_ID, "status": "active"})
        plans.insert({"_id": "r2", "practitioner_id": DOCTOR_ID, "status": "active"})
        plans.insert({"_id": "r3", "practitioner_id": DOCTOR_ID, "status": "completed"})
        plans.insert({"_id": "r4", "practitioner_id": str(ObjectId()), "status": "active"})
        progress = db.rehab_progress
        progress.insert({"_id": "pg1", "patient_id": PATIENT_ID, "completed": True,
                         "date": datetime.utcnow() - timedelta(days=1)})
        # 字符串日期不参与 datetime 范围比较（类型括号），不计入本月
        progress.insert({"_id": "pg2", "patient_id": PATIENT_ID, "completed": True,
                         "date": "2020-01-01T00:00:00"})
        # 未完成的不计入
        progress.insert({"_id": "pg3", "patient_id": PATIENT_ID, "completed": False,
                         "date": datetime.utcnow()})

        self._setup(db, _make_user())
        response = await self._client.get("/api/doctors/statistics")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["patientCount"], 2)
        self.assertEqual(body["rehabPlans"], {"total": 3, "active": 2, "completed": 1})
        self.assertEqual(body["completedSessionsThisMonth"], 1)

    async def test_unknown_doctor_returns_404(self):
        db = FakeDatabase()
        self._setup(db, _make_user())
        response = await self._client.get("/api/doctors/statistics")
        self.assertEqual(response.status_code, 404, response.text)


class PatientMonitoringContractTests(DoctorRouterContractTestBase):
    def _seed_doctor(self, db):
        db.users.insert({"_id": ObjectId(DOCTOR_ID), "role": "doctor", "name": "医生",
                         "patients": [PATIENT_ID]})

    async def test_patient_not_found_returns_404(self):
        db = FakeDatabase()
        self._seed_doctor(db)
        self._setup(db, _make_user())
        response = await self._client.get(f"/api/doctors/patient-monitoring/{OTHER_PATIENT_ID}")
        self.assertEqual(response.status_code, 404, response.text)

    async def test_patient_of_other_doctor_returns_403(self):
        db = FakeDatabase()
        self._seed_doctor(db)
        db.users.insert({"_id": ObjectId(OTHER_PATIENT_ID), "role": "patient", "name": "外人"})
        self._setup(db, _make_user())
        response = await self._client.get(f"/api/doctors/patient-monitoring/{OTHER_PATIENT_ID}")
        self.assertEqual(response.status_code, 403, response.text)

    async def test_monitoring_snapshot_aggregated(self):
        """命中数据：绑定设备数、计划状态分布、近 30 天完成训练记录数为真实聚合。"""
        db = FakeDatabase()
        self._seed_doctor(db)
        db.users.insert({"_id": ObjectId(PATIENT_ID), "role": "patient", "name": "张三", "practitioners": [DOCTOR_ID]})
        db.devices.insert({"_id": "dev1", "patient_id": PATIENT_ID, "status": "active"})
        db.devices.insert({"_id": "dev2", "patient_id": PATIENT_ID, "status": "inactive"})
        db.rehab_plans.insert({"_id": "r1", "patient_id": PATIENT_ID, "status": "active"})
        db.rehab_progress.insert({"_id": "pg1", "patient_id": PATIENT_ID, "completed": True,
                                  "date": datetime.utcnow() - timedelta(days=2)})
        db.rehab_progress.insert({"_id": "pg2", "patient_id": PATIENT_ID, "completed": True,
                                  "date": datetime.utcnow() - timedelta(days=60)})

        self._setup(db, _make_user())
        response = await self._client.get(f"/api/doctors/patient-monitoring/{PATIENT_ID}")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["implemented"], True)
        self.assertEqual(body["patientId"], PATIENT_ID)
        self.assertEqual(body["boundDevices"], 2)
        self.assertEqual(body["rehabPlans"], {"total": 1, "active": 1, "completed": 0})
        self.assertEqual(body["completedSessionsLast30Days"], 1)

    async def test_invalid_patient_id_returns_404(self):
        db = FakeDatabase()
        self._seed_doctor(db)
        self._setup(db, _make_user())
        response = await self._client.get("/api/doctors/patient-monitoring/not-an-objectid")
        self.assertEqual(response.status_code, 404, response.text)


class DoctorPatientAuthorityTests(DoctorRouterContractTestBase):
    async def test_patient_side_link_controls_list_and_statistics(self):
        db = FakeDatabase()
        # 旧反向列表只指向已撤销患者；当前归属包含历史 ObjectId 类型。
        db.users.insert({"_id": ObjectId(DOCTOR_ID), "role": "doctor",
                         "patients": [OTHER_PATIENT_ID]})
        db.users.insert({"_id": ObjectId(PATIENT_ID), "role": "patient",
                         "name": "当前患者", "practitioners": [ObjectId(DOCTOR_ID)]})
        db.users.insert({"_id": ObjectId(OTHER_PATIENT_ID), "role": "patient",
                         "practitioners": []})
        self._setup(db, _make_user())
        listed = await self._client.get("/api/doctors/patients")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual([doc["id"] for doc in listed.json()], [PATIENT_ID])
        stats = await self._client.get("/api/doctors/statistics")
        self.assertEqual(stats.status_code, 200, stats.text)
        self.assertEqual(stats.json()["patientCount"], 1)

    async def test_stale_doctor_link_does_not_grant_record_or_monitoring(self):
        db = FakeDatabase()
        db.users.insert({"_id": ObjectId(DOCTOR_ID), "role": "doctor",
                         "patients": [PATIENT_ID]})
        db.users.insert({"_id": ObjectId(PATIENT_ID), "role": "patient",
                         "practitioners": []})
        self._setup(db, _make_user())
        with patch("app.api.routers.doctor_router.get_health_record_for_patient",
                   new_callable=AsyncMock) as load_record:
            for endpoint in ["health-records", "patient-monitoring"]:
                response = await self._client.get(f"/api/doctors/{endpoint}/{PATIENT_ID}")
                self.assertEqual(response.status_code, 403, response.text)
            load_record.assert_not_awaited()

    async def test_current_patient_link_grants_record_and_monitoring_without_reverse_link(self):
        db = FakeDatabase()
        db.users.insert({"_id": ObjectId(DOCTOR_ID), "role": "doctor", "patients": []})
        db.users.insert({"_id": ObjectId(PATIENT_ID), "role": "patient",
                         "name": "当前患者", "practitioners": [DOCTOR_ID]})
        self._setup(db, _make_user())
        with patch("app.api.routers.doctor_router.get_health_record_for_patient",
                   new_callable=AsyncMock, return_value=None):
            response = await self._client.get(f"/api/doctors/health-records/{PATIENT_ID}")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["name"], "当前患者")
        response = await self._client.get(f"/api/doctors/patient-monitoring/{PATIENT_ID}")
        self.assertEqual(response.status_code, 200, response.text)

    async def test_revocation_applies_to_next_list_record_and_monitoring_request(self):
        db = FakeDatabase()
        db.users.insert({"_id": ObjectId(DOCTOR_ID), "role": "doctor", "patients": [PATIENT_ID]})
        patient_key = ObjectId(PATIENT_ID)
        db.users.insert({"_id": patient_key, "role": "patient", "practitioners": [ObjectId(DOCTOR_ID)]})
        self._setup(db, _make_user())
        with patch("app.api.routers.doctor_router.get_health_record_for_patient",
                   new_callable=AsyncMock, return_value=None):
            allowed = await self._client.get(f"/api/doctors/health-records/{PATIENT_ID}")
            self.assertEqual(allowed.status_code, 200, allowed.text)
            # 模拟患者侧移除已成功、旧医生侧兼容镜像尚未同步。
            db.users.docs[patient_key]["practitioners"] = []
            for endpoint in ["health-records", "patient-monitoring"]:
                denied = await self._client.get(f"/api/doctors/{endpoint}/{PATIENT_ID}")
                self.assertEqual(denied.status_code, 403, denied.text)
        listed = await self._client.get("/api/doctors/patients")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json(), [])


if __name__ == "__main__":
    unittest.main()
