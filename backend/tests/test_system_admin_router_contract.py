"""系统管理端路由契约测试（2026-11-08 去桩真实化）。

覆盖 /api/admin 前端实际消费的端点：
- GET /admin/patients、/admin/health-managers：users 按 role 真实查询，
  字段与前端 PatientManagement / HealthManagerManagement 页面消费结构对齐；
- GET /admin/doctors：空库返回 []，不再回退模拟数据（去 mock-doc 假数据）；
- GET /admin/organizations：organizations 集合真实查询；
- POST /admin/doctors、/admin/patients、/admin/health-managers：走
  user_service.create_user 真实落库（含密码哈希），邮箱冲突 409；
- GET/POST /admin/tags：真实空态、持久化、分类过滤、重复拒绝及权限；
- 非 admin 角色 403。

全部内存打桩 + FastAPI 依赖覆盖，不触碰真实数据库。
"""

import unittest
from datetime import datetime
from types import SimpleNamespace
from bson import ObjectId

import httpx

from app.core.auth import get_current_user
from app.db.mongodb import get_database
from app.main import app
from app.schemas.user import UserResponse

ADMIN_ID = str(ObjectId())
DOCTOR_ID = str(ObjectId())


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
                    str_set = {str(item) for item in operand}
                    if str(value) not in str_set:
                        return False
                elif op == "$ne":
                    if value == operand:
                        return False
                else:
                    if value != operand:
                        return False
            continue
        if value != cond and str(value) != str(cond):
            return False
    return True


class FakeCursor:
    def __init__(self, docs, filter_):
        self._docs = [d for d in docs if _match(d, filter_)]
        self._skip = 0
        self._limit = None

    def skip(self, n):
        self._skip = n
        return self

    def limit(self, n):
        self._limit = n
        return self

    def __aiter__(self):
        self._iterator = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration:
            raise StopAsyncIteration

    async def to_list(self, length=None):
        items = self._docs[self._skip:]
        if self._limit is not None:
            items = items[:self._limit]
        if length is not None:
            items = items[:length]
        return items


class FakeCollection:
    def __init__(self):
        self.docs = {}

    def find(self, filter_=None, projection=None, **kwargs):
        # 兼容 patient_identity.load_identity_groups 的 find(filter, projection, session=...) 调用
        return FakeCursor(list(self.docs.values()), filter_ or {})

    async def find_one(self, filter_):
        for doc in self.docs.values():
            if _match(doc, filter_):
                return doc
        return None

    async def insert_one(self, doc):
        doc = dict(doc)
        if "_id" not in doc:
            doc["_id"] = ObjectId()
        self.docs[doc["_id"]] = doc
        return SimpleNamespace(inserted_id=doc["_id"])

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

    async def command(self, *args, **kwargs):
        return {"ok": 1}

    async def list_collection_names(self):
        return list(self._collections.keys())


def _make_admin():
    return UserResponse(id=ADMIN_ID, email="admin@example.com", name="管理员",
                        role="admin", is_active=True,
                        createdAt=datetime.utcnow(), updatedAt=datetime.utcnow())


def _make_user(role, email):
    return UserResponse(id=str(ObjectId()), email=email, name=role,
                        role=role, is_active=True,
                        createdAt=datetime.utcnow(), updatedAt=datetime.utcnow())


