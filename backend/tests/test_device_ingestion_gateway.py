"""T74 设备数据接入网关测试：鉴权、单条/批上报、幂等、质量管道、分析链。

网关服务层（DeviceIngestionService）+ 网关端点（/devices/gateway/*），
使用内存假库（device_ingestion_fake），分析链以 AsyncMock 打桩验证复用
（device_analysis_service.generate_device_alerts 不重造）。
"""
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from bson import ObjectId

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.device_ingestion_service import (
    device_ingestion_service,
    DeviceIngestionError,
    SOURCE_AUTOMATED,
    SOURCE_VEEPOO_WECHAT,
)
from app.services import device_ingestion_service as ingestion_module
from tests.device_ingestion_fake import FakeDatabase

from app.api.routers.device_router import router as device_router, \
    get_device_ingestion_service

DEVICE_OID = "64b0f1c2a3b4c5d6e7f80901"
DEVICE_SN = "JMD-540-A001"
DEVICE_KEY = "gateway-secret-1"
PATIENT_ID = "507f1f77bcf86cd799439011"


def make_device(**overrides):
    doc = {
        "_id": ObjectId(DEVICE_OID),
        "device_id": DEVICE_SN,
        "device_type": "康复评估设备",
        "model": "JMD-540",
        "patient_id": PATIENT_ID,
        "status": "active",
        "settings": {},
        "device_key": DEVICE_KEY,
    }
    doc.update(overrides)
    return doc


def frame(ts=None, hr=72, offset_seconds=0):
    """构造上报帧；ts 缺省时相对当前 UTC 时间偏移 offset_seconds（避免
    固定时刻与系统时钟漂移冲突——时间戳合理性校验按真实时钟判定）。"""
    if ts is None:
        ts = (datetime.utcnow() + timedelta(seconds=offset_seconds)
              ).isoformat() + "Z"
    return {
        "device_sn": DEVICE_SN,
        "measured_at": ts,
        "metrics": [{"metric": "heart_rate", "value": hr, "unit": "bpm"}],
    }


class IngestionServiceTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = FakeDatabase(["devices", "device_data",
                                "device_collection_sessions", "rehab_plans"])
        self.db.seed("devices", [make_device()])
        self.db.seed("users", [{"_id": ObjectId(PATIENT_ID), "role": "patient", "is_active": True}])
        self.service = device_ingestion_service.__class__(db=self.db)
        # 分析链打桩：验证复用既有 device_analysis_service，不重造
        self.analysis_mock = AsyncMock()
        self.analysis_mock.generate_device_alerts = AsyncMock(
            return_value=[{"type": "status"}])
        self.analysis_patch = patch.object(
            ingestion_module, "device_analysis_service", self.analysis_mock)
        self.analysis_patch.start()

    def tearDown(self):
        self.analysis_patch.stop()


class AuthenticateDeviceTests(IngestionServiceTestBase):
    async def test_unknown_device_rejected_without_existence_leak(self):
        with self.assertRaises(DeviceIngestionError) as ctx:
            await self.service.authenticate_device("SN-UNKNOWN", DEVICE_KEY)
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_deleted_device_rejected(self):
        self.db.seed("devices", [make_device(device_id="SN-DEL", status="deleted")])
        with self.assertRaises(DeviceIngestionError):
            await self.service.authenticate_device("SN-DEL", DEVICE_KEY)

    async def test_device_without_key_not_enabled(self):
        self.db.seed("devices", [make_device(device_id="SN-NONE", device_key=None)])
        with self.assertRaises(DeviceIngestionError) as ctx:
            await self.service.authenticate_device("SN-NONE", DEVICE_KEY)
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_wrong_key_rejected(self):
        with self.assertRaises(DeviceIngestionError) as ctx:
            await self.service.authenticate_device(DEVICE_SN, "wrong-key")
        self.assertEqual(ctx.exception.status_code, 401)

    async def test_missing_key_rejected(self):
        with self.assertRaises(DeviceIngestionError) as ctx:
            await self.service.authenticate_device(DEVICE_SN, None)
        self.assertEqual(ctx.exception.status_code, 401)

    async def test_valid_key_returns_device(self):
        device = await self.service.authenticate_device(DEVICE_SN, DEVICE_KEY)
        self.assertEqual(str(device["_id"]), DEVICE_OID)


