"""T74 设备数据质量管道测试：指标范围配置、时间戳合理性、质量报告。

质量分级语义回归锁定：
- 必填/时间戳异常 → 硬拒绝（不入库，响应 rejected 可见）；
- 范围超标/乱序/未登记指标 → 标记 quality_flags 入库（分析侧可见可过滤）；
- 重复 → 剔除不写库。
"""
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from bson import ObjectId

from app.services.device_ingestion_service import (
    device_ingestion_service,
    DEFAULT_METRIC_RANGES,
    FLAG_OUT_OF_ORDER,
    FLAG_UNREGISTERED_METRIC,
    SOURCE_AUTOMATED,
)
from app.services import device_ingestion_service as ingestion_module
from tests.device_ingestion_fake import FakeDatabase, silent_analysis_mock


class QualityConfigTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = FakeDatabase(["devices", "device_data",
                                "device_collection_sessions"])
        self.service = device_ingestion_service.__class__(db=self.db)
        self.analysis_patch = patch.object(
            ingestion_module, "device_analysis_service",
            silent_analysis_mock())
        self.analysis_patch.start()

    def tearDown(self):
        self.analysis_patch.stop()

    def _device(self, settings=None):
        return {"_id": "64b0f1c2a3b4c5d6e7f80901", "device_id": "SN-Q",
                "patient_id": "p1", "model": "JMD-540",
                "settings": settings or {}}

    def _frame(self, metric="heart_rate", value=72, ts=None):
        if ts is None:
            ts = datetime.utcnow().isoformat() + "Z"
        return {"device_sn": "SN-Q", "measured_at": ts,
                "metrics": [{"metric": metric, "value": value}]}

    async def _ingest(self, settings=None, frames=None):
        device = self._device(settings)
        return await self.service.ingest(device, frames or [self._frame()])

    async def test_default_ranges_applied(self):
        result = await self._ingest(frames=[self._frame(value=1000)])
        doc = self.db["device_data"].docs[0]
        self.assertIn("out_of_range:heart_rate", doc["quality_flags"])

    async def test_device_settings_override_ranges(self):
        settings = {"ingestion_quality": {"ranges": {"heart_rate": [10, 20]}}}
        base = datetime.utcnow().isoformat() + "Z"
        later = (datetime.utcnow() + timedelta(seconds=1)).isoformat() + "Z"
        await self._ingest(settings=settings, frames=[
            self._frame(value=15, ts=base), self._frame(value=25, ts=later)])
        by_value = {d["value"]: d["quality_flags"]
                    for d in self.db["device_data"].docs}
        self.assertEqual(by_value[15.0], [])          # 设备级范围内
        self.assertIn("out_of_range:heart_rate", by_value[25.0])

    async def test_malformed_range_config_does_not_guess(self):
        settings = {"ingestion_quality": {"ranges": {"heart_rate": ["低", 2]}}}
        result = await self._ingest(settings=settings, frames=[
            self._frame(value=9999)])
        doc = self.db["device_data"].docs[0]
        # 配置畸形时不猜测：不标 out_of_range，也不硬拒绝
        self.assertNotIn("out_of_range:heart_rate", doc["quality_flags"])
        self.assertEqual(result["accepted_count"], 1)

    async def test_default_range_table_covers_core_metrics(self):
        for metric in ("heart_rate", "spo2", "systolic_pressure",
                       "diastolic_pressure", "body_temperature"):
            self.assertIn(metric, DEFAULT_METRIC_RANGES)
            lo, hi = DEFAULT_METRIC_RANGES[metric]
            self.assertLess(lo, hi)

    async def test_future_beyond_tolerance_rejected(self):
        future = (datetime.utcnow() + timedelta(minutes=10)).isoformat() + "Z"
        result = await self._ingest(frames=[self._frame(ts=future)])
        self.assertEqual(result["rejected_count"], 1)
        self.assertEqual(len(self.db["device_data"].docs), 0)

    async def test_future_within_tolerance_accepted(self):
        near_future = (datetime.utcnow() + timedelta(seconds=60)).isoformat() + "Z"
        result = await self._ingest(frames=[self._frame(ts=near_future)])
        self.assertEqual(result["accepted_count"], 1)

    async def test_ancient_timestamp_rejected(self):
        ancient = (datetime.utcnow() - timedelta(days=400)).isoformat() + "Z"
        result = await self._ingest(frames=[self._frame(ts=ancient)])
        self.assertEqual(result["rejected_count"], 1)
        self.assertIn("时间戳过旧", result["rejected"][0]["error"])

    async def test_max_age_days_device_override(self):
        settings = {"ingestion_quality": {"max_age_days": 1}}
        old = (datetime.utcnow() - timedelta(days=10)).isoformat() + "Z"
        result = await self._ingest(settings=settings,
                                    frames=[self._frame(ts=old)])
        self.assertEqual(result["rejected_count"], 1)


class QualityReportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = FakeDatabase(["devices", "device_data",
                                "device_collection_sessions"])
        self.service = device_ingestion_service.__class__(db=self.db)
        self.analysis_patch = patch.object(
            ingestion_module, "device_analysis_service",
            silent_analysis_mock())
        self.analysis_patch.start()

    def tearDown(self):
        self.analysis_patch.stop()

    def _seed_reading(self, value, flags=None, ts=None, source=SOURCE_AUTOMATED,
                      device_id="D1"):
        self.db["device_data"].docs.append({
            "_id": ObjectId(),
            "device_id": device_id, "patient_id": "p1",
            "data_type": "heart_rate", "value": value, "unit": "bpm",
            "timestamp": ts or datetime(2026, 11, 15, 8, 0, 0),
            "metadata": {"source": source},
            "quality_flags": flags or [],
            "created_at": datetime.utcnow(),
        })

    async def test_report_counts_and_pass_rate(self):
        self._seed_reading(72)
        self._seed_reading(999, flags=["out_of_range:heart_rate"])
        self._seed_reading(76, flags=[FLAG_OUT_OF_ORDER])
        self._seed_reading(70, device_id="D2")  # 其他设备不计入
        report = await self.service.quality_report("D1")
        self.assertEqual(report["total_automated"], 3)
        self.assertEqual(report["passed"], 1)
        self.assertEqual(report["flagged"], 2)
        self.assertEqual(report["pass_rate"], round(1 / 3, 4))
        self.assertEqual(report["out_of_range_count"], 1)

    async def test_report_window_filter(self):
        base = datetime(2026, 11, 15, 8, 0, 0)
        self._seed_reading(72, ts=base)
        self._seed_reading(73, ts=base + timedelta(hours=2))
        report = await self.service.quality_report(
            "D1", start=base + timedelta(hours=1))
        self.assertEqual(report["total_automated"], 1)

    async def test_report_excludes_manual_readings(self):
        self._seed_reading(72, source=None)
        self.db["device_data"].docs[-1]["metadata"] = {"source": "手工登记"}
        report = await self.service.quality_report("D1")
        self.assertEqual(report["total_automated"], 0)
        self.assertIsNone(report["pass_rate"])

    async def test_report_empty_device(self):
        report = await self.service.quality_report("D-EMPTY")
        self.assertEqual(report["total_automated"], 0)
        self.assertIsNone(report["pass_rate"])


if __name__ == "__main__":
    unittest.main()
