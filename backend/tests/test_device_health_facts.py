"""Device raw telemetry and clinical facts share one atomic acceptance decision."""
import asyncio
import os
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit
from uuid import uuid4

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo.errors import OperationFailure

from app.core.exceptions import AppBaseException
from app.services.device_health_data import device_health_document
from app.services.device_ingestion_service import DeviceIngestionError, DeviceIngestionService
from app.services.device_service import DeviceService
from app.models.health_data_threshold import HealthDataThreshold


class DeviceFactMappingTests(unittest.TestCase):
    def reading(self, metric="heart_rate", source="automated", **overrides):
        return {"_id": ObjectId(), "device_id": str(ObjectId()), "data_type": metric,
                "timestamp": datetime.utcnow(), "created_at": datetime.utcnow(),
                "value": 72.0, "unit": "bpm", "quality_flags": ["out_of_order"],
                "metadata": {"source": source, "raw_payload": {"private": "raw-only"}}, **overrides}

    def test_aliases_preserve_values_units_quality_and_raw_identity(self):
        aliases = {"spo2": "oxygen_saturation", "respiration_rate": "respiratory_rate",
                   "pulse": "heart_rate", "systolic_pressure": "blood_pressure_systolic",
                   "diastolic_pressure": "blood_pressure_diastolic"}
        for original, expected in aliases.items():
            row = self.reading(original, quality_flags=["out_of_range:" + original, "unknown_future_flag"])
            fact = device_health_document(row, "patient-1")
            self.assertEqual(fact["_id"], row["_id"])
            self.assertEqual(fact["data"], {"type": expected, "value": row["value"], "unit": row["unit"]})
            self.assertEqual(fact["recorded_at"], row["timestamp"])
            self.assertEqual(fact["source"], "device")
            self.assertEqual(fact["metadata"]["device_data_type"], original)
            self.assertEqual(fact["metadata"]["quality_flags"], row["quality_flags"])
            self.assertNotIn("raw_payload", fact["metadata"])

    def test_unknown_metrics_are_explicit_measurements_and_simulation_is_raw_only(self):
        self.assertEqual(device_health_document(self.reading("vendor_metric"), "p")["data_type"], "device_measurement")
        self.assertIsNone(device_health_document(self.reading(source="automated_simulated_replay"), "p"))
        row = self.reading(); row["metadata"]["simulated"] = True
        self.assertIsNone(device_health_document(row, "p"))