class IngestPipelineTests(IngestionServiceTestBase):
    async def test_single_frame_written_with_automated_source(self):
        result = await self.service.ingest(await self._device(), [frame()])
        self.assertEqual(result["accepted_count"], 1)
        self.assertEqual(result["duplicate_count"], 0)
        doc = self.db["device_data"].docs[0]
        self.assertEqual(doc["metadata"]["source"], SOURCE_AUTOMATED)
        self.assertIn("raw_payload", doc["metadata"])
        self.assertEqual(doc["quality_flags"], [])
        self.assertEqual(doc["device_id"], DEVICE_OID)

    async def test_batch_frames_all_written(self):
        result = await self.service.ingest(
            await self._device(),
            [frame(offset_seconds=i, hr=70 + i) for i in range(3)])
        self.assertEqual(result["accepted_count"], 3)
        self.assertEqual(len(self.db["device_data"].docs), 3)

    async def test_idempotency_same_frame_twice_duplicates(self):
        device = await self._device()
        same_frame = frame()
        await self.service.ingest(device, [same_frame])
        result = await self.service.ingest(device, [same_frame])
        self.assertEqual(result["accepted_count"], 0)
        self.assertEqual(result["duplicate_count"], 1)
        self.assertEqual(len(self.db["device_data"].docs), 1)

    async def test_in_batch_duplicates_deduplicated(self):
        same_ts = datetime.utcnow().isoformat() + "Z"
        result = await self.service.ingest(
            await self._device(),
            [frame(ts=same_ts), frame(ts=same_ts, hr=73)])
        self.assertEqual(result["accepted_count"], 1)
        self.assertEqual(result["duplicate_count"], 1)

    async def test_out_of_range_value_flagged_not_dropped(self):
        result = await self.service.ingest(
            await self._device(), [frame(hr=999)])
        self.assertEqual(result["accepted_count"], 1)
        doc = self.db["device_data"].docs[0]
        self.assertIn("out_of_range:heart_rate", doc["quality_flags"])
        self.assertEqual(result["quality_flags_summary"],
                         {"out_of_range:heart_rate": 1})

    async def test_unregistered_metric_flagged(self):
        payload = frame()
        payload["metrics"] = [{"metric": "grip_strength", "value": 40}]
        result = await self.service.ingest(await self._device(), [payload])
        doc = self.db["device_data"].docs[0]
        self.assertIn("unregistered_metric", doc["quality_flags"])
        self.assertEqual(result["accepted_count"], 1)

    async def test_future_timestamp_hard_rejected(self):
        future = (datetime.utcnow() + timedelta(hours=2)).isoformat() + "Z"
        result = await self.service.ingest(await self._device(), [frame(ts=future)])
        self.assertEqual(result["accepted_count"], 0)
        self.assertEqual(result["rejected_count"], 1)
        self.assertIn("时间戳超前", result["rejected"][0]["error"])
        self.assertEqual(len(self.db["device_data"].docs), 0)

    async def test_malformed_frame_rejected_with_errors(self):
        result = await self.service.ingest(
            await self._device(), [{"garbage": True}])
        self.assertEqual(result["accepted_count"], 0)
        self.assertTrue(result["rejected"])
        self.assertEqual(len(self.db["device_data"].docs), 0)

    async def test_out_of_order_flagged(self):
        device = await self._device()
        await self.service.ingest(device, [frame(offset_seconds=120)])
        result = await self.service.ingest(
            device, [frame(offset_seconds=0, hr=75)])
        doc = [d for d in self.db["device_data"].docs
               if d["value"] == 75.0][0]
        self.assertIn("out_of_order", doc["quality_flags"])
        self.assertEqual(result["accepted_count"], 1)

    async def test_analysis_chain_invoked_after_ingest(self):
        result = await self.service.ingest(await self._device(), [frame()])
        self.analysis_mock.generate_device_alerts.assert_awaited_once()
        kwargs = self.analysis_mock.generate_device_alerts.await_args.kwargs
        self.assertEqual(kwargs["device_id"], DEVICE_OID)
        self.assertEqual(result["alerts_generated"], 1)

    async def test_analysis_chain_failure_does_not_lose_data(self):
        failing = AsyncMock()
        failing.generate_device_alerts = AsyncMock(
            side_effect=RuntimeError("db down"))
        patcher = patch.object(ingestion_module, "device_analysis_service",
                               failing)
        patcher.start()
        try:
            result = await self.service.ingest(await self._device(), [frame()])
        finally:
            patcher.stop()
        self.assertEqual(result["accepted_count"], 1)
        self.assertEqual(result["alerts"][0]["type"], "analysis_chain_error")
        self.assertEqual(result["alerts"][0]["type"], "analysis_chain_error")

    async def test_unregistered_model_rejected(self):
        self.db.seed("devices", [make_device(device_id="SN-X", model="UNKNOWN-1")])
        device = await self.service.authenticate_device("SN-X", DEVICE_KEY)
        with self.assertRaises(DeviceIngestionError) as ctx:
            await self.service.ingest(device, [frame()])
        self.assertEqual(ctx.exception.status_code, 422)

    async def test_last_connected_and_battery_updated_from_report(self):
        payload = frame()
        payload["battery_level"] = 88
        await self.service.ingest(await self._device(), [payload])
        device_doc = self.db["devices"].docs[0]
        self.assertIsNotNone(device_doc.get("last_connected"))
        self.assertEqual(device_doc.get("battery_level"), 88.0)

    async def test_readings_attached_to_active_session(self):
        session_oid = str(ObjectId())
        self.db.seed("device_collection_sessions", [{
            "_id": ObjectId(session_oid), "device_id": DEVICE_OID,
            "patient_id": PATIENT_ID, "status": "active",
            "started_at": datetime.utcnow() - timedelta(minutes=5),
        }])
        await self.service.ingest(await self._device(), [frame()])
        doc = self.db["device_data"].docs[0]
        self.assertEqual(doc["metadata"]["session_id"], session_oid)

    async def _device(self):
        return await self.service.authenticate_device(DEVICE_SN, DEVICE_KEY)


