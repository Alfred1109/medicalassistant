"""T74 采集会话生命周期测试：开始/结束/取消、方案观测关联（打通或登记）、
会话摘要与设备在线采集标注。

设备会话可以关联方案和运动以便归档观测，但不写康复执行进度；只有患者
自报代表患者确认的训练执行状态。
"""
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from bson import ObjectId

from app.services.device_ingestion_service import device_ingestion_service
from app.services import device_ingestion_service as ingestion_module
from app.services.device_ingestion_service import DeviceIngestionError
from tests.device_ingestion_fake import FakeDatabase, silent_analysis_mock

DEVICE_OID = "64b0f1c2a3b4c5d6e7f80901"
DEVICE_SN = "JMD-540-A001"
DEVICE_KEY = "k"
PATIENT_ID = "507f1f77bcf86cd799439011"
PLAN_OID = "6ab0f1c2a3b4c5d6e7f80901"


class SessionTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = FakeDatabase(["devices", "device_data",
                                "device_collection_sessions", "rehab_plans",
                                "rehab_plan_versions", "rehab_prescription_items"])
        self.db["devices"].docs.append({
            "_id": ObjectId(DEVICE_OID), "device_id": DEVICE_SN,
            "patient_id": PATIENT_ID, "status": "active",
            "model": "JMD-540", "device_key": DEVICE_KEY, "settings": {},
        })
        self.service = device_ingestion_service.__class__(db=self.db)
        self.analysis_patch = patch.object(
            ingestion_module, "device_analysis_service",
            silent_analysis_mock())
        self.analysis_patch.start()

    def tearDown(self):
        self.analysis_patch.stop()

    def _device(self):
        return self.db["devices"].docs[0]

    VERSION_ID = "6ab0f1c2a3b4c5d6e7f80902"
    ITEM_ID = "prescription-item-1"

    def _seed_plan(self):
        self.db["rehab_plans"].docs.append({
            "_id": ObjectId(PLAN_OID),
            "patient_id": PATIENT_ID,
            "published_version_id": self.VERSION_ID,
            "status": "active",
        })
        self.db["rehab_plan_versions"].docs.append({
            "_id": ObjectId(self.VERSION_ID), "plan_id": PLAN_OID,
            "patient_id": PATIENT_ID, "workflow": "patient_publication",
            "status": "published",
            "items_snapshot": [{"item_id": self.ITEM_ID, "name": "肘关节屈伸",
                                "intervention_type": "exercise"}],
        })
        self.db["rehab_prescription_items"].docs.append({
            "plan_id": PLAN_OID, "version_id": self.VERSION_ID,
            "item_id": self.ITEM_ID, "name": "肘关节屈伸",
        })


class StartSessionTests(SessionTestBase):
    async def test_start_session_without_plan_linkage_none(self):
        session = await self.service.start_collection_session(
            self._device(), PATIENT_ID)
        self.assertEqual(session["status"], "active")
        self.assertEqual(session["linkage_status"], "none")
        self.assertEqual(session["patient_id"], PATIENT_ID)
        device_doc = self.db["devices"].docs[0]
        self.assertEqual(device_doc.get("active_session_id"), session["_id"])

    async def test_start_session_with_verified_plan_is_linked(self):
        self._seed_plan()
        session = await self.service.start_collection_session(
            self._device(), PATIENT_ID, plan_id=PLAN_OID,
            version_id=self.VERSION_ID, prescription_item_id=self.ITEM_ID)
        self.assertEqual(session["linkage_status"], "linked")
        self.assertIsNone(session["linkage_error"])

    async def test_partial_plan_linkage_is_rejected(self):
        with self.assertRaises(DeviceIngestionError) as ctx:
            await self.service.start_collection_session(
                self._device(), PATIENT_ID, plan_id=PLAN_OID)
        self.assertEqual(ctx.exception.status_code, 422)

    async def test_plan_owned_by_another_patient_is_rejected(self):
        self._seed_plan()
        with self.assertRaises(DeviceIngestionError) as ctx:
            await self.service.start_collection_session(
                self._device(), "another-patient", plan_id=PLAN_OID,
                version_id=self.VERSION_ID, prescription_item_id=self.ITEM_ID)
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_wrong_version_or_item_is_rejected(self):
        self._seed_plan()
        with self.assertRaises(DeviceIngestionError):
            await self.service.start_collection_session(
                self._device(), PATIENT_ID, plan_id=PLAN_OID,
                version_id=str(ObjectId()), prescription_item_id=self.ITEM_ID)
        await self.db["rehab_plan_versions"].update_one(
            {"_id": ObjectId(self.VERSION_ID)},
            {"$set": {"items_snapshot": [{"item_id": "other-item",
                                             "intervention_type": "exercise"}]}})
        with self.assertRaises(DeviceIngestionError):
            await self.service.start_collection_session(
                self._device(), PATIENT_ID, plan_id=PLAN_OID,
                version_id=self.VERSION_ID, prescription_item_id=self.ITEM_ID)

    async def test_malformed_plan_id_registered(self):
        with self.assertRaises(DeviceIngestionError) as ctx:
            await self.service.start_collection_session(
                self._device(), PATIENT_ID, plan_id="not-objectid",
                version_id=self.VERSION_ID, prescription_item_id=self.ITEM_ID)
        self.assertEqual(ctx.exception.status_code, 422)

    async def test_second_active_session_conflict_409(self):
        await self.service.start_collection_session(self._device(), PATIENT_ID)
        with self.assertRaises(DeviceIngestionError) as ctx:
            await self.service.start_collection_session(self._device(), PATIENT_ID)
        self.assertEqual(ctx.exception.status_code, 409)