class SystemAdminRouterContractTests(unittest.IsolatedAsyncioTestCase):
    def _setup(self, db, user=None):
        async def fake_current_user():
            return user or _make_admin()

        app.dependency_overrides[get_database] = lambda: db
        app.dependency_overrides[get_current_user] = fake_current_user
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://system-admin-router-test")

    async def asyncTearDown(self):
        await self._client.aclose()
        app.dependency_overrides.clear()

    # ---------- GET /admin/patients ----------

    async def test_patients_empty_db_returns_empty_list(self):
        self._setup(FakeDatabase())
        response = await self._client.get("/api/admin/patients")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [])

    async def test_patients_real_query_field_alignment(self):
        db = FakeDatabase()
        db.users.insert({
            "_id": ObjectId("651000000000000000000001"),
            "name": "患者甲", "email": "p1@example.com", "role": "patient",
            "is_active": True,
            "demographic_info": {"age": 58, "gender": "男",
                                 "contact_number": "13800000001",
                                 "address": "北京市朝阳区"},
            "medical_info": {"diagnosis": "脑卒中恢复期"},
            "practitioners": [DOCTOR_ID],
        })
        db.users.insert({
            "_id": ObjectId(DOCTOR_ID),
            "name": "治疗师乙", "email": "d1@example.com", "role": "doctor",
            "is_active": True,
        })
        db.users.insert({  # 非患者角色不得混入
            "_id": ObjectId("651000000000000000000002"),
            "name": "医生丙", "email": "d2@example.com", "role": "doctor",
            "is_active": True,
        })
        db.users.insert({  # 停用患者
            "_id": ObjectId("651000000000000000000003"),
            "name": "患者丁", "email": "p2@example.com", "role": "patient",
            "is_active": False,
        })

        self._setup(db)
        response = await self._client.get("/api/admin/patients")
        self.assertEqual(response.status_code, 200, response.text)
        rows = response.json()
        self.assertEqual(len(rows), 2)

        active = next(r for r in rows if r["name"] == "患者甲")
        self.assertEqual(active["id"], "651000000000000000000001")
        self.assertEqual(active["age"], 58)
        self.assertEqual(active["gender"], "男")
        self.assertEqual(active["contact_number"], "13800000001")
        self.assertEqual(active["address"], "北京市朝阳区")
        self.assertEqual(active["diagnosis"], "脑卒中恢复期")
        self.assertEqual(active["doctor_assigned"], "治疗师乙")
        self.assertEqual(active["email"], "p1@example.com")
        self.assertEqual(active["status"], "正常")
        # users 集合无治疗方案/入院日期数据源，如实留空
        self.assertEqual(active["treatment_plan"], "")
        self.assertEqual(active["admission_date"], "")

        inactive = next(r for r in rows if r["name"] == "患者丁")
        self.assertEqual(inactive["status"], "停用")
        self.assertEqual(inactive["doctor_assigned"], "")

    async def test_patients_response_shape_locked(self):
        """响应字段集合锁死：前端 PatientManagement 消费结构不变（T18 收敛后仍保持）。"""
        db = FakeDatabase()
        db.users.insert({
            "_id": ObjectId("651000000000000000000004"),
            "name": "患者戊", "email": "p3@example.com", "role": "patient",
        })
        self._setup(db)
        response = await self._client.get("/api/admin/patients")
        self.assertEqual(response.status_code, 200, response.text)
        rows = response.json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0].keys()), {
            "id", "name", "age", "gender", "contact_number", "email",
            "address", "diagnosis", "doctor_assigned",
            "treatment_plan", "admission_date", "status",
        })

    async def test_patients_pagination_skip_limit(self):
        """分页语义保持不变：skip 跳过、limit 截断页内文档。"""
        db = FakeDatabase()
        for i in range(3):
            db.users.insert({
                "_id": ObjectId(f"65100000000000000000001{i}"),
                "name": f"患者{i}", "role": "patient",
            })
        self._setup(db)
        response = await self._client.get("/api/admin/patients", params={"skip": 1, "limit": 1})
        self.assertEqual(response.status_code, 200, response.text)
        rows = response.json()
        self.assertEqual([r["name"] for r in rows], ["患者1"])

    async def test_patients_ambiguous_identity_returns_503(self):
        """同一患者标识 ObjectId/字符串双文档：load_identity_groups 口径
        上抛 LegacyPatientIdentityError（PATIENT_IDENTITY_AMBIGUOUS/503），
        不得被 except Exception 降级为 500。"""
        db = FakeDatabase()
        db.users.insert({"_id": ObjectId("651000000000000000000005"), "role": "patient",
                         "name": "患者A"})
        db.users.insert({"_id": "651000000000000000000005", "role": "patient",
                         "name": "患者B"})
        self._setup(db)
        response = await self._client.get("/api/admin/patients")
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["error"], "PATIENT_IDENTITY_AMBIGUOUS")

    async def test_patients_non_admin_forbidden(self):
        self._setup(FakeDatabase(), _make_user("doctor", "doc@example.com"))
        response = await self._client.get("/api/admin/patients")
        self.assertEqual(response.status_code, 403, response.text)

    # ---------- GET /admin/health-managers ----------

    async def test_health_managers_empty_db_returns_empty_list(self):
        self._setup(FakeDatabase())
        response = await self._client.get("/api/admin/health-managers")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [])

    async def test_health_managers_real_query_field_alignment(self):
        db = FakeDatabase()
        db.users.insert({
            "_id": ObjectId("651000000000000000000011"),
            "name": "健管师甲", "email": "hm1@example.com",
            "role": "health_manager", "is_active": True,
            "certification": "健康管理师一级",
            "specialty_areas": ["慢病管理", "运动康复"],
            "department": "康复管理科",
            "patients": [str(ObjectId()), str(ObjectId())],
            "created_at": datetime(2024, 3, 5, 10, 0, 0),
        })
        self._setup(db)
        response = await self._client.get("/api/admin/health-managers")
        self.assertEqual(response.status_code, 200, response.text)
        rows = response.json()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["id"], "651000000000000000000011")
        self.assertEqual(row["name"], "健管师甲")
        self.assertEqual(row["title"], "健康管理师一级")
        self.assertEqual(row["specialty"], "慢病管理、运动康复")
        self.assertEqual(row["department"], "康复管理科")
        self.assertEqual(row["patients"], 2)
        self.assertEqual(row["status"], "在职")
        self.assertEqual(row["join_date"], "2024-03-05")

    async def test_health_managers_non_admin_forbidden(self):
        self._setup(FakeDatabase(), _make_user("patient", "p@example.com"))
        response = await self._client.get("/api/admin/health-managers")
        self.assertEqual(response.status_code, 403, response.text)

    # ---------- GET /admin/doctors ----------

    async def test_doctors_empty_db_returns_empty_not_mock(self):
        """空库返回 []，不再回退 mock-doc 模拟数据。"""
        self._setup(FakeDatabase())
        response = await self._client.get("/api/admin/doctors")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body, [])
        self.assertNotIn("mock-doc-001", response.text)

    async def test_doctors_non_admin_forbidden(self):
        """恢复管理员守卫（原实现为便于调试完全移除了权限检查）。"""
        self._setup(FakeDatabase(), _make_user("patient", "p@example.com"))
        response = await self._client.get("/api/admin/doctors")
        self.assertEqual(response.status_code, 403, response.text)

    # ---------- POST /admin/doctors ----------

    async def test_create_doctor_persists_with_hashed_password(self):
        db = FakeDatabase()
        self._setup(db)
        response = await self._client.post("/api/admin/doctors", json={
            "name": "新医生", "email": "newdoc@example.com",
            "password": "s3cret-pass", "role": "doctor",
            "department": "康复科", "specialty": "神经康复",
        })
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["role"], "doctor")
        self.assertEqual(body["email"], "newdoc@example.com")
        self.assertTrue(body["id"])

        stored = await db.users.find_one({"email": "newdoc@example.com"})
        self.assertIsNotNone(stored, "医生账号应真实落库 users 集合")
        self.assertTrue(stored.get("hashed_password"))
        self.assertNotEqual(stored["hashed_password"], "s3cret-pass")
        self.assertNotIn("password", stored)

    async def test_create_doctor_duplicate_email_conflict(self):
        db = FakeDatabase()
        db.users.insert({"_id": ObjectId(), "name": "已有医生",
                         "email": "dup@example.com", "role": "doctor"})
        self._setup(db)
        response = await self._client.post("/api/admin/doctors", json={
            "name": "重复医生", "email": "dup@example.com",
            "password": "s3cret-pass", "role": "doctor",
        })
        self.assertEqual(response.status_code, 409, response.text)

    async def test_create_doctor_non_admin_forbidden(self):
        self._setup(FakeDatabase(), _make_user("health_manager", "hm@example.com"))
        response = await self._client.post("/api/admin/doctors", json={
            "name": "x", "email": "x@example.com",
            "password": "s3cret-pass", "role": "doctor",
        })
        self.assertEqual(response.status_code, 403, response.text)

    # ---------- POST /admin/patients ----------

    async def test_create_patient_persists_and_listable(self):
        db = FakeDatabase()
        self._setup(db)
        response = await self._client.post("/api/admin/patients", json={
            "name": "新患者", "email": "newp@example.com",
            "password": "s3cret-pass", "role": "patient",
            "demographic_info": {"age": 40, "gender": "女"},
        })
        self.assertEqual(response.status_code, 201, response.text)

        listed = await self._client.get("/api/admin/patients")
        self.assertEqual(listed.status_code, 200, listed.text)
        rows = listed.json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "新患者")
        self.assertEqual(rows[0]["age"], 40)

        stored = await db.users.find_one({"email": "newp@example.com"})
        self.assertIsNotNone(stored)
        self.assertTrue(stored.get("hashed_password"))

    # ---------- POST /admin/health-managers ----------

    async def test_create_health_manager_persists(self):
        db = FakeDatabase()
        self._setup(db)
        response = await self._client.post("/api/admin/health-managers", json={
            "name": "新健管师", "email": "newhm@example.com",
            "password": "s3cret-pass", "role": "health_manager",
            "specialty_areas": ["慢病管理"],
        })
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["role"], "health_manager")

        stored = await db.users.find_one({"email": "newhm@example.com"})
        self.assertIsNotNone(stored)
        self.assertTrue(stored.get("hashed_password"))

    # ---------- GET/POST /admin/organizations ----------

    async def test_organizations_empty_db_returns_empty_list(self):
        self._setup(FakeDatabase())
        response = await self._client.get("/api/admin/organizations")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [])

    async def test_organizations_real_query_field_alignment(self):
        db = FakeDatabase()
        db.organizations.insert({
            "_id": ObjectId("651000000000000000000021"),
            "name": "康复医院", "type": "hospital",
            "address": {"detail": "幸福路 100 号"},
            "contact_info": {"person": "王主任", "phone": "13900000001"},
            "active": True,
        })
        db.organizations.insert({
            "_id": ObjectId("651000000000000000000022"),
            "name": "停用诊所", "type": "clinic", "active": False,
        })
        self._setup(db)
        response = await self._client.get("/api/admin/organizations")
        self.assertEqual(response.status_code, 200, response.text)
        rows = response.json()
        self.assertEqual(len(rows), 2)
        active = next(r for r in rows if r["name"] == "康复医院")
        self.assertEqual(active["address"], "幸福路 100 号")
        self.assertEqual(active["contact_person"], "王主任")
        self.assertEqual(active["contact_phone"], "13900000001")
        self.assertEqual(active["status"], "active")
        inactive = next(r for r in rows if r["name"] == "停用诊所")
        self.assertEqual(inactive["status"], "inactive")

    async def test_create_organization_persists(self):
        db = FakeDatabase()
        self._setup(db)
        response = await self._client.post("/api/admin/organizations", json={
            "name": "新机构", "type": "clinic",
            "contact_info": {"person": "李干事", "phone": "13700000001"},
        })
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["name"], "新机构")
        self.assertEqual(body["contact_person"], "李干事")

        listed = await self._client.get("/api/admin/organizations")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(len(listed.json()), 1)

    async def test_organizations_non_admin_forbidden(self):
        self._setup(FakeDatabase(), _make_user("doctor", "d@example.com"))
        response = await self._client.get("/api/admin/organizations")
        self.assertEqual(response.status_code, 403, response.text)

    # ---------- GET/POST /admin/tags ----------

    async def test_tags_empty_db_returns_empty_list(self):
        self._setup(FakeDatabase())
        response = await self._client.get("/api/admin/tags")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [])

    async def test_create_tag_persists_and_filters_category(self):
        db = FakeDatabase()
        self._setup(db)
        payload = {"name": " 步行 ", "category": " 康复 ", "color": "#112233"}
        response = await self._client.post("/api/admin/tags", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        tag = response.json()
        self.assertTrue(ObjectId.is_valid(tag["id"]))
        self.assertEqual(tag["name"], "步行")
        self.assertEqual(tag["category"], "康复")
        self.assertEqual(tag["color"], "#112233")
        self.assertIn(ObjectId(tag["id"]), db.tags.docs)
        listed = await self._client.get("/api/admin/tags", params={"category": "康复"})
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json(), [tag])
        other = await self._client.get("/api/admin/tags", params={"category": "其他"})
        self.assertEqual(other.status_code, 200, other.text)
        self.assertEqual(other.json(), [])
        duplicate = await self._client.post("/api/admin/tags", json=payload)
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        self.assertEqual(len(db.tags.docs), 1)

    async def test_invalid_tag_is_not_persisted(self):
        db = FakeDatabase()
        self._setup(db)
        response = await self._client.post("/api/admin/tags", json={"name": " ", "category": "康复"})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(db.tags.docs, {})

    async def test_tags_non_admin_forbidden(self):
        db = FakeDatabase()
        self._setup(db, _make_user("doctor", "doctor@example.com"))
        responses = [
            await self._client.get("/api/admin/tags"),
            await self._client.post("/api/admin/tags", json={"name": "步行", "category": "康复"}),
            await self._client.delete(f"/api/admin/tags/{ObjectId()}"),
        ]
        for response in responses:
            self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(db.tags.docs, {})


if __name__ == "__main__":
    unittest.main()
