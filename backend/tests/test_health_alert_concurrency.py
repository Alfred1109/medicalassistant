"""Three-state alert disposition: real Mongo CAS, legacy rows and idempotent retries."""
import asyncio
import os
import unittest
from uuid import uuid4

from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from app.models.health_data_threshold import HealthDataAlert
from app.schemas.health_data_threshold import AlertUpdate
from app.services.health_alert_service import HealthAlertService

URI = os.environ.get("REHAB_TEST_ALERT_MONGO_URI")


@unittest.skipUnless(URI, "set isolated local REHAB_TEST_ALERT_MONGO_URI")
class AlertConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue(URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")))
        self.client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.client["rehab_alert_cas_test_" + uuid4().hex]
        self.service = HealthAlertService(self.db)
        self.actor = str(ObjectId())
        self.row = HealthDataAlert(health_data_id=str(ObjectId()), patient_id=str(ObjectId()),
            data_type="vital_sign", value=140, vital_type="heart_rate").to_mongo()
        await self.db.health_data_alerts.insert_one(self.row)
        self.identifier = str(self.row["_id"])

    async def asyncTearDown(self):
        await self.client.drop_database(self.db.name)
        self.client.close()

    async def test_competing_dispositions_only_one_version_commits(self):
        results = await asyncio.gather(
            self.service.resolve_alert(self.identifier, self.actor, "处置", expected_version=0),
            self.service.ignore_alert(self.identifier, self.actor, "排除", expected_version=0),
            return_exceptions=True)
        self.assertEqual(sum(isinstance(result, HTTPException) and result.status_code == 409 for result in results), 1)
        row = await self.db.health_data_alerts.find_one({"_id": self.row["_id"]})
        self.assertEqual(row["version"], 1)
        self.assertEqual(len(row["timeline"]), 1)
        self.assertEqual(row["timeline"][0]["to_status"], row["status"])

    async def test_same_request_is_atomic_and_reuse_for_different_content_conflicts(self):
        results = await asyncio.gather(*[
            self.service.resolve_alert(self.identifier, self.actor, "处置", expected_version=0,
                                       request_id="same-request-001") for _ in range(4)])
        self.assertTrue(all(result.status == "resolved" and result.version == 1 for result in results))
        row = await self.db.health_data_alerts.find_one({"_id": self.row["_id"]})
        self.assertEqual(len(row["timeline"]), 1)
        with self.assertRaises(HTTPException) as conflict:
            await self.service.ignore_alert(self.identifier, self.actor, "排除", expected_version=0,
                                            request_id="same-request-001")
        self.assertEqual(conflict.exception.detail["code"], "ALERT_IDEMPOTENCY_CONFLICT")

    async def test_legacy_rows_gain_version_on_first_write_and_reopening_is_preserved(self):
        await self.db.health_data_alerts.update_one({"_id": self.row["_id"]}, {"$unset": {"version": "", "timeline": ""}})
        result = await self.service.ignore_alert(self.identifier, self.actor)
        self.assertEqual(result.version, 1)
        self.assertIsNotNone(result.resolved_at)
        result = await self.service.update_alert(self.identifier, AlertUpdate(status="active", expected_version=1), actor_id=self.actor)
        self.assertEqual(result.status, "active")
        self.assertEqual(result.version, 2)
        row = await self.db.health_data_alerts.find_one({"_id": self.row["_id"]})
        self.assertEqual([event["to_status"] for event in row["timeline"]], ["ignored", "active"])

    async def test_legacy_callers_without_expected_version_still_use_cas(self):
        original = self.service.alerts
        barrier = asyncio.Event()
        reads = 0

        class SnapshotReads:
            async def find_one(inner, *args, **kwargs):
                nonlocal reads
                row = await original.find_one(*args, **kwargs)
                reads += 1
                if reads == 2:
                    barrier.set()
                await barrier.wait()
                return row

            async def update_one(inner, *args, **kwargs):
                return await original.update_one(*args, **kwargs)

        self.service.alerts = SnapshotReads()
        results = await asyncio.gather(
            self.service.resolve_alert(self.identifier, self.actor),
            self.service.ignore_alert(self.identifier, self.actor), return_exceptions=True)
        self.assertEqual(sum(isinstance(result, HTTPException) and result.status_code == 409 for result in results), 1)
        self.assertEqual((await original.find_one({"_id": self.row["_id"]}))["version"], 1)

    async def test_null_version_is_legacy_zero_but_invalid_versions_fail_closed(self):
        await self.db.health_data_alerts.update_one({"_id": self.row["_id"]}, {"$set": {"version": None}})
        self.assertEqual((await self.service.resolve_alert(self.identifier, self.actor)).version, 1)
        for invalid in ["one", -1, True]:
            await self.db.health_data_alerts.update_one({"_id": self.row["_id"]}, {"$set": {"version": invalid}})
            with self.assertRaises(HTTPException) as conflict:
                await self.service.ignore_alert(self.identifier, self.actor)
            self.assertEqual(conflict.exception.detail["code"], "ALERT_VERSION_CONFLICT")
            row = await self.db.health_data_alerts.find_one({"_id": self.row["_id"]})
            self.assertEqual(len(row["timeline"]), 1)
            self.assertEqual(row["status"], "resolved")

    async def test_retry_after_later_change_returns_current_state_without_reapplying(self):
        await self.service.resolve_alert(self.identifier, self.actor, expected_version=0, request_id="old-request-001")
        await self.service.update_alert(self.identifier, AlertUpdate(status="active", expected_version=1), actor_id=self.actor)
        replayed = await self.service.resolve_alert(self.identifier, self.actor, expected_version=0, request_id="old-request-001")
        self.assertEqual(replayed.status, "active")
        self.assertEqual(replayed.version, 2)
        self.assertEqual(len((await self.db.health_data_alerts.find_one({"_id": self.row["_id"]}))["timeline"]), 2)
