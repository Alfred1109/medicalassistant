"""生命体征落点盘点脚本的判定口径测试。

两部分：
1. 纯函数部分（无库依赖，不门控）：指标名归一、重叠配对判定。
2. 副本集部分（门控）：三个落点的真实文档形态下的计数、重叠与时间线覆盖。
   门控：REHAB_TEST_VITALS_AUDIT_URI，未显式提供时回退
   REHAB_TEST_PATIENT_MIGRATION_URI（同本机副本集惯例），两者都缺省时跳过。
   每个用例使用独立临时库（uuid 后缀），teardown 时 drop，只触碰 URI 指向
   实例上自己创建的库。
"""

import os
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from scripts.vitals_storage_audit import _norm_metric, _overlap, audit_database

URI = (os.environ.get("REHAB_TEST_VITALS_AUDIT_URI")
       or os.environ.get("REHAB_TEST_PATIENT_MIGRATION_URI"))


class MetricNormalisationTests(unittest.TestCase):
    def test_aliases_fold_to_one_key(self):
        self.assertEqual(_norm_metric("HR"), "heart_rate")
        self.assertEqual(_norm_metric("heart rate"), "heart_rate")
        self.assertEqual(_norm_metric("Blood-Pressure"), "blood_pressure")
        self.assertEqual(_norm_metric("BP"), "blood_pressure")
        self.assertEqual(_norm_metric("  glucose "), "blood_glucose")

    def test_non_string_is_empty(self):
        self.assertEqual(_norm_metric(None), "")
        self.assertEqual(_norm_metric(3), "")


class OverlapJudgementTests(unittest.TestCase):
    def _reading(self, patient, metric, at, ident):
        return {"id": ident, "patient_id": patient, "metric": metric, "at": at}

    def test_same_patient_same_metric_inside_window_pairs(self):
        base = datetime(2026, 11, 1, tzinfo=timezone.utc)
        health = {"_readings": [self._reading("p1", "heart_rate", base, "h1")]}
        device = {"_readings": [self._reading("p1", "heart_rate",
                                              base + timedelta(hours=2), "d1")]}
        result = _overlap(health, device, 24, 20)
        self.assertEqual(result["matched_pairs"], 1)
        self.assertEqual(result["patients"], 1)
        self.assertEqual(result["by_metric"], {"heart_rate": 1})
        self.assertEqual(result["examples"][0]["delta_hours"], 2.0)

    def test_different_patient_or_metric_does_not_pair(self):
        base = datetime(2026, 11, 1, tzinfo=timezone.utc)
        health = {"_readings": [self._reading("p1", "heart_rate", base, "h1")]}
        device = {"_readings": [self._reading("p2", "heart_rate", base, "d1"),
                                self._reading("p1", "blood_pressure", base, "d2")]}
        result = _overlap(health, device, 24, 20)
        self.assertEqual(result["matched_pairs"], 0)

    def test_outside_window_does_not_pair(self):
        base = datetime(2026, 11, 1, tzinfo=timezone.utc)
        health = {"_readings": [self._reading("p1", "heart_rate", base, "h1")]}
        device = {"_readings": [self._reading("p1", "heart_rate",
                                              base + timedelta(hours=48), "d1")]}
        self.assertEqual(_overlap(health, device, 24, 20)["matched_pairs"], 0)


@unittest.skipUnless(URI, "set REHAB_TEST_VITALS_AUDIT_URI to an isolated local replica set")
class StorageAuditReplicaTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = AsyncIOMotorClient(URI)
        self.db = self.client[f"rehab_vitals_audit_{uuid4().hex}"]

    async def asyncTearDown(self):
        await self.client.drop_database(self.db.name)
        self.client.close()

    async def test_three_landing_spots_are_counted_and_overlap_estimated(self):
        base = datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc)
        health_id = ObjectId()
        device_id = ObjectId()
        await self.db["health_data"].insert_many([
            {"_id": health_id, "patient_id": "p1", "data_type": "vital_sign",
             "source": "manual", "recorded_at": base,
             "data": {"type": "heart_rate", "value": 72, "unit": "bpm"}},
            {"_id": ObjectId(), "patient_id": "p1", "data_type": "lab_result",
             "source": "manual", "recorded_at": base, "data": {"test_name": "血糖"}},
            {"_id": ObjectId(), "data_type": "vital_sign", "source": "manual",
             "recorded_at": base, "data": {"type": "heart_rate", "value": 60}},
        ])
        await self.db["device_data"].insert_many([
            {"_id": device_id, "patient_id": "p1", "device_id": "dev1",
             "data_type": "heart_rate", "value": 71, "unit": "bpm",
             "timestamp": base + timedelta(hours=1),
             "metadata": {"source": "JMD-540"}},
            {"_id": ObjectId(), "device_id": "dev1", "data_type": "blood_pressure",
             "value": {"systolic": 120}, "timestamp": base,
             "metadata": {"source": "手工登记"}},
        ])
        await self.db["health_records"].insert_one(
            {"patient_id": "p1", "vital_signs": [{"type": "heart_rate", "value": 70}]})
        await self.db["medical_timelines"].insert_one(
            {"patient_id": "p1", "item_type": "health_data_vital_sign",
             "occurred_at": base, "related_ids": [str(health_id)]})
        await self.db["health_metrics"].insert_one({"user_id": "p1"})

        report = await audit_database(self.db, overlap_window_hours=24)

        self.assertEqual(report["health_data"]["total_documents"], 3)
        self.assertEqual(report["health_data"]["missing_patient_id"], 1)
        self.assertEqual(report["health_data"]["vital_by_type"]["heart_rate"], 2)
        self.assertEqual(report["health_data"]["by_source"]["manual"], 3)

        self.assertEqual(report["device_data"]["total_documents"], 2)
        self.assertEqual(report["device_data"]["missing_patient_id"], 1)
        self.assertEqual(report["device_data"]["by_source"]["手工登记"], 1)

        self.assertEqual(report["health_records_embedded"]["entries"], 1)
        self.assertEqual(report["health_records_embedded"]["by_type"]["heart_rate"], 1)

        self.assertEqual(report["medical_timelines"]["total_documents"], 1)
        self.assertEqual(report["medical_timelines"]["linked_health_data"], 1)
        self.assertEqual(report["medical_timelines"]["device_linked_entries"], 0)

        self.assertEqual(report["health_metrics"]["total_documents"], 1)

        self.assertEqual(report["overlap"]["matched_pairs"], 1)
        self.assertEqual(report["overlap"]["patients"], 1)
        self.assertEqual(report["overlap"]["examples"][0]["health_data_id"], str(health_id))


if __name__ == "__main__":
    unittest.main()
