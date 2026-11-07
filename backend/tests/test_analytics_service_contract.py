"""分析服务诚实数据契约测试（2026-11-08 修复随机模拟数据）。

覆盖 analytics_service.AnalyticsService：
- get_stats_overview：空库全 0 且不落异常回退模拟数据；硬编码 68/92 移除，
  rehabilitationRate/patientSatisfaction 恒 0 并带 dataAvailable:false 标记；
  异常如实上抛（不再回退 patientCount=1248 等模拟概览）。
- get_trend_data：按 created_at 新增数量真实聚合（users/devices/rehab_plans），
  桶补 0，缺 created_at/字符串日期不计入；未知 data_type/time_range 返回 []。
- get_distribution_data：按真实字段分组计数（department/device_type/status/
  demographic_info.gender），缺失归"未填写"；未知 data_type 返回 []。
- get_comparison_data：当前窗口 vs 对比窗口新增数量；target 无数据源返回
  compareValue=None；未知 compare_with 上抛。

全部内存打桩，不触碰真实数据库。
"""

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services.analytics_service import AnalyticsService


# ---------------------------------------------------------------------------
# 内存版 Mongo 桩：仅实现本服务用到的最小查询/聚合能力
# ---------------------------------------------------------------------------

def _get_path(doc, path):
    cur = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _match(doc, filter_):
    """支持相等匹配与 $lt/$lte/$gte/$gt/$in/$type(date) 操作符。"""
    for key, cond in filter_.items():
        value = _get_path(doc, key)
        if isinstance(cond, dict) and any(op.startswith("$") for op in cond):
            for op, operand in cond.items():
                try:
                    if op == "$lt" and not (value is not None and value < operand):
                        return False
                    if op == "$lte" and not (value is not None and value <= operand):
                        return False
                    if op == "$gte" and not (value is not None and value >= operand):
                        return False
                    if op == "$gt" and not (value is not None and value > operand):
                        return False
                except TypeError:
                    # 与 Mongo 类型括号语义一致：类型不匹配（如字符串日期 vs datetime）不命中
                    return False
                if op == "$in" and value not in operand:
                    return False
                if op == "$type" and operand == "date" and not isinstance(value, datetime):
                    return False
            continue
        if value != cond and str(value) != str(cond):
            return False
    return True


class _AggregateCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, length=None):
        return list(self._docs)


class FakeCollection:
    """最小化 AsyncIOMotorCollection 打桩：内存字典存储。"""

    def __init__(self):
        self.docs = {}
        self.count_error = None

    async def count_documents(self, filter_):
        if self.count_error is not None:
            raise self.count_error
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

    def aggregate(self, pipeline):
        docs = list(self.docs.values())
        for stage in pipeline:
            (op, spec), = stage.items()
            if op == "$match":
                docs = [d for d in docs if _match(d, spec)]
            elif op == "$group":
                docs = self._group(docs, spec)
            elif op == "$sort":
                (key, direction), = spec.items()
                docs.sort(key=lambda d: d[key], reverse=direction < 0)
            else:
                raise AssertionError(f"打桩聚合不支持该阶段: {op}")
        return _AggregateCursor(docs)

    @staticmethod
    def _group(docs, spec):
        id_spec = spec["_id"]
        grouped = {}
        if "$dateToString" in id_spec:
            sub = id_spec["$dateToString"]
            for d in docs:
                date_val = _get_path(d, sub["date"].lstrip("$"))
                if not isinstance(date_val, datetime):
                    raise AssertionError("打桩仅支持日期类型 $dateToString 分组键")
                grouped.setdefault(date_val.strftime(sub["format"]), []).append(d)
        elif "$ifNull" in id_spec:
            field, fallback = id_spec["$ifNull"]
            for d in docs:
                val = _get_path(d, field.lstrip("$"))
                key = fallback if (val is None or val == "") else val
                grouped.setdefault(key, []).append(d)
        else:
            raise AssertionError("打桩聚合仅支持 $dateToString / $ifNull 分组键")
        out = []
        for key, group in grouped.items():
            row = {"_id": key}
            for field, acc in spec.items():
                if field == "_id":
                    continue
                (acc_op, operand), = acc.items()
                if acc_op != "$sum" or operand != 1:
                    raise AssertionError(f"打桩聚合仅支持 $sum:1 累加器: {acc_op}")
                row[field] = len(group)
            out.append(row)
        return out

    def insert(self, doc):
        """测试播种辅助：直接写入一份文档（拷贝）。"""
        self.docs[doc["_id"]] = dict(doc)


