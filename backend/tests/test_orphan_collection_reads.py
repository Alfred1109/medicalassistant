"""孤儿读集合引用契约测试（BASE03 后续，2026-11-08）。

覆盖两个无写入方的孤儿集合读取（处置方式 b：不猜映射，锁定空安全行为）：

1. analytics_service.AnalyticsService 读 rehabilitation_records
   （期望形状：数值型 duration 的训练记录；消费端点 GET /api/system/visualization/overview
   的 avgTrainingTime 指标）：
   - 空集合 -> 端点 200，avgTrainingTime = 0（且不是异常回退的模拟数据）；
   - 命中数据 -> 按含 duration 的文档正确求平均，缺 duration 的文档跳过。

2. report_scheduler_service.ReportSchedulerService 读 rehabilitation_sessions
   （期望形状：created_at + duration + score 的逐次训练记录；仅被后台报表调度
   _get_chart_data("rehabilitation") 消费，无直接 HTTP 端点）：
   - 空集合 -> 返回 []；
   - 命中数据 -> 按天分组，count / avgDuration / avgScore 聚合正确。

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
    """analytics_service 对孤儿集合 rehabilitation_records 的读取契约。"""

    def _service(self, db):
        return AnalyticsService(db)

    async def test_empty_collections_overview_is_zero_not_mock_fallback(self):
        """空库：各计数为 0、avgTrainingTime 为 0；不得落入 except 的模拟数据回退
        （回退字典 patientCount=1248，一旦命中即与本断言冲突）。"""
        db = FakeDatabase()
        stats = await self._service(db).get_stats_overview()

        self.assertEqual(stats["patientCount"], 0)
        self.assertEqual(stats["doctorCount"], 0)
        self.assertEqual(stats["totalDevices"], 0)
        self.assertEqual(stats["avgTrainingTime"], 0)

    async def test_seeded_durations_average_correctly(self):
        """命中数据：仅统计含数值 duration 的文档，缺 duration 的文档跳过。"""
        db = FakeDatabase()
        records = db.rehabilitation_records
        records.insert({"_id": "r1", "duration": 10})
        records.insert({"_id": "r2", "duration": 20})
        records.insert({"_id": "r3", "duration": 30})
        records.insert({"_id": "r4", "other_field": 999})  # 缺 duration，应跳过

        stats = await self._service(db).get_stats_overview()
        self.assertEqual(stats["avgTrainingTime"], 20.0)

    async def test_overview_endpoint_returns_200_on_empty_db(self):
        """端点契约：空库下 GET /api/system/visualization/overview 返回 200 空统计。"""
        db = FakeDatabase()
        app.dependency_overrides[get_database] = lambda: db
        get_user_mock = AsyncMock(return_value=_make_doctor())
        lookup = patch.object(UserService, "get_user_by_id", new=get_user_mock)
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
            # 空库真实路径：0 计数 + 0 平均训练时长（而非异常回退模拟数据）
            self.assertEqual(body["data"]["patientCount"], 0)
            self.assertEqual(body["data"]["avgTrainingTime"], 0)
        finally:
            await client.aclose()
            lookup.stop()
            app.dependency_overrides.clear()


class ReportSchedulerOrphanReadTests(unittest.IsolatedAsyncioTestCase):
    """report_scheduler_service 对孤儿集合 rehabilitation_sessions 的读取契约。"""

    def _service(self, db):
        service = ReportSchedulerService()
        service.db = db  # 绕过 start()，直接注入打桩库
        return service

    async def test_empty_sessions_return_empty_list(self):
        """空库：聚合无输出，安全返回 []（调度不报错、报表图表为空）。"""
        db = FakeDatabase()
        result = await self._service(db)._get_rehabilitation_stats(30)
        self.assertEqual(result, [])

    async def test_seeded_sessions_aggregate_by_day(self):
        """命中数据：按天分组，count / avgDuration / avgScore 聚合正确，
        窗口外（created_at 早于 start_date）的文档不计入。"""
        db = FakeDatabase()
        sessions = db.rehabilitation_sessions
        now = datetime.utcnow()
        day_a = now.replace(hour=10, minute=0, second=0, microsecond=0)
        day_b = day_a - timedelta(days=1)
        old = now - timedelta(days=60)  # 30 天窗口之外

        sessions.insert({"_id": "s1", "created_at": day_a, "duration": 10, "score": 60})
        sessions.insert({"_id": "s2", "created_at": day_a, "duration": 30, "score": 80})
        sessions.insert({"_id": "s3", "created_at": day_b, "duration": 20, "score": 100})
        sessions.insert({"_id": "s4", "created_at": old, "duration": 999, "score": 0})

        result = await self._service(db)._get_rehabilitation_stats(30)

        self.assertEqual(len(result), 2)
        by_date = {row["date"]: row for row in result}
        day_a_key = day_a.strftime("%Y-%m-%d")
        day_b_key = day_b.strftime("%Y-%m-%d")
        self.assertEqual(by_date[day_a_key]["count"], 2)
        self.assertEqual(by_date[day_a_key]["avgDuration"], 20.0)
        self.assertEqual(by_date[day_a_key]["avgScore"], 70.0)
        self.assertEqual(by_date[day_b_key]["count"], 1)
        self.assertEqual(by_date[day_b_key]["avgDuration"], 20.0)
        self.assertEqual(by_date[day_b_key]["avgScore"], 100.0)
        # 按日期升序
        self.assertEqual([row["date"] for row in result], [day_b_key, day_a_key])

    async def test_chart_data_dispatch_for_rehabilitation_type(self):
        """消费链路：_get_chart_data(data_type='rehabilitation') 走孤儿读并透传结果。"""
        db = FakeDatabase()
        service = self._service(db)
        db.rehabilitation_sessions.insert(
            {"_id": "s1", "created_at": datetime.utcnow(), "duration": 15, "score": 88})

        result = await service._get_chart_data("bar", "rehabilitation", "month")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["count"], 1)
        self.assertEqual(result[0]["avgDuration"], 15.0)
        self.assertEqual(result[0]["avgScore"], 88.0)


if __name__ == "__main__":
    unittest.main()