class EndSessionTests(SessionTestBase):
    async def _start(self, **kwargs):
        return await self.service.start_collection_session(
            self._device(), PATIENT_ID, **kwargs)

    def _seed_session_reading(self, session_id, value=72, flags=None):
        self.db["device_data"].docs.append({
            "_id": ObjectId(), "device_id": DEVICE_OID,
            "patient_id": PATIENT_ID, "data_type": "heart_rate",
            "value": value, "unit": "bpm",
            "timestamp": datetime.utcnow(),
            "metadata": {"source": "automated", "session_id": session_id},
            "quality_flags": flags or [],
            "created_at": datetime.utcnow(),
        })

    async def test_end_session_writes_summary_and_unsets_device_state(self):
        session = await self._start()
        self._seed_session_reading(session["_id"], 72)
        self._seed_session_reading(session["_id"], 999,
                                   flags=["out_of_range:heart_rate"])
        ended = await self.service.end_collection_session(
            self._device(), session["_id"])
        self.assertEqual(ended["status"], "ended")
        self.assertIsNotNone(ended["ended_at"])
        self.assertEqual(ended["summary"]["readings_count"], 2)
        self.assertEqual(ended["summary"]["flagged_count"], 1)
        self.assertNotIn("rehab_progress_logged", ended["summary"])
        device_doc = self.db["devices"].docs[0]
        self.assertNotIn("active_session_id", device_doc)

    async def test_end_linked_session_preserves_device_observation_without_rehab_progress(self):
        self._seed_plan()
        session = await self._start(plan_id=PLAN_OID,
                                    version_id=StartSessionTests.VERSION_ID,
                                    prescription_item_id=StartSessionTests.ITEM_ID)
        self._seed_session_reading(session["_id"], 72)
        ended = await self.service.end_collection_session(
            self._device(), session["_id"])
        self.assertEqual(ended["linkage_status"], "linked")
        self.assertEqual(ended["plan_id"], PLAN_OID)
        self.assertEqual(ended["prescription_item_id"], StartSessionTests.ITEM_ID)
        self.assertNotIn("rehab_progress_logged", ended["summary"])
        self.assertEqual(self.db["rehab_plans"].docs[0]["published_version_id"],
                         StartSessionTests.VERSION_ID)
        self.assertEqual(ended["summary"]["readings_count"], 1)

    async def test_cancel_session_marks_cancelled(self):
        session = await self._start()
        ended = await self.service.end_collection_session(
            self._device(), session["_id"], cancel=True)
        self.assertEqual(ended["status"], "cancelled")
        self.assertEqual(ended["summary"]["ended_as"], "cancelled")

    async def test_end_unknown_or_ended_session_returns_none(self):
        self.assertIsNone(await self.service.end_collection_session(
            self._device(), "not-an-objectid"))
        self.assertIsNone(await self.service.end_collection_session(
            self._device(), str(ObjectId())))
        session = await self._start()
        await self.service.end_collection_session(self._device(), session["_id"])
        self.assertIsNone(await self.service.end_collection_session(
            self._device(), session["_id"]))  # 已结束不可重复结束

    async def test_list_sessions_ordered_latest_first(self):
        first = await self._start()
        # 结束第一个会话后才能开第二个（真实流程 409 拦截并发会话）
        self.db["device_collection_sessions"].docs[0]["status"] = "ended"
        second = await self._start()
        self.db["device_collection_sessions"].docs[0]["started_at"] = \
            datetime(2026, 1, 1)
        sessions = await self.service.list_collection_sessions(DEVICE_OID)
        self.assertEqual([s["_id"] for s in sessions][0], second["_id"])
        self.assertEqual(len(sessions), 2)


if __name__ == "__main__":
    unittest.main()
