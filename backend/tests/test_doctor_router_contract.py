"""医生路由诚实数据契约测试（2026-11-08 修复模拟患者与存根端点）。

覆盖 GET /api/doctors：
- /patients：空库/无关联患者如实返回空列表（绝不返回 mock_i 模拟患者）；
  数据库异常如实 500；命中数据返回真实患者。
- /statistics：真实聚合（患者数、康复计划状态分布）；未定义训练场次口径时不返回完成数，
  空库返回真实 0 而非存根空对象。
- /patient-monitoring/{id}：真实聚合快照（绑定设备数、康复计划状态分布）；
  患者不存在 404、不属于当前医生 403。

全部内存打桩 + FastAPI 依赖覆盖，不触碰真实数据库。
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
from bson import ObjectId

from app.core.auth import get_current_user
from app.api.dependencies import get_health_record_for_patient
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
                    if op == "$lte" and not (value is not None and value <= operand):
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
        self.docs = list(docs)
        # 分页路径调用记录：缺省路径必须完全不触碰（锁定「缺省=全量不排序」）
        self.sort_call = None
        self.skip_call = None
        self.limit_call = None

    def sort(self, key, direction=1):
        self.sort_call = (key, direction)
        self.docs = sorted(self.docs, key=lambda doc: doc.get(key) if doc.get(key) is not None else "")
        return self

    def skip(self, count):
        self.skip_call = count
        self.docs = self.docs[count:]
        return self

    def limit(self, count):
        self.limit_call = count
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
        self.find_one_error = None
        self.last_cursor = None

    async def find_one(self, filter_, *args, **kwargs):
        # canonical 路径的 require_canonical 会以 session=None 关键字调用
        if self.find_one_error is not None:
            raise self.find_one_error
        for doc in self.docs.values():
            if _match(doc, filter_):
                return dict(doc)
        return None

    def find(self, filter_, projection=None, **kwargs):
        if self.find_one_error is not None:
            raise self.find_one_error
        self.last_cursor = FakeCursor([doc for doc in self.docs.values() if _match(doc, filter_)])
        return self.last_cursor

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
        # 纯函数级用例（不经 HTTP）可不创建 _client
        if getattr(self, "_client", None) is not None:
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
        self.assertEqual(body["patientSelfReportsThisMonth"]["total"], 0)
        self.assertEqual(body["patientSelfReportsThisMonth"]["periodStart"].split("T")[0],
                         datetime.utcnow().strftime("%Y-%m-01"))

    async def test_seeded_statistics_aggregated(self):
        """命中数据：患者数和计划状态按真实集合聚合，不读取旧执行集合。"""
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
        # 旧集合即使有记录，也不再冒充新架构中的患者自报。
        db.rehab_progress.insert({"_id": "pg1", "patient_id": PATIENT_ID, "completed": True,
                                  "date": datetime.utcnow() - timedelta(days=1)})
        reports = db.rehab_execution_events
        reports.insert({"_id": "ev1", "patient_id": PATIENT_ID, "event_type": "patient_report",
                        "schema_version": 1, "source": "patient_self_report",
                        "execution_status": "completed", "performed_at": datetime.utcnow() - timedelta(days=1)})
        reports.insert({"_id": "ev2", "patient_id": PATIENT_ID, "event_type": "patient_report",
                        "schema_version": 1, "source": "patient_self_report",
                        "execution_status": "partial", "performed_at": datetime.utcnow()})
        reports.insert({"_id": "ev3", "patient_id": str(ObjectId()), "event_type": "patient_report",
                        "schema_version": 1, "source": "patient_self_report",
                        "execution_status": "completed", "performed_at": datetime.utcnow()})

        self._setup(db, _make_user())
        response = await self._client.get("/api/doctors/statistics")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["patientCount"], 2)
        self.assertEqual(body["rehabPlans"], {"total": 3, "active": 2, "completed": 1})
        self.assertEqual(body["patientSelfReportsThisMonth"]["total"], 2)
        self.assertEqual(body["patientSelfReportsThisMonth"]["completed"], 1)
        self.assertEqual(body["patientSelfReportsThisMonth"]["partial"], 1)
        self.assertEqual(body["patientSelfReportsThisMonth"]["not_done"], 0)

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
        """命中数据：绑定设备数和计划状态聚合，不把历史行当训练场次。"""
        db = FakeDatabase()
        self._seed_doctor(db)
        db.users.insert({"_id": ObjectId(PATIENT_ID), "role": "patient", "name": "张三", "practitioners": [DOCTOR_ID]})
        db.devices.insert({"_id": "dev1", "patient_id": PATIENT_ID, "status": "active"})
        db.devices.insert({"_id": "dev2", "patient_id": PATIENT_ID, "status": "inactive"})
        db.rehab_plans.insert({"_id": "r1", "patient_id": PATIENT_ID, "status": "active"})
        db.rehab_progress.insert({"_id": "pg1", "patient_id": PATIENT_ID, "completed": True,
                                  "date": datetime.utcnow() - timedelta(days=2)})

        self._setup(db, _make_user())
        response = await self._client.get(f"/api/doctors/patient-monitoring/{PATIENT_ID}")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["implemented"], True)
        self.assertEqual(body["patientId"], PATIENT_ID)
        self.assertEqual(body["boundDevices"], 2)
        self.assertEqual(body["rehabPlans"], {"total": 1, "active": 1, "completed": 0})
        self.assertNotIn("completedSessionsLast30Days", body)

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


class PatientReadAdapterContractTests(DoctorRouterContractTestBase):
    """患者读取收敛到 legacy 适配器后的防护契约（T2 第一波段）。

    - 医护患者列表/统计经 LegacyPatientRepository.assigned_ids，获得标识歧义防护
      （同一标识存在 ObjectId/字符串双文档时上抛 PATIENT_IDENTITY_AMBIGUOUS/503，
      不再静默重复列出）；
    - get_health_record_for_patient 不再 ObjectId-only 直查 users，
      与适配器一致支持 string/ObjectId 双字面。
    """

    def _seed_ambiguous_pair(self, db):
        # 同一患者标识的 ObjectId 与字符串双文档（历史双写形态）→ 歧义
        db.users.insert({"_id": ObjectId(DOCTOR_ID), "role": "doctor", "name": "医生"})
        db.users.insert({"_id": ObjectId(PATIENT_ID), "role": "patient",
                         "name": "患者A", "practitioners": [DOCTOR_ID]})
        db.users.insert({"_id": PATIENT_ID, "role": "patient",
                         "name": "患者B", "practitioners": [DOCTOR_ID]})

    async def test_ambiguous_patient_identity_on_list_returns_503(self):
        db = FakeDatabase()
        self._seed_ambiguous_pair(db)
        self._setup(db, _make_user())
        response = await self._client.get("/api/doctors/patients")
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["error"], "PATIENT_IDENTITY_AMBIGUOUS")

    async def test_ambiguous_patient_identity_on_statistics_returns_503(self):
        db = FakeDatabase()
        self._seed_ambiguous_pair(db)
        self._setup(db, _make_user())
        response = await self._client.get("/api/doctors/statistics")
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["error"], "PATIENT_IDENTITY_AMBIGUOUS")

    async def test_patient_list_shape_unchanged(self):
        """列表响应形状契约不变：id/name/age/gender/diagnosis/status 字段保持。"""
        db = FakeDatabase()
        db.users.insert({"_id": ObjectId(DOCTOR_ID), "role": "doctor", "name": "医生"})
        db.users.insert({"_id": ObjectId(PATIENT_ID), "role": "patient", "name": "张三",
                         "practitioners": [ObjectId(DOCTOR_ID)], "age": 40, "gender": "男",
                         "diagnosis": "腰椎间盘突出", "status": "在治疗",
                         "practitioners_extra": "不应出现在响应中"})
        self._setup(db, _make_user())
        response = await self._client.get("/api/doctors/patients")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [{
            "id": PATIENT_ID,
            "name": "张三",
            "age": 40,
            "gender": "男",
            "diagnosis": "腰椎间盘突出",
            "status": "在治疗",
        }])

    async def test_health_record_patient_load_supports_non_objectid_id(self):
        """get_health_record_for_patient 与适配器同源：非 ObjectId 字符串主键可命中。"""
        db = FakeDatabase()
        db.users.insert({"_id": "legacy-patient-001", "role": "patient", "name": "老患者",
                         "age": 55, "gender": "女"})
        record = await get_health_record_for_patient("legacy-patient-001", db)
        self.assertEqual(record["name"], "老患者")
        self.assertEqual(record["age"], 55)
        self.assertEqual(record["gender"], "女")


class DoctorPatientsPaginationContractTests(DoctorRouterContractTestBase):
    """T59 分页预适配契约（legacy 域）。

    - 缺省（不传 skip/limit）路径零行为变化：全量返回，游标不做 sort/skip/limit；
    - 显式分页生效：按 _id 升序翻页（加法式新路径）；
    - 参数越界统一 INVALID_PATIENT_PAGINATION/503（与 canonical 仓库语义一致）。
    """

    def _seed_patients(self, db, count):
        db.users.insert({"_id": ObjectId(DOCTOR_ID), "role": "doctor", "name": "医生"})
        ids = []
        for index in range(count):
            patient_id = ObjectId()
            ids.append(str(patient_id))
            db.users.insert({"_id": patient_id, "role": "patient",
                             "name": f"患者{index}", "practitioners": [ObjectId(DOCTOR_ID)]})
        return ids

    async def test_default_request_keeps_full_unsorted_behavior(self):
        """缺省请求：不排序、不跳页、不截断，游标保持原样。"""
        db = FakeDatabase()
        self._seed_patients(db, 5)
        self._setup(db, _make_user())
        response = await self._client.get("/api/doctors/patients")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()), 5)
        cursor = db.users.last_cursor
        self.assertIsNone(cursor.sort_call)
        self.assertIsNone(cursor.skip_call)
        self.assertIsNone(cursor.limit_call)

    async def test_explicit_pagination_applies_id_ascending_page(self):
        """显式 skip/limit：按 _id 升序返回对应页（legacy 分页新路径）。"""
        db = FakeDatabase()
        ids = self._seed_patients(db, 5)
        self._setup(db, _make_user())
        response = await self._client.get("/api/doctors/patients?skip=2&limit=2")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([item["id"] for item in response.json()], sorted(ids)[2:4])
        cursor = db.users.last_cursor
        self.assertEqual(cursor.sort_call, ("_id", 1))
        self.assertEqual(cursor.skip_call, 2)
        self.assertEqual(cursor.limit_call, 2)

    async def test_limit_only_page_is_sorted_and_capped(self):
        """仅传 limit：排序生效并截断前 limit 条。"""
        db = FakeDatabase()
        ids = self._seed_patients(db, 4)
        self._setup(db, _make_user())
        response = await self._client.get("/api/doctors/patients?limit=2")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([item["id"] for item in response.json()], sorted(ids)[:2])

    async def test_limit_boundary_200_accepted(self):
        """limit=200 为合法上界（与 canonical 仓库约束一致）。"""
        db = FakeDatabase()
        self._seed_patients(db, 3)
        self._setup(db, _make_user())
        response = await self._client.get("/api/doctors/patients?limit=200")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()), 3)

    async def test_invalid_pagination_returns_503_with_domain_code(self):
        """越界/非法分页参数：统一 INVALID_PATIENT_PAGINATION/503。"""
        db = FakeDatabase()
        self._seed_patients(db, 2)
        self._setup(db, _make_user())
        for params in ["limit=201", "limit=0", "limit=-1", "skip=-1"]:
            response = await self._client.get(f"/api/doctors/patients?{params}")
            self.assertEqual(response.status_code, 503, f"{params}: {response.text}")
            self.assertEqual(response.json()["error"], "INVALID_PATIENT_PAGINATION")


class DoctorPatientsCanonicalPaginationContractTests(DoctorRouterContractTestBase):
    """T59 canonical 语义映射契约。

    - 缺省请求映射 list_assigned 仓库级缺省：limit=100、按 patient_id 排序、
      仅 status=active，响应形状与 legacy 一致（id=patient_id）；
    - 显式分页映射 skip/limit；
    - 分页越界错误码与 legacy 一致；域状态异常 fail-closed 503。
    """

    CANONICAL_STATE = {"_id": "clinical-patients-v1", "mode": "canonical",
                       "schema_version": 1}

    def _seed_canonical(self, db, count, inactive=False):
        db.patient_domain_state.insert(dict(self.CANONICAL_STATE))
        db.users.insert({"_id": ObjectId(DOCTOR_ID), "role": "doctor", "name": "医生"})
        ids = []
        for index in range(count):
            patient_id = ObjectId()
            ids.append(str(patient_id))
            db.clinical_patients.insert({
                "_id": patient_id, "patient_id": str(patient_id),
                "name": f"患者{index}",
                "status": "inactive" if inactive and index == 0 else "active",
                "practitioners": [DOCTOR_ID],
                "demographic_info": {"age": 30 + index, "gender": "男"},
                "medical_info": {"diagnosis": f"诊断{index}"},
            })
        return ids

    async def test_canonical_default_maps_list_assigned_default(self):
        """缺省请求：canonical 下按 patient_id 排序、剔除 inactive、形状不变。"""
        db = FakeDatabase()
        ids = self._seed_canonical(db, 3)
        self._setup(db, _make_user())
        response = await self._client.get("/api/doctors/patients")
        self.assertEqual(response.status_code, 200, response.text)
        patients = response.json()
        self.assertEqual([item["id"] for item in patients], sorted(ids))
        self.assertEqual(patients[0], {
            "id": sorted(ids)[0], "name": "患者0", "age": 30,
            "gender": "男", "diagnosis": "诊断0", "status": "active"})
        cursor = db.clinical_patients.last_cursor
        self.assertEqual(cursor.sort_call, ("patient_id", 1))
        self.assertEqual(cursor.limit_call, 100)
        self.assertEqual(cursor.skip_call, 0)

    async def test_canonical_default_caps_at_repository_limit_100(self):
        """缺省请求在 canonical 域最多返回仓库缺省 100 条（域切换语义差异的锁定）。"""
        db = FakeDatabase()
        self._seed_canonical(db, 103)
        self._setup(db, _make_user())
        response = await self._client.get("/api/doctors/patients")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()), 100)

    async def test_canonical_explicit_pagination_maps_skip_limit(self):
        """显式 skip/limit：映射到 list_assigned 的分页语义。"""
        db = FakeDatabase()
        ids = self._seed_canonical(db, 5)
        self._setup(db, _make_user())
        response = await self._client.get("/api/doctors/patients?skip=1&limit=2")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([item["id"] for item in response.json()], sorted(ids)[1:3])

    async def test_canonical_inactive_patients_excluded(self):
        """canonical 仅返回 status=active（list_assigned 内建收窄）。"""
        db = FakeDatabase()
        ids = self._seed_canonical(db, 3, inactive=True)
        self._setup(db, _make_user())
        response = await self._client.get("/api/doctors/patients")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([item["id"] for item in response.json()],
                         sorted(ids)[1:])

    async def test_canonical_invalid_pagination_returns_same_code(self):
        """越界分页在 canonical 域与 legacy 同码：INVALID_PATIENT_PAGINATION/503。"""
        db = FakeDatabase()
        self._seed_canonical(db, 2)
        self._setup(db, _make_user())
        response = await self._client.get("/api/doctors/patients?limit=201")
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["error"], "INVALID_PATIENT_PAGINATION")

    async def test_canonical_unknown_domain_state_fails_closed_503(self):
        """域状态异常（未知 mode）：fail-closed 503，绝不静默回退 legacy。"""
        db = FakeDatabase()
        db.patient_domain_state.insert({"_id": "clinical-patients-v1",
                                        "mode": "migrating", "schema_version": 1})
        db.users.insert({"_id": ObjectId(DOCTOR_ID), "role": "doctor", "name": "医生"})
        self._setup(db, _make_user())
        response = await self._client.get("/api/doctors/patients")
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["error"], "PATIENT_DOMAIN_STATE_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
