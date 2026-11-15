"""T74 模拟回放端到端测试：固定帧 → 完整网关管道 → 入库 → 分析链。

REM02 红线验证：回放读数全部携带 simulated 标记，metadata.source=
automated_simulated_replay；除来源标记外，质量校验/幂等/分析链与
真实上报同一条路径。
"""
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from bson import ObjectId

from app.services.device_ingestion_service import device_ingestion_service
from app.services import device_ingestion_service as ingestion_module
from tests.device_ingestion_fake import FakeDatabase, silent_analysis_mock

DEVICE_OID = "64b0f1c2a3b4c5d6e7f80901"
DEVICE_SN = "JMD-540-A001"
PATIENT_ID = "507f1f77bcf86cd799439011"


class SimulatedReplayEndToEndTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = FakeDatabase(["devices", "device_data",
                                "device_collection_sessions"])
        self.db["devices"].docs.append({
            "_id": ObjectId(DEVICE_OID), "device_id": DEVICE_SN,
            "patient_id": PATIENT_ID, "status": "active",
            "model": "JMD-540", "device_key": "k", "settings": {},
        })
        self.service = device_ingestion_service.__class__(db=self.db)
        self.device = self.db["devices"].docs[0]
        self.analysis_mock = AsyncMock()
        self.analysis_mock.generate_device_alerts = AsyncMock(
            return_value=[{"type": "status"}])
        self.analysis_patch = patch.object(
            ingestion_module, "device_analysis_service", self.analysis_mock)
        self.analysis_patch.start()

    def tearDown(self):
        self.analysis_patch.stop()

    async def test_replay_writes_simulated_marked_readings(self):
        base = datetime.utcnow().replace(microsecond=0)
        result = await self.service.replay_simulated(
            self.device, frame_count=4, base_time=base)
        self.assertEqual(result["accepted_count"], 8)  # 每帧 2 指标 × 4 帧
        for doc in self.db["device_data"].docs:
            self.assertEqual(doc["metadata"]["source"],
                             "automated_simulated_replay")
            self.assertTrue(doc["metadata"].get("simulated"))
            self.assertIn("raw_payload", doc["metadata"])
            # 质量管道与真实路径一致：数值均为合法范围，无质量标记
            self.assertEqual(doc["quality_flags"], [])
        # 4 帧按 60s 间隔推进，逐帧时间戳确定
        self.assertEqual(
            {doc["timestamp"] for doc in self.db["device_data"].docs},
            {base + timedelta(minutes=m) for m in range(4)})
        self.analysis_mock.generate_device_alerts.assert_awaited_once()

    async def test_replay_is_idempotent_through_same_pipeline(self):
        # 同一窗口重复回放 → 幂等去重（与真实上报同管道）
        base = datetime.utcnow().replace(microsecond=0)
        await self.service.replay_simulated(self.device, 4, base_time=base)
        second = await self.service.replay_simulated(
            self.device, 4, base_time=base)
        self.assertEqual(second["accepted_count"], 0)
        self.assertEqual(second["duplicate_count"], 8)
        self.assertEqual(len(self.db["device_data"].docs), 8)

    async def test_replay_out_of_range_value_still_flagged(self):
        # 回放走同一质量管道：范围校验语义一致（固定帧值均在范围内，
        # 此处经设备级收窄范围验证标记路径）
        self.device["settings"] = {"ingestion_quality": {
            "ranges": {"heart_rate": [10, 20]}}}
        result = await self.service.replay_simulated(self.device, 2)
        flagged = [r for r in result["readings"]
                   if r["data_type"] == "heart_rate"]
        self.assertTrue(all(r["quality_flags"] == ["out_of_range:heart_rate"]
                            for r in flagged))

    async def test_replay_attaches_active_session(self):
        session_oid = ObjectId()
        self.db["device_collection_sessions"].docs.append({
            "_id": session_oid, "device_id": DEVICE_OID,
            "patient_id": PATIENT_ID, "status": "active",
            "started_at": datetime.utcnow(),
        })
        await self.service.replay_simulated(self.device, 2)
        docs = self.db["device_data"].docs
        self.assertTrue(all(
            doc["metadata"]["session_id"] == str(session_oid)
            for doc in docs))


if __name__ == "__main__":
    unittest.main()