class GatewayEndpointTests(IngestionServiceTestBase):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(device_router, prefix="/api")
        app.dependency_overrides[get_device_ingestion_service] = lambda: self.service
        self.client = TestClient(app)

    def test_gateway_ingest_requires_device_key(self):
        response = self.client.post("/api/devices/gateway/ingest", json={
            "device_sn": DEVICE_SN, "readings": [frame()]})
        self.assertEqual(response.status_code, 401)

    def test_gateway_ingest_wrong_key_401(self):
        response = self.client.post("/api/devices/gateway/ingest", json={
            "device_sn": DEVICE_SN, "device_key": "bad", "readings": [frame()]})
        self.assertEqual(response.status_code, 401)

    def test_gateway_ingest_unknown_device_404(self):
        response = self.client.post("/api/devices/gateway/ingest", json={
            "device_sn": "NOPE", "device_key": DEVICE_KEY,
            "readings": [frame()]})
        self.assertEqual(response.status_code, 404)

    def test_gateway_ingest_body_key_success(self):
        response = self.client.post("/api/devices/gateway/ingest", json={
            "device_sn": DEVICE_SN, "device_key": DEVICE_KEY,
            "readings": [frame()]})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["accepted_count"], 1)

    def test_gateway_ingest_header_key_success(self):
        response = self.client.post(
            "/api/devices/gateway/ingest", json={
                "device_sn": DEVICE_SN, "readings": [frame()]},
            headers={"X-Device-Key": DEVICE_KEY})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["accepted_count"], 1)

    def test_gateway_batch_and_idempotent_replay(self):
        payload = {"device_sn": DEVICE_SN, "device_key": DEVICE_KEY,
                   "readings": [frame(offset_seconds=i) for i in range(5)]}
        first = self.client.post("/api/devices/gateway/ingest", json=payload)
        second = self.client.post("/api/devices/gateway/ingest", json=payload)
        self.assertEqual(first.json()["accepted_count"], 5)
        self.assertEqual(second.json()["accepted_count"], 0)
        self.assertEqual(second.json()["duplicate_count"], 5)

    def test_gateway_ingest_rejects_oversized_batch(self):
        response = self.client.post("/api/devices/gateway/ingest", json={
            "device_sn": DEVICE_SN, "device_key": DEVICE_KEY,
            "readings": [frame(offset_seconds=5)] * 501})
        self.assertEqual(response.status_code, 400)

    def test_gateway_heartbeat_refreshes_connection(self):
        response = self.client.post("/api/devices/gateway/heartbeat", json={
            "device_sn": DEVICE_SN, "device_key": DEVICE_KEY})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertIsNone(body["active_session_id"])
        self.assertIsNotNone(self.db["devices"].docs[0].get("last_connected"))

    def test_gateway_has_no_simulated_replay_route(self):
        response = self.client.post(
            f"/api/devices/{DEVICE_OID}/gateway/replay-simulated")
        self.assertEqual(response.status_code, 404)