class FakeDatabase:
    """按属性/键访问惰性创建集合（db.users / db.devices / ...）。"""

    def __init__(self):
        self._collections = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._collections.setdefault(name, FakeCollection())

    def __getitem__(self, name):
        return getattr(self, name)


def _service(db):
    return AnalyticsService(db)


class StatsOverviewContractTests(unittest.IsolatedAsyncioTestCase):
    """get_stats_overview：真实聚合 + 无数据源指标显式标记，异常如实上抛。"""

    async def test_empty_db_returns_real_zeros_not_mock(self):
        """空库：真实计数为 0；不得出现模拟概览回退值（patientCount=1248 等）。"""
        stats = await _service(FakeDatabase()).get_stats_overview()
        self.assertEqual(stats["patientCount"], 0)
        self.assertEqual(stats["doctorCount"], 0)
        self.assertEqual(stats["totalDevices"], 0)
        self.assertEqual(stats["activeDeviceRate"], 0)
        self.assertEqual(stats["weekPatientChange"], 0)
        self.assertEqual(stats["avgTrainingTime"], 0)
        self.assertNotEqual(stats, {
            "patientCount": 1248, "weekPatientChange": 4.2, "doctorCount": 86,
            "totalDevices": 152, "activeDeviceRate": 82, "avgTrainingTime": 45,
            "rehabilitationRate": 68, "patientSatisfaction": 92})

    async def test_no_source_metrics_are_zero_with_unavailable_flag(self):
        """无数据源的康复有效率/患者满意度：恒 0 并带 dataAvailable:false，
        不再是硬编码 68/92。"""
        stats = await _service(FakeDatabase()).get_stats_overview()
        self.assertEqual(stats["rehabilitationRate"], 0)
        self.assertEqual(stats["patientSatisfaction"], 0)
        self.assertEqual(stats["dataAvailable"]["rehabilitationRate"], False)
        self.assertEqual(stats["dataAvailable"]["patientSatisfaction"], False)

    async def test_real_counts_aggregated_from_collections(self):
        """命中数据：患者/医生/设备计数与活跃设备比例来自真实集合。"""
        db = FakeDatabase()
        now = datetime.utcnow()
        users = db.users
        users.insert({"_id": "p1", "role": "patient", "created_at": now - timedelta(days=30)})
        users.insert({"_id": "p2", "role": "patient", "created_at": now - timedelta(days=1)})
        users.insert({"_id": "d1", "role": "doctor", "created_at": now})
        devices = db.devices
        devices.insert({"_id": "dev1", "status": "active", "created_at": now})
        devices.insert({"_id": "dev2", "status": "inactive", "created_at": now})

        stats = await _service(db).get_stats_overview()
        self.assertEqual(stats["patientCount"], 2)
        self.assertEqual(stats["doctorCount"], 1)
        self.assertEqual(stats["totalDevices"], 2)
        self.assertEqual(stats["activeDeviceRate"], 50.0)
        # 一周前只有 1 名患者 -> 一周增长 100%
        self.assertEqual(stats["weekPatientChange"], 100.0)

    async def test_exception_propagates_no_mock_fallback(self):
        """数据库异常：如实上抛，不再回退模拟概览。"""
        db = FakeDatabase()
        db.users.count_error = RuntimeError("db down")
        with self.assertRaises(RuntimeError):
            await _service(db).get_stats_overview()