@unittest.skipUnless(os.getenv("REHAB_TEST_DEVICE_FACT_MONGO_URI"), "isolated replica set required")
class DeviceFactTransactions(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        uri = os.environ["REHAB_TEST_DEVICE_FACT_MONGO_URI"]
        if urlsplit(uri).hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError("Only disposable local databases are allowed")
        self.client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=3000)
        self.db = self.client["rehab_device_facts_" + uuid4().hex]
        self.pid, self.did = ObjectId(), ObjectId()
        self.actor = SimpleNamespace(id=str(ObjectId()), role="doctor")
        await self.db.users.insert_many([
            {"_id": ObjectId(self.actor.id), "role": "doctor", "is_active": True},
            {"_id": self.pid, "role": "patient", "is_active": True, "practitioners": [self.actor.id]},
        ])
        self.device = {"_id": self.did, "patient_id": str(self.pid), "device_id": "FACT-SN",
                       "status": "active", "model": "JMD-540", "device_type": "手环",
                       "device_key": "test-only-key", "settings": {}}
        await self.db.devices.insert_one(self.device)
        # Pre-create namespaces as production initialization does; no production database is used.
        await self.db.create_collection("device_data")
        await self.db.create_collection("health_data")
        self.gateway = DeviceIngestionService(self.db)
        self.gateway._trigger_analysis = AsyncMock(return_value=[])
        self.manual = DeviceService(self.db)
        self.now = datetime.utcnow().replace(microsecond=0)

    async def asyncTearDown(self):
        await self.client.drop_database(self.db.name)
        self.client.close()

    def frame(self, metric="heart_rate", value=72, at=None):
        return {"device_sn": "FACT-SN", "measured_at": (at or self.now).isoformat() + "Z",
                "metrics": [{"metric": metric, "value": value, "unit": "raw-unit"}]}

    async def test_gateway_preserves_quality_and_does_not_pair_blood_pressure_components(self):
        result = await self.gateway.ingest(self.device, [self.frame("systolic_pressure", 999),
            self.frame("diastolic_pressure", 80, self.now + timedelta(seconds=2))])
        self.assertEqual(result["accepted_count"], 2)
        facts = await self.db.health_data.find({}).sort("recorded_at", 1).to_list(None)
        raw = await self.db.device_data.find({}).sort("timestamp", 1).to_list(None)
        self.assertEqual([f["data"]["type"] for f in facts], ["blood_pressure_systolic", "blood_pressure_diastolic"])
        for fact, reading in zip(facts, raw):
            self.assertEqual(fact["_id"], reading["_id"])
            self.assertEqual(fact["recorded_at"], reading["timestamp"])
            self.assertEqual(fact["metadata"]["quality_flags"], reading["quality_flags"])
            self.assertEqual(fact["patient_id"], str(self.pid))
        self.assertIn("out_of_range:systolic_pressure", facts[0]["metadata"]["quality_flags"])

    async def test_concurrent_duplicate_payload_commits_one_raw_and_one_fact(self):
        results = await asyncio.gather(*(self.gateway.ingest(self.device, [self.frame()]) for _ in range(6)))
        self.assertEqual(sum(r["accepted_count"] for r in results), 1)
        self.assertEqual(sum(r["duplicate_count"] for r in results), 5)
        self.assertEqual(await self.db.device_data.count_documents({}), 1)
        self.assertEqual(await self.db.health_data.count_documents({}), 1)

    async def test_fact_write_failure_rolls_back_raw_and_same_payload_can_be_retried(self):
        original = AsyncIOMotorCollection.insert_one
        async def fail_fact(collection, *args, **kwargs):
            if collection.name == "health_data":
                raise OperationFailure("injected fact storage failure")
            return await original(collection, *args, **kwargs)
        with patch.object(AsyncIOMotorCollection, "insert_one", fail_fact):
            with self.assertRaises(AppBaseException):
                await self.gateway.ingest(self.device, [self.frame()])
        self.assertEqual(await self.db.device_data.count_documents({}), 0)
        self.assertEqual(await self.db.health_data.count_documents({}), 0)
        self.assertEqual((await self.gateway.ingest(self.device, [self.frame()]))["accepted_count"], 1)

    async def test_stale_binding_and_revoked_credential_cannot_write_to_another_patient(self):
        for change in ({"patient_id": str(ObjectId())}, {"device_key": "rotated-test-key"}, {"status": "deleted"}):
            await self.db.devices.replace_one({"_id": self.did}, {**self.device, **change})
            with self.assertRaises(DeviceIngestionError):
                await self.gateway.ingest(self.device, [self.frame()])
        self.assertEqual(await self.db.device_data.count_documents({}), 0)
        self.assertEqual(await self.db.health_data.count_documents({}), 0)

    async def test_manual_reading_commits_fact_under_existing_authority(self):
        row = await self.manual.record_manual_reading(str(self.did), "heart_rate", "73.4", "", self.now, actor=self.actor)
        fact = await self.db.health_data.find_one({"_id": ObjectId(row["id"])})
        self.assertEqual(fact["data"]["value"], row["value"])
        self.assertEqual(fact["data"]["unit"], row["unit"])
        self.assertEqual(fact["recorded_by"], self.actor.id)
        self.assertEqual(fact["metadata"]["measurement_source"], "手工登记")

    async def test_manual_fact_failure_rolls_back_telemetry(self):
        original = AsyncIOMotorCollection.insert_one
        async def fail_fact(collection, *args, **kwargs):
            if collection.name == "health_data":
                raise OperationFailure("injected manual fact failure")
            return await original(collection, *args, **kwargs)
        with patch.object(AsyncIOMotorCollection, "insert_one", fail_fact):
            with self.assertRaises(AppBaseException):
                await self.manual.record_manual_reading(str(self.did), "heart_rate", "72", "bpm", self.now, actor=self.actor)
        self.assertEqual(await self.db.device_data.count_documents({}), 0)
        self.assertEqual(await self.db.health_data.count_documents({}), 0)

    async def test_missing_and_nonpatient_bindings_fail_but_existing_legacy_string_patient_is_preserved(self):
        for patient_id in ("missing-legacy-id", self.actor.id, None, ""):
            stale = {**self.device, "patient_id": patient_id}
            await self.db.devices.replace_one({"_id": self.did}, stale)
            with self.assertRaises((AppBaseException, DeviceIngestionError)):
                await self.gateway.ingest(stale, [self.frame()])
        self.assertEqual(await self.db.device_data.count_documents({}), 0)
        self.assertEqual(await self.db.health_data.count_documents({}), 0)
        await self.db.users.insert_one({"_id": "existing-legacy-patient", "role": "patient", "is_active": True})
        legacy = {**self.device, "patient_id": "existing-legacy-patient"}
        await self.db.devices.replace_one({"_id": self.did}, legacy)
        await self.gateway.ingest(legacy, [self.frame()])
        self.assertEqual((await self.db.health_data.find_one({}))["patient_id"], "existing-legacy-patient")

    async def test_credential_rotation_during_ingestion_prevents_old_key_commit(self):
        original = AsyncIOMotorCollection.update_one
        reached, proceed = asyncio.Event(), asyncio.Event()
        paused = False
        async def pause_device_fence(collection, query, update, **kwargs):
            nonlocal paused
            if not paused and collection.name == "devices" and "_device_write_fence" in update.get("$inc", {}):
                paused = True
                reached.set()
                await asyncio.wait_for(proceed.wait(), 5)
            return await original(collection, query, update, **kwargs)
        with patch.object(AsyncIOMotorCollection, "update_one", pause_device_fence):
            task = asyncio.create_task(self.gateway.ingest(self.device, [self.frame()]))
            try:
                await asyncio.wait_for(reached.wait(), 5)
                await original(self.db.devices, {"_id": self.did}, {"$set": {"device_key": "rotated-test-key"}})
            finally:
                proceed.set()
            with self.assertRaises(DeviceIngestionError):
                await task
        self.assertEqual(await self.db.device_data.count_documents({}), 0)
        self.assertEqual(await self.db.health_data.count_documents({}), 0)

    async def test_canonical_patient_without_account_accepts_but_unknown_domain_fails_closed(self):
        await self.db.users.delete_one({"_id": self.pid})
        await self.db.patient_domain_state.insert_one({"_id": "clinical-patients-v1", "mode": "canonical", "schema_version": 1})
        await self.db.clinical_patients.insert_one({"patient_id": str(self.pid), "status": "active", "name": "synthetic"})
        result = await self.gateway.ingest(self.device, [self.frame()])
        self.assertEqual(result["accepted_count"], 1)
        self.assertEqual((await self.db.health_data.find_one({}))["patient_id"], str(self.pid))
        self.assertEqual(await self.db.patient_account_links.count_documents({}), 0)
        await self.db.patient_domain_state.update_one({"_id": "clinical-patients-v1"}, {"$set": {"mode": "migrating"}})
        with self.assertRaises(AppBaseException) as raised:
            await self.gateway.ingest(self.device, [self.frame(at=self.now + timedelta(seconds=1))])
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(await self.db.device_data.count_documents({}), 1)
        self.assertEqual(await self.db.health_data.count_documents({}), 1)

    async def test_simulated_replay_keeps_telemetry_without_clinical_facts(self):
        result = await self.gateway.replay_simulated(self.device, 1, base_time=self.now)
        self.assertEqual(result["accepted_count"], 2)
        self.assertEqual(await self.db.device_data.count_documents({}), 2)
        self.assertEqual(await self.db.health_data.count_documents({}), 0)

    async def test_simulation_and_real_reading_do_not_consume_each_others_identity(self):
        simulated = await self.gateway.replay_simulated(self.device, 1, base_time=self.now)
        self.assertEqual(simulated["clinical_facts_created"], 0)
        real = await self.gateway.ingest(self.device, [self.frame(value=81)])
        self.assertEqual((real["accepted_count"], real["clinical_facts_created"]), (1, 1))
        repeated = await self.gateway.ingest(self.device, [self.frame(value=81)])
        self.assertEqual((repeated["duplicate_count"], repeated["clinical_facts_created"]), (1, 0))
        repeated_simulation = await self.gateway.replay_simulated(self.device, 1, base_time=self.now)
        self.assertEqual((repeated_simulation["duplicate_count"], repeated_simulation["clinical_facts_created"]), (2, 0))
        self.assertEqual(await self.db.device_data.count_documents({}), 3)
        self.assertEqual((await self.db.health_data.find_one({}))["data"]["value"], 81)

    async def test_real_then_simulated_same_identity_both_keep_their_own_source(self):
        await self.gateway.ingest(self.device, [self.frame()])
        replayed = await self.gateway.replay_simulated(self.device, 1, base_time=self.now)
        self.assertEqual((replayed["accepted_count"], replayed["clinical_facts_created"]), (2, 0))
        self.assertEqual(await self.db.health_data.count_documents({}), 1)

    async def test_explicit_simulation_metadata_has_separate_identity_in_a_mixed_batch(self):
        adapter = self.gateway._select_adapter(self.device)
        frames = [adapter.parse(self.frame()), adapter.parse(self.frame(value=81))]
        frames[0].readings[0].metadata["simulated"] = True
        result = await self.gateway._process_parsed_frames(self.device, frames, source="automated")
        self.assertEqual((result["accepted_count"], result["clinical_facts_created"]), (2, 1))
        repeated = await self.gateway._process_parsed_frames(self.device, frames, source="automated")
        self.assertEqual((repeated["duplicate_count"], repeated["clinical_facts_created"]), (2, 0))
        self.assertEqual((await self.db.health_data.find_one({}))["data"]["value"], 81)

    async def test_historical_real_raw_without_fact_is_duplicate_without_backfill(self):
        await self.db.device_data.insert_one({"_id": ObjectId(), "device_id": str(self.did),
            "data_type": "heart_rate", "timestamp": self.now, "value": 72,
            "metadata": {"source": "automated"}})
        result = await self.gateway.ingest(self.device, [self.frame()])
        self.assertEqual((result["duplicate_count"], result["clinical_facts_created"]), (1, 0))
        self.assertIn("不回填历史", result["readings"][0]["reason"])
        self.assertEqual(await self.db.health_data.count_documents({}), 0)

    async def test_simulated_times_do_not_mark_a_real_reading_out_of_order(self):
        await self.gateway.replay_simulated(self.device, 1, base_time=self.now + timedelta(seconds=10))
        result = await self.gateway.ingest(self.device, [self.frame()])
        self.assertNotIn("out_of_order", result["readings"][0]["quality_flags"])

    async def test_reading_views_filter_simulation_before_limiting_and_include_f300_in_quality(self):
        sources = [
            {"source": "automated"}, {"source": "veepoo_wechat"}, {"source": "手工登记"},
            {"source": "automated_simulated_replay"}, {"source": "automated", "simulated": True},
        ]
        device_id = str(self.did)
        await self.db.device_data.insert_many([
            {"device_id": device_id, "timestamp": self.now + timedelta(seconds=index),
             "metadata": metadata, "quality_flags": ["out_of_order"] if index else []}
            for index, metadata in enumerate(sources)
        ])

        latest = await self.manual.get_device_data(device_id, limit=1)
        automated = await self.manual.get_device_data(device_id, limit=2, automated_only=True)
        report = await self.gateway.quality_report(device_id)
        self.assertEqual([row["metadata"]["source"] for row in latest], ["手工登记"])
        self.assertEqual([row["metadata"]["source"] for row in automated], ["veepoo_wechat", "automated"])
        self.assertEqual((report["total_automated"], report["flagged"], report["pass_rate"]), (2, 1, 0.5))
        self.assertEqual(await self.db.device_data.count_documents({}), 5)

    async def test_stale_heartbeat_and_all_rejected_batch_cannot_refresh_rebound_device(self):
        for change in ({"device_key": "new-key"}, {"patient_id": str(ObjectId())}, {"status": "deleted"}):
            await self.db.devices.replace_one({"_id": self.did}, self.device)
            authenticated = await self.gateway.authenticate_device("FACT-SN", "test-only-key")
            await self.db.devices.update_one({"_id": self.did}, {"$set": change})
            with self.assertRaises(DeviceIngestionError):
                await self.gateway.heartbeat(authenticated)
            with self.assertRaises(DeviceIngestionError):
                await self.gateway.ingest(authenticated, [self.frame(at=self.now + timedelta(days=1))])
            current = await self.db.devices.find_one({"_id": self.did})
            self.assertNotIn("last_connected", current)
        self.assertEqual(await self.db.device_data.count_documents({}), 0)
        self.assertEqual(await self.db.health_data.count_documents({}), 0)

    async def test_credential_rotation_after_fact_commit_cannot_refresh_connection(self):
        original = AsyncIOMotorCollection.update_one
        reached, proceed = asyncio.Event(), asyncio.Event()

        async def pause_connection_update(collection, query, update, **kwargs):
            if collection.name == "devices" and "last_connected" in update.get("$set", {}):
                reached.set()
                await asyncio.wait_for(proceed.wait(), 5)
            return await original(collection, query, update, **kwargs)

        authenticated = await self.gateway.authenticate_device("FACT-SN", "test-only-key")
        with patch.object(AsyncIOMotorCollection, "update_one", pause_connection_update):
            task = asyncio.create_task(self.gateway.ingest(authenticated, [self.frame()]))
            try:
                await asyncio.wait_for(reached.wait(), 5)
                await original(self.db.devices, {"_id": self.did}, {"$set": {"device_key": "new-key"}})
            finally:
                proceed.set()
            with self.assertRaises(DeviceIngestionError) as error:
                await task
        self.assertEqual(error.exception.status_code, 409)
        self.assertNotIn("last_connected", await self.db.devices.find_one({"_id": self.did}))
        self.assertEqual((await self.db.health_data.find_one({}))["patient_id"], str(self.pid))
        self.assertEqual(await self.db.device_data.count_documents({}), 1)

    async def prepare_blood_pressure(self):
        await self.db.devices.update_one({"_id": self.did}, {"$set": {"device_type": "血压计"}})
        await self.db.health_data_thresholds.insert_one(HealthDataThreshold.create_blood_pressure_threshold(
            name="synthetic configured threshold", normal_systolic={"min": 90, "max": 120},
            normal_diastolic={"min": 60, "max": 80}, is_default=True).to_mongo())

    def blood_pressure_fact(self, *, patient_id=None, device_id=None, at=None):
        reading = {"_id": ObjectId(), "device_id": device_id or str(self.did),
            "data_type": "blood_pressure_systolic", "value": 150, "unit": "mmHg",
            "timestamp": at or self.now - timedelta(minutes=10), "created_at": self.now,
            "quality_flags": [], "metadata": {"source": "automated"}}
        return device_health_document(reading, patient_id or str(self.pid))

    async def record_diastolic(self, *, unit="mmHg"):
        return await self.manual.record_manual_reading(str(self.did), "blood_pressure_diastolic", "95",
            unit, self.now, actor=self.actor)

    async def test_clinical_blood_pressure_pairs_fact_without_raw_telemetry(self):
        await self.prepare_blood_pressure()
        await self.db.health_data.insert_one(self.blood_pressure_fact())
        row = await self.record_diastolic()
        self.assertEqual(row["metadata"]["health_alert"]["status"], "warning")
        alert = await self.db.health_data_alerts.find_one({})
        self.assertEqual(alert["value"], {"systolic": 150, "diastolic": 95})
        self.assertEqual(await self.db.device_data.count_documents({}), 1)

    async def test_raw_only_or_foreign_patient_or_device_cannot_supply_clinical_component(self):
        await self.prepare_blood_pressure()
        await self.db.device_data.insert_one({"_id": ObjectId(), "device_id": str(self.did),
            "data_type": "blood_pressure_systolic", "value": 150, "unit": "mmHg",
            "timestamp": self.now, "metadata": {"source": "automated_simulated_replay"}})
        await self.db.health_data.insert_many([
            self.blood_pressure_fact(patient_id=str(ObjectId())),
            self.blood_pressure_fact(device_id=str(ObjectId()))])
        row = await self.record_diastolic()
        self.assertEqual(row["metadata"]["health_alert"]["status"], "skipped")
        self.assertEqual(await self.db.health_data_alerts.count_documents({}), 0)

    async def test_untrusted_or_flagged_or_wrong_unit_component_never_forms_clinical_pair(self):
        await self.prepare_blood_pressure()
        invalid = [
            ("metadata.quality_flags", ["out_of_range:systolic_pressure"]),
            ("metadata.quality_flags", "corrupt"), ("metadata.quality_flags", None),
            ("metadata.measurement_source", "automated_simulated_replay"),
            ("metadata.simulated", True), ("metadata.device_data_id", "untraceable"),
            ("data.unit", "kPa"), ("data.value", True), ("deleted", True),
        ]
        for field, value in invalid:
            with self.subTest(field=field, value=value):
                await self.db.health_data.delete_many({})
                fact = self.blood_pressure_fact()
                await self.db.health_data.insert_one(fact)
                await self.db.health_data.update_one({"_id": fact["_id"]}, {"$set": {field: value}})
                row = await self.record_diastolic()
                self.assertEqual(row["metadata"]["health_alert"]["status"], "skipped")
        self.assertEqual(await self.db.health_data_alerts.count_documents({}), 0)

    async def test_current_component_unit_mismatch_does_not_create_clinical_alert(self):
        await self.prepare_blood_pressure()
        await self.db.health_data.insert_one(self.blood_pressure_fact())
        row = await self.record_diastolic(unit="kPa")
        self.assertEqual(row["metadata"]["health_alert"]["status"], "skipped")
        self.assertEqual(await self.db.health_data_alerts.count_documents({}), 0)

    async def test_pair_window_stays_backwards_and_does_not_skip_invalid_nearest_fact(self):
        await self.prepare_blood_pressure()
        await self.db.health_data.insert_many([
            self.blood_pressure_fact(at=self.now - timedelta(minutes=31)),
            self.blood_pressure_fact(at=self.now + timedelta(seconds=1))])
        self.assertEqual((await self.record_diastolic())["metadata"]["health_alert"]["status"], "skipped")
        await self.db.health_data.insert_one(self.blood_pressure_fact())
        invalid = self.blood_pressure_fact(at=self.now - timedelta(seconds=1))
        invalid["metadata"]["quality_flags"] = ["out_of_order"]
        await self.db.health_data.insert_one(invalid)
        self.assertEqual((await self.record_diastolic())["metadata"]["health_alert"]["status"], "skipped")
        self.assertEqual(await self.db.health_data_alerts.count_documents({}), 0)