class VeePooF300IngestionTests(IngestionServiceTestBase):
    async def test_live_heart_rate_is_normalized_and_uses_phone_capture_time(self):
        device = make_device(model="F300", settings={"veepoo_hardware_id": "F3:00:11:22:33:44"})
        captured = {}

        async def capture(device_arg, parsed, *, source, actor=None, expected_hardware_id=None):
            captured.update(device=device_arg, parsed=parsed, source=source, actor=actor,
                            expected_hardware_id=expected_hardware_id)
            return {"success": True}

        self.service._process_parsed_frames = capture
        actor = object()
        measured_at = datetime.now().astimezone()
        result = await self.service.ingest_veepoo_readings(device, [{
            "data_type": "heart_rate", "value": 81, "unit": "bpm",
            "measured_at": measured_at, "sdk_type": 51,
            "record_key": "f300-test-event",
            "raw_payload": {"heartRate": 81},
        }], actor=actor)

        reading = captured["parsed"][0].readings[0]
        self.assertEqual(result, {"success": True})
        self.assertEqual(captured["source"], SOURCE_VEEPOO_WECHAT)
        self.assertIs(captured["actor"], actor)
        self.assertEqual(captured["expected_hardware_id"], "F3:00:11:22:33:44")
        self.assertEqual(reading.data_type, "heart_rate")
        self.assertEqual(reading.value, 81)
        self.assertEqual(reading.unit, "bpm")
        self.assertEqual(reading.timestamp, measured_at)
        self.assertEqual(reading.metadata["capture_time_source"], "phone_callback")
        self.assertEqual(reading.metadata["record_key"], "f300-test-event")

    async def test_hardware_identity_is_only_pinned_for_f300(self):
        with self.assertRaises(DeviceIngestionError):
            await self.service.pin_veepoo_hardware_id(
                make_device(model="JMD-540"), "AA:BB:CC:DD", actor=object())

    async def test_hardware_identity_rejects_unencodable_unicode_without_crashing(self):
        device = make_device(model="F300")
        with self.assertRaises(DeviceIngestionError) as ctx:
            await self.service.pin_veepoo_hardware_id(
                device, "F300-\ud800", actor=object())
        self.assertEqual(ctx.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
