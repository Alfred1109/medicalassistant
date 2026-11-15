"""Real Mongo projection, patient isolation, history retention and paging."""
import os
import unittest
from datetime import datetime, timedelta
from uuid import uuid4
from types import SimpleNamespace

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import AsyncClient, ASGITransport

from app.schemas.followup import FollowUpRecordCreate
from app.schemas.health_record import HealthDataCreate, HealthRecordCreate
from app.services.followup_service import FollowupService
from app.services.health_record_service import HealthRecordService
from app.services.medical_timeline import timeline_pipeline
from app.db.indexes import ensure_timeline_indexes
from app.core.exceptions import AppBaseException
from app.patients.repository import ClinicalPatientRepository, STATE, STATE_ID, PATIENTS
from app.api.routers.health_record_router import router, get_current_user, get_health_record_service


URI = os.environ.get("REHAB_TEST_TIMELINE_MONGO_URI")


@unittest.skipUnless(URI, "set REHAB_TEST_TIMELINE_MONGO_URI to an isolated local Mongo")
class TimelineProjectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue(URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")))
        self.client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.client["rehab_timeline_test_" + uuid4().hex]
        self.patient, self.other, self.actor = (str(ObjectId()) for _ in range(3))
        self.now = datetime(2026, 11, 1, 12)
        self.service = HealthRecordService(self.db)

    async def asyncTearDown(self):
        await self.client.drop_database(self.db.name)
        self.client.close()

    async def source(self, collection, **values):
        row = {"_id": ObjectId(), "patient_id": self.patient, **values}
        await self.db[collection].insert_one(row)
        return row

    async def history(self, kind, source_id=None, **values):
        return await self.source("medical_timelines", item_type=kind,
            related_ids=[str(source_id)] if source_id else [], title="旧快照",
            occurred_at=self.now, **values)

    async def test_live_facts_include_all_sources_and_exclude_other_patients_and_deleted(self):
        sources = {"health_records": {"title": "病历", "created_at": self.now},
            "followup_records": {"follow_up_type": "phone", "status": "in_review", "scheduled_date": self.now},
            "health_data": {"data_type": "vital_sign", "recorded_at": self.now, "source": "device",
                            "device_id": "device-1", "data": {"type": "heart_rate", "value": 72, "unit": "bpm"},
                            "metadata": {"quality_flags": ["out_of_range:heart_rate"], "device_data_id": "raw-1"}},
            "rehab_assessments": {"assessment_type": "initial", "created_at": self.now},
            "icf_assessments": {"review_status": "pending", "assessed_at": self.now}}
        expected = set()
        for name, values in sources.items():
            row = await self.source(name, **values)
            expected.add(f"{name}:objectId:{row['_id']}")
            await self.source(name, patient_id=self.other, **values)
            await self.source(name, deleted=True, **values)
        rows = await self.service.get_medical_timeline(self.patient)
        self.assertEqual({item.id for item in rows}, expected)
        self.assertTrue(all(item.patient_id == self.patient for item in rows))
        device = next(item for item in rows if item.item_type == "health_data_vital_sign")
        self.assertEqual(device.data["metadata"]["device_id"], "device-1")
        self.assertEqual(device.data["metadata"]["quality_flags"], ["out_of_range:heart_rate"])
        self.assertEqual(device.data["metadata"]["device_data_id"], "raw-1")
        self.assertEqual(device.data["metadata"]["values"]["value"], 72)
        self.assertEqual(await self.db.medical_timelines.count_documents({}), 0)

    async def test_current_deduplicates_exact_sources_including_deleted_and_preserves_orphans(self):
        record = await self.source("health_records", title="当前内容", created_at=self.now)
        deleted = await self.source("followup_records", deleted=True, status="completed", scheduled_date=self.now)
        foreign = await self.source("health_records", patient_id=self.other, title="其他患者私密内容", created_at=self.now)
        await self.history("health_record", record["_id"])
        await self.history("health_record", record["_id"])
        await self.history("follow_up", deleted["_id"])
        orphan = await self.history("health_record", ObjectId())
        foreign_reference = await self.history("health_record", foreign["_id"])
        await self.history("health_record", record["_id"], patient_id=self.other)
        current = await self.service.get_medical_timeline(self.patient)
        self.assertEqual({row.id for row in current}, {f"health_records:objectId:{record['_id']}",
            f"medical_timelines:objectId:{orphan['_id']}", f"medical_timelines:objectId:{foreign_reference['_id']}"})
        self.assertTrue(all(row.data["source"]["orphan"] for row in current if row.data["source"]["view"] == "history"))
        self.assertNotIn("其他患者私密内容", str(current))
        history = await self.service.get_medical_timeline(self.patient, view="history")
        self.assertEqual(len(history), 5)
        self.assertEqual(sum(not item.data["source"]["orphan"] for item in history), 3)
        # Read views do not rewrite old duplicates, snapshots or soft-deleted facts.
        self.assertEqual(await self.db.medical_timelines.count_documents({}), 6)

    async def test_union_filters_then_stable_pagination_and_preserves_update_time_basis(self):
        await self.source("health_records", title="更正病历", created_at=self.now - timedelta(days=10), updated_at=self.now)
        await self.source("followup_records", status="scheduled", scheduled_date=self.now - timedelta(days=2))
        await self.source("health_data", data_type="lab_result", recorded_at=self.now - timedelta(days=1))
        whole = await self.service.get_medical_timeline(self.patient)
        pages = [*(await self.service.get_medical_timeline(self.patient, skip=0, limit=2)),
                 *(await self.service.get_medical_timeline(self.patient, skip=2, limit=2))]
        self.assertEqual([item.id for item in pages], [item.id for item in whole])
        self.assertEqual(whole[0].data["original_timestamp"], self.now - timedelta(days=10))
        self.assertEqual(whole[0].data["metadata"]["timestamp_basis"], "updated_at_then_created_at")
        filtered = await self.service.get_medical_timeline(self.patient,
            start_date=self.now - timedelta(days=1), end_date=self.now, item_types=["lab_result"])
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].item_type, "health_data_lab_result")

    async def test_history_filters_paging_unknown_types_and_missing_dates(self):
        unknown = await self.history("historical_custom_type")
        await self.source("medical_timelines", item_type="medication", title="无日期旧记录")
        await self.history("follow_up")
        rows = await self.service.get_medical_timeline(self.patient, view="history")
        self.assertEqual(len(rows), 3)
        self.assertIsNone(rows[-1].timestamp)
        only = await self.service.get_medical_timeline(self.patient, view="history",
            start_date=self.now, end_date=self.now, item_types=["historical_custom_type"], limit=1)
        self.assertEqual(only[0].id, f"medical_timelines:objectId:{unknown['_id']}")
        page = await self.service.get_medical_timeline(self.patient, view="history", skip=1, limit=1)
        self.assertEqual(page[0].id, rows[1].id)

    async def test_followup_changes_are_visible_without_rewriting_old_snapshot(self):
        followup = await self.source("followup_records", follow_up_type="online", status="scheduled", scheduled_date=self.now)
        snapshot = await self.history("follow_up", followup["_id"])
        await self.db.followup_records.update_one({"_id": followup["_id"]}, {"$set": {"status": "completed", "actual_date": self.now + timedelta(days=1)}})
        rows = await self.service.get_medical_timeline(self.patient)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].data["metadata"]["status"], "completed")
        self.assertEqual(rows[0].timestamp, self.now + timedelta(days=1))
        self.assertEqual(await self.db.medical_timelines.find_one({"_id": snapshot["_id"]}), snapshot)

    async def test_lab_and_composite_vital_values_survive_replacing_old_replica(self):
        lab = await self.source("health_data", data_type="lab_result", recorded_at=self.now,
            data={"test_name": "肌酐", "result_value": 88, "unit": "µmol/L"})
        bp = await self.source("health_data", data_type="vital_sign", recorded_at=self.now,
            data={"type": "blood_pressure", "value": {"systolic": 120, "diastolic": 80}, "unit": "mmHg"})
        await self.history("health_data_lab_result", lab["_id"])
        await self.history("health_data_vital_sign", bp["_id"])
        rows = await self.service.get_medical_timeline(self.patient)
        self.assertEqual(len(rows), 2)
        lab_row = next(row for row in rows if row.item_type == "health_data_lab_result")
        bp_row = next(row for row in rows if row.item_type == "health_data_vital_sign")
        self.assertIn("肌酐: 88 µmol/L", lab_row.description)
        self.assertIn("systolic: 120", bp_row.description)
        self.assertIn("diastolic: 80", bp_row.description)
        self.assertEqual(bp_row.data["metadata"]["values"]["value"], {"systolic": 120, "diastolic": 80})

    async def test_new_business_records_never_create_timeline_replicas(self):
        await self.service.create_health_record(HealthRecordCreate(patient_id=self.patient,
            record_type="medical_record", title="新记录", content="真实记录", created_by=self.actor))
        await self.service.create_health_data(HealthDataCreate(patient_id=self.patient, data_type="vital_sign",
            data_content={"type": "heart_rate", "value": 72}, source="manual", recorded_by=self.actor))
        await FollowupService(self.db).create_followup_record(FollowUpRecordCreate(patient_id=self.patient,
            follow_up_type="phone", scheduled_date=self.now, created_by=self.actor, provider_id=self.actor, description="安排随访"))
        self.assertEqual(await self.db.medical_timelines.count_documents({}), 0)
        self.assertEqual(len(await self.service.get_medical_timeline(self.patient)), 3)

    async def test_historical_source_lookup_uses_native_id_indexes(self):
        for source, kind in (("health_records", "health_record"), ("followup_records", "follow_up"),
                             ("health_data", "health_data_vital_sign"),
                             ("rehab_assessments", "rehabilitation_assessment"),
                             ("icf_assessments", "icf_assessment")):
            row = await self.source(source, created_at=self.now)
            await self.history(kind, row["_id"])
        # Unrelated facts must not turn each historical lookup into a table scan.
        await self.db.health_records.insert_many([{"_id": ObjectId(), "patient_id": self.other}
                                                  for _ in range(1000)])
        collection, pipeline = timeline_pipeline(self.patient, view="history")
        explanation = await self.db.command("explain", {"aggregate": collection, "pipeline": pipeline, "cursor": {}},
                                            verbosity="executionStats")
        lookups = [stage for stage in explanation.get("stages", []) if "$lookup" in stage]
        self.assertEqual(len(lookups), 5)
        for lookup in lookups:
            self.assertIn("_id_", lookup.get("indexesUsed", []), lookup)
            self.assertEqual(lookup.get("collectionScans"), 0, lookup)

    async def test_same_literal_different_id_types_are_distinct_and_history_is_ambiguous(self):
        identifier = ObjectId()
        await self.db.health_records.insert_many([
            {"_id": identifier, "patient_id": self.patient, "title": "ObjectId事实", "created_at": self.now},
            {"_id": str(identifier), "patient_id": self.patient, "title": "字符串事实", "created_at": self.now}])
        await self.history("health_record", identifier)
        rows = await self.service.get_medical_timeline(self.patient)
        self.assertEqual(len(rows), 3)
        self.assertEqual(len({row.id for row in rows}), 3)
        historical = next(row for row in rows if row.data["source"]["view"] == "history")
        self.assertTrue(historical.data["source"]["ambiguous"])
        self.assertFalse(historical.data["source"]["orphan"])

    async def test_source_indexes_reuse_existing_prefix_and_never_create_collections(self):
        await self.source("health_records", title="记录")
        await self.history("historical")
        await self.db.health_records.create_index([("patient_id", 1), ("created_at", -1)], name="existing_patient_history")
        before = await self.db.list_collection_names()
        self.assertTrue(await ensure_timeline_indexes(self.db))
        self.assertEqual(sorted(await self.db.list_collection_names()), sorted(before))
        existing = await self.db.health_records.index_information()
        self.assertNotIn("timeline_patient_query", existing)
        history_indexes = await self.db.medical_timelines.index_information()
        self.assertFalse(history_indexes["timeline_patient_query"].get("unique", False))
        self.assertTrue(await ensure_timeline_indexes(self.db))
        self.assertEqual(await self.db.medical_timelines.index_information(), history_indexes)

    async def test_canonical_patient_resolves_self_then_reads_own_timeline_and_rechecks_revocation(self):
        account_id = str(ObjectId())
        self.assertNotEqual(account_id, self.patient)
        await self.db[STATE].insert_one({"_id": STATE_ID, "mode": "canonical", "schema_version": 1})
        await self.db.users.insert_one({"_id": ObjectId(account_id), "role": "patient", "is_active": True})
        await self.db[PATIENTS].insert_one({"_id": ObjectId(self.patient), "patient_id": self.patient,
            "status": "active", "name": "合成患者", "practitioners": [], "health_managers": []})
        repository = ClinicalPatientRepository(self.db)
        await repository.bind_account(self.patient, account_id=account_id, reviewer="test-reviewer", evidence_reference="synthetic-binding")
        await self.source("health_data", data_type="vital_sign", recorded_at=self.now, data={"value": 72})
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=account_id, role="patient")
        app.dependency_overrides[get_health_record_service] = lambda: self.service

        @app.exception_handler(AppBaseException)
        async def domain_error(request, error):
            return JSONResponse(status_code=error.status_code, content={"code": error.error_code})

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://timeline-test") as client:
            context = await client.get("/api/health-records/patient-context")
            self.assertEqual(context.status_code, 200, context.text)
            self.assertEqual(context.json()["patient_id"], self.patient)
            result = await client.get("/api/health-records/timeline/" + context.json()["patient_id"])
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(len(result.json()), 1)
            for target in (account_id, self.other):
                for view in ("current", "history"):
                    denied = await client.get(f"/api/health-records/timeline/{target}", params={"view": view})
                    self.assertEqual(denied.status_code, 403, denied.text)
            reversed_dates = await client.get(f"/api/health-records/timeline/{self.patient}",
                params={"start_date": "2026-11-02T00:00:00+08:00", "end_date": "2026-11-01T00:00:00"})
            self.assertEqual(reversed_dates.status_code, 422, reversed_dates.text)
            mixed_dates = await client.get(f"/api/health-records/timeline/{self.patient}",
                params={"start_date": "2026-11-01T00:00:00", "end_date": "2026-11-02T00:00:00+08:00"})
            self.assertEqual(mixed_dates.status_code, 200, mixed_dates.text)
            await repository.disable_account_link(self.patient, reviewer="test-reviewer", evidence_reference="revoke-test")
            self.assertEqual((await client.get("/api/health-records/patient-context")).status_code, 403)
            self.assertEqual((await client.get(f"/api/health-records/timeline/{self.patient}")).status_code, 403)
