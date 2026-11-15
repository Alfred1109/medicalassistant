"""孤儿读集合引用契约测试（BASE03 后续，2026-11-08）。

覆盖两个无写入方的孤儿集合读取（处置方式 b：不猜映射，锁定空安全行为）：

1. analytics_service 不再读取无写入方的 rehabilitation_records，
   avgTrainingTime 返回 None 并用 dataAvailable 标记不可用。

2. report_scheduler_service 对 rehabilitation 图表不再读取无写入方的
   rehabilitation_sessions，旧图表类型返回空序列。

全部内存打桩，不触碰真实数据库。映射决策本身是业务决策项，不在本测试中固化。
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
from bson import ObjectId
from jose import jwt

from app.core.config import settings
from app.db.mongodb import get_database
from app.main import app
from app.schemas.user import UserResponse
from app.services.analytics_service import AnalyticsService
from app.services.report_scheduler_service import ReportSchedulerService
from app.services.user_service import UserService

DOCTOR_ID = str(ObjectId())


def _match(doc, filter_):
    """支持测试所需的最小 $match / count_documents 过滤语义。"""
    for key, cond in filter_.items():
        value = doc.get(key)
        if isinstance(cond, dict):
            for op, operand in cond.items():
                if op == "$lt" and not value < operand:
                    return False
                if op == "$lte" and not value <= operand:
                    return False
                if op == "$gte" and not value >= operand:
                    return False
                if op == "$gt" and not value > operand:
                    return False
                if op == "$in" and value not in operand:
                    return False
            continue
        if value != cond:
            return False
    return True


class FakeCollection:
    """最小化 AsyncIOMotorCollection 打桩：内存字典存储。"""

    def __init__(self):
        self.docs = {}

    async def count_documents(self, filter_):
        return sum(1 for doc in self.docs.values() if _match(doc, filter_))

    async def find_one(self, query=None, session=None):
        """单点读取打桩（本套件用于 patient_domain_state 域开关读取；
        无状态文档 -> legacy，与 patients/repository.domain_mode 同语义）。"""
        for doc in self.docs.values():
            if _match(doc, query or {}):
                return dict(doc)
        return None

    def find(self, _filter, projection=None):
        self._cursor = iter(list(self.docs.values()))
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._cursor)
        except StopIteration:
            raise StopAsyncIteration

    def insert(self, doc):
        """测试播种辅助：直接写入一份文档（拷贝）。"""
        self.docs[doc["_id"]] = dict(doc)

    def aggregate(self, pipeline):
        """最小聚合执行器：仅支持本仓库孤儿读用到的 $match/$group/$sort。

        $group 支持 _id 的 $dateToString 与 $sum/$avg 累加器（常量 1 或字段引用）。
        其余操作符一律抛错，避免打桩悄悄偏离真实聚合语义。
        """
        docs = list(self.docs.values())
        for stage in pipeline:
            if set(stage) != {"$match"} and set(stage) != {"$group"} \
                    and set(stage) != {"$sort"}:
                raise AssertionError(f"打桩聚合不支持该阶段: {stage}")
            if "$match" in stage:
                docs = [d for d in docs if _match(d, stage["$match"])]
            elif "$group" in stage:
                spec = stage["$group"]
                grouped = {}
                for d in docs:
                    id_spec = spec["_id"]
                    if "$dateToString" in id_spec:
                        date = d[id_spec["$dateToString"]["date"].lstrip("$")]
                        key = date.strftime(id_spec["$dateToString"]["format"])
                    else:
                        raise AssertionError("打桩聚合仅支持 $dateToString 分组键")
                    grouped.setdefault(key, []).append(d)
                out = []
                for key, group in grouped.items():
                    row = {"_id": key}
                    for field, acc in spec.items():
                        if field == "_id":
                            continue
                        (op, operand), = acc.items()
                        if op == "$sum":
                            if operand == 1:
                                row[field] = len(group)
                            else:
                                row[field] = sum(
                                    g[operand.lstrip("$")] for g in group)
                        elif op == "$avg":
                            vals = [g[operand.lstrip("$")] for g in group]
                            row[field] = sum(vals) / len(vals) if vals else None
                        else:
                            raise AssertionError(f"打桩聚合不支持累加器: {op}")
                    out.append(row)
                docs = out
            elif "$sort" in stage:
                (key, direction), = stage["$sort"].items()
                docs.sort(key=lambda d: d[key], reverse=direction < 0)
        self._cursor = iter(docs)
        return self


class FakeDatabase:
    """按属性访问惰性创建集合（db.users / db.devices / ...）。"""

    def __init__(self):
        self._collections = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._collections.setdefault(name, FakeCollection())

    def __getitem__(self, name):
        return getattr(self, name)


def _make_doctor():
    return UserResponse(id=DOCTOR_ID, email="doctor@example.com", name="合成医生",
                        role="doctor", is_active=True,
                        createdAt=datetime.utcnow(), updatedAt=datetime.utcnow())


class AnalyticsOrphanReadTests(unittest.IsolatedAsyncioTestCase):
    """analytics_service 对无来源训练时长的不可用契约。"""

    def _service(self, db):
        return AnalyticsService(db)

    async def test_empty_collections_overview_is_zero_not_mock_fallback(self):
        """空库：无来源训练时长为 None 且标记不可用，其他计数如实为 0。"""
        db = FakeDatabase()
        stats = await self._service(db).get_stats_overview()

        self.assertEqual(stats["patientCount"], 0)
        self.assertEqual(stats["doctorCount"], 0)
        self.assertEqual(stats["totalDevices"], 0)
        self.assertIsNone(stats["avgTrainingTime"])
        self.assertFalse(stats["dataAvailable"]["avgTrainingTime"])
        self.assertNotIn("rehabilitation_records", db._collections)

    async def test_overview_endpoint_returns_200_on_empty_db(self):
        """端点契约：空库下 GET /api/system/visualization/overview 返回 200 空统计。"""
        db = FakeDatabase()
        app.dependency_overrides[get_database] = lambda: db
        get_user_mock = AsyncMock(return_value=_make_doctor())
        lookup = patch("app.core.user_record.load_user_response", new=get_user_mock)
        lookup.start()
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://orphan-read-test")
        try:
            token = jwt.encode(
                {"sub": DOCTOR_ID, "token_type": "access",
                 "exp": datetime.utcnow() + timedelta(minutes=5)},
                settings.SECRET_KEY, algorithm=settings.ALGORITHM)
            response = await client.get(
                "/api/system/visualization/overview",
                headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertEqual(body["status"], "success")
            # 无来源的时长必须明确不可用，不能伪装为 0 分钟。
            self.assertEqual(body["data"]["patientCount"], 0)
            self.assertIsNone(body["data"]["avgTrainingTime"])
            self.assertFalse(body["data"]["dataAvailable"]["avgTrainingTime"])
        finally:
            await client.aclose()
            lookup.stop()
            app.dependency_overrides.clear()


class ReportSchedulerOrphanReadTests(unittest.IsolatedAsyncioTestCase):
    """旧康复报表类型不再读取 rehabilitation_sessions。"""

    def _service(self, db):
        service = ReportSchedulerService()
        service.db = db  # 直接注入打桩库（T53 后已无 start() 生命周期）
        return service

    async def test_rehabilitation_chart_does_not_read_legacy_collection(self):
        """旧图表未接入新执行事件模型前，不再假装生成训练汇总。"""
        db = FakeDatabase()
        service = self._service(db)
        result = await service._get_chart_data("bar", "rehabilitation", "month")
        self.assertEqual(result, [])
        self.assertNotIn("rehabilitation_sessions", db._collections)


class ReportSchedulerPatientDomainTests(unittest.IsolatedAsyncioTestCase):
    """T66：report_scheduler._get_patient_stats 患者聚合源按域分派。

    该执行链当前无调度入口（T53 死代码处置），但作为登记的潜在复用件
    一并随患者域波次换源：legacy（users + role）逐字等价；canonical
    （clinical_patients + status=="active"，含无账号患者）；unknown 不猜
    测域，fail-safe 返回空序列。
    """

    def _service(self, db):
        service = ReportSchedulerService()
        service.db = db
        return service

    def _seed_state(self, db, mode):
        from app.patients.repository import SCHEMA_VERSION, STATE_ID
        db.patient_domain_state.insert(
            {"_id": STATE_ID, "mode": mode, "schema_version": SCHEMA_VERSION})

    async def test_no_state_reads_users_like_before(self):
        """无状态文档：legacy 口径不变（users + role=="patient"）。"""
        db = FakeDatabase()
        db.users.insert({"_id": "p1", "role": "patient", "created_at": datetime.utcnow()})
        db.users.insert({"_id": "d1", "role": "doctor", "created_at": datetime.utcnow()})

        rows = await self._service(db)._get_patient_stats(30)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["value"], 1)

    async def test_canonical_reads_clinical_patients_including_accountless(self):
        """canonical：clinical_patients + status=="active"，无账号患者计入，
        users 里的患者账号同文档不计入。"""
        db = FakeDatabase()
        self._seed_state(db, "canonical")
        now = datetime.utcnow()
        db.clinical_patients.insert({"_id": "cp1", "patient_id": "cp1", "status": "active",
                                     "created_at": now})
        db.clinical_patients.insert({"_id": "cp2", "patient_id": "cp2", "status": "active",
                                     "created_at": now - timedelta(days=40)})
        db.clinical_patients.insert({"_id": "cp3", "patient_id": "cp3", "status": "inactive",
                                     "created_at": now})
        db.users.insert({"_id": "u1", "role": "patient", "created_at": now})

        rows = await self._service(db)._get_patient_stats(30)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["value"], 1)  # 30 天窗口内仅 cp1

    async def test_unknown_domain_returns_empty_not_guess(self):
        """unknown：域状态读取失败不猜测域，fail-safe 返回 []。"""
        db = FakeDatabase()
        db.users.insert({"_id": "p1", "role": "patient", "created_at": datetime.utcnow()})
        # Simulate 域开关读取失败：find_one 未实现/抛错均降级 unknown
        async def broken_find_one(query=None, session=None):
            raise RuntimeError("state read down")
        db.patient_domain_state.find_one = broken_find_one

        rows = await self._service(db)._get_patient_stats(30)
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