class TrendDataContractTests(unittest.IsolatedAsyncioTestCase):
    """get_trend_data：按 created_at 新增数量真实聚合。"""

    async def test_patient_trend_counts_creations_per_day(self):
        """week 粒度：按天统计新增患者，桶补 0，医生不计入患者序列。"""
        db = FakeDatabase()
        now = datetime.utcnow()
        today = now.replace(hour=12, minute=0, second=0, microsecond=0)
        users = db.users
        users.insert({"_id": "p1", "role": "patient", "created_at": today})
        users.insert({"_id": "p2", "role": "patient", "created_at": today})
        users.insert({"_id": "p3", "role": "patient", "created_at": today - timedelta(days=3)})
        users.insert({"_id": "d1", "role": "doctor", "created_at": today})
        # 遗留字符串日期不计入（$type: date 过滤）
        users.insert({"_id": "p4", "role": "patient", "created_at": "2020-01-01T00:00:00"})

        rows = await _service(db).get_trend_data("patient", "week")
        self.assertEqual(len(rows), 7)
        self.assertEqual(sum(r["value"] for r in rows), 3)
        # 今天桶为 2
        today_key = today.strftime("%Y-%m-%d")
        today_rows = [r for r in rows if r["timestamp"].startswith(today_key)]
        self.assertEqual(len(today_rows), 1)
        self.assertEqual(today_rows[0]["value"], 2)
        # 时间戳升序
        timestamps = [r["timestamp"] for r in rows]
        self.assertEqual(timestamps, sorted(timestamps))

    async def test_doctor_and_device_and_rehab_trends_use_own_collections(self):
        """doctor/device/rehabilitation 各自从唯一集合按 created_at 聚合。"""
        db = FakeDatabase()
        now = datetime.utcnow()
        db.users.insert({"_id": "d1", "role": "doctor", "created_at": now})
        db.devices.insert({"_id": "dev1", "created_at": now})
        db.rehab_plans.insert({"_id": "rp1", "created_at": now})

        doctor_rows = await _service(db).get_trend_data("doctor", "day")
        self.assertEqual(sum(r["value"] for r in doctor_rows), 1)
        device_rows = await _service(db).get_trend_data("device", "day")
        self.assertEqual(sum(r["value"] for r in device_rows), 1)
        rehab_rows = await _service(db).get_trend_data("rehabilitation", "day")
        self.assertEqual(sum(r["value"] for r in rehab_rows), 1)
        # 患者序列不受 doctor/device/rehab 数据影响
        patient_rows = await _service(db).get_trend_data("patient", "day")
        self.assertEqual(sum(r["value"] for r in patient_rows), 0)

    async def test_unknown_data_type_or_time_range_returns_empty(self):
        """未知类型/粒度：返回空列表，不伪造序列。"""
        db = FakeDatabase()
        self.assertEqual(await _service(db).get_trend_data("unknown", "week"), [])
        self.assertEqual(await _service(db).get_trend_data("patient", "decade"), [])

    async def test_year_trend_buckets_by_month(self):
        """year 粒度：12 个自然月桶，本月新增计入当月桶。"""
        db = FakeDatabase()
        now = datetime.utcnow()
        db.users.insert({"_id": "p1", "role": "patient", "created_at": now})
        rows = await _service(db).get_trend_data("patient", "year")
        self.assertEqual(len(rows), 12)
        self.assertEqual(sum(r["value"] for r in rows), 1)


class DistributionDataContractTests(unittest.IsolatedAsyncioTestCase):
    """get_distribution_data：按真实字段分组计数。"""

    async def test_doctor_distribution_by_department(self):
        db = FakeDatabase()
        doctors = db.users
        doctors.insert({"_id": "d1", "role": "doctor", "department": "骨科"})
        doctors.insert({"_id": "d2", "role": "doctor", "department": "骨科"})
        doctors.insert({"_id": "d3", "role": "doctor", "department": "康复科"})
        doctors.insert({"_id": "d4", "role": "doctor"})  # 缺 department
        doctors.insert({"_id": "p1", "role": "patient", "department": "骨科"})  # 非医生不计入

        rows = await _service(db).get_distribution_data("doctor", "month")
        self.assertEqual(rows, [
            {"category": "骨科", "value": 2},
            {"category": "康复科", "value": 1},
            {"category": "未填写", "value": 1},
        ])

    async def test_device_and_rehab_distribution(self):
        db = FakeDatabase()
        db.devices.insert({"_id": "v1", "device_type": "上肢康复"})
        db.devices.insert({"_id": "v2", "device_type": "下肢康复"})
        db.rehab_plans.insert({"_id": "r1", "status": "active"})
        db.rehab_plans.insert({"_id": "r2", "status": "active"})
        db.rehab_plans.insert({"_id": "r3", "status": "completed"})

        device_rows = await _service(db).get_distribution_data("device", "month")
        self.assertEqual(device_rows, [
            {"category": "上肢康复", "value": 1},
            {"category": "下肢康复", "value": 1},
        ])
        rehab_rows = await _service(db).get_distribution_data("rehabilitation", "month")
        self.assertEqual(rehab_rows, [
            {"category": "active", "value": 2},
            {"category": "completed", "value": 1},
        ])

    async def test_patient_distribution_uses_demographic_gender(self):
        db = FakeDatabase()
        db.users.insert({"_id": "p1", "role": "patient",
                         "demographic_info": {"gender": "男"}})
        db.users.insert({"_id": "p2", "role": "patient",
                         "demographic_info": {"gender": ""}})
        db.users.insert({"_id": "p3", "role": "patient"})

        rows = await _service(db).get_distribution_data("patient", "month")
        self.assertEqual(rows, [
            {"category": "未填写", "value": 2},
            {"category": "男", "value": 1},
        ])

    async def test_unknown_data_type_returns_empty(self):
        self.assertEqual(
            await _service(FakeDatabase()).get_distribution_data("unknown", "month"), [])


class ComparisonDataContractTests(unittest.IsolatedAsyncioTestCase):
    """get_comparison_data：当前窗口 vs 对比窗口新增数量。"""

    async def test_last_period_comparison(self):
        """month 窗口（30 天）：本期 2 名新增患者 vs 上一窗口 1 名。"""
        db = FakeDatabase()
        now = datetime.utcnow()
        users = db.users
        users.insert({"_id": "p1", "role": "patient", "created_at": now - timedelta(days=1)})
        users.insert({"_id": "p2", "role": "patient", "created_at": now - timedelta(days=2)})
        users.insert({"_id": "p3", "role": "patient", "created_at": now - timedelta(days=40)})

        rows = await _service(db).get_comparison_data("patient", "month", "lastPeriod")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["category"], "新增患者")
        self.assertEqual(rows[0]["currentValue"], 2)
        self.assertEqual(rows[0]["compareValue"], 1)

    async def test_last_year_comparison(self):
        db = FakeDatabase()
        now = datetime.utcnow()
        users = db.users
        users.insert({"_id": "p1", "role": "patient", "created_at": now - timedelta(days=10)})
        users.insert({"_id": "p2", "role": "patient", "created_at": now - timedelta(days=400)})

        rows = await _service(db).get_comparison_data("patient", "year", "lastYear")
        self.assertEqual(rows[0]["currentValue"], 1)
        self.assertEqual(rows[0]["compareValue"], 1)

    async def test_target_has_no_source_returns_null(self):
        """target：无真实目标值数据源，compareValue 为 null 而非伪造 100。"""
        db = FakeDatabase()
        db.users.insert({"_id": "p1", "role": "patient", "created_at": datetime.utcnow()})
        rows = await _service(db).get_comparison_data("patient", "week", "target")
        self.assertEqual(rows[0]["currentValue"], 1)
        self.assertIsNone(rows[0]["compareValue"])

    async def test_unknown_inputs(self):
        db = FakeDatabase()
        self.assertEqual(
            await _service(db).get_comparison_data("unknown", "week", "lastPeriod"), [])
        self.assertEqual(
            await _service(db).get_comparison_data("patient", "decade", "lastPeriod"), [])
        with self.assertRaises(ValueError):
            await _service(db).get_comparison_data("patient", "week", "bogus")


if __name__ == "__main__":
    unittest.main()
