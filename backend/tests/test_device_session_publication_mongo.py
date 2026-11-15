"""Device observation sessions bind only to a patient's current publication."""
import os
import unittest
import importlib
from datetime import datetime
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

from bson import ObjectId
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

from app.services.device_ingestion_service import DeviceIngestionError, DeviceIngestionService
from app.services.device_service import DeviceService
from app.api.routers.device_router import CollectionSessionStartRequest
router_module = importlib.import_module("app.api.routers.device_router")

URI = os.environ.get("REHAB_TEST_DEVICE_MONGO_URI")


class DeviceSessionRequestContractTests(unittest.TestCase):
    def test_old_exercise_id_is_rejected_instead_of_silently_ignored(self):
        with self.assertRaises(ValueError):
            CollectionSessionStartRequest.model_validate({"exercise_id": "old-id"})


@unittest.skipUnless(URI, "set REHAB_TEST_DEVICE_MONGO_URI to an isolated local replica set")
class DeviceSessionPublicationMongoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if urlsplit(URI).hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError("Only disposable local Mongo databases are allowed")
        self.client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.client["rehab_device_session_" + uuid4().hex]
        self.patient, self.other_patient = ObjectId(), ObjectId()
        self.doctor = ObjectId()
        self.device_id = ObjectId()
        self.plan_id, self.version_id, self.item_id = [ObjectId() for _ in range(3)]
        self.device = {"_id": self.device_id, "device_id": "SESSION-TEST",
                       "patient_id": str(self.patient), "status": "active",
                       "device_key": "test-only", "settings": {}}
        await self.db.devices.insert_one(self.device)
        await self.db.users.insert_many([
            {"_id": self.patient, "role": "patient", "is_active": True,
             "practitioners": [str(self.doctor)]},
            {"_id": self.doctor, "role": "doctor", "is_active": True},
        ])
        await self.db.rehab_plans.insert_one({
            "_id": self.plan_id, "patient_id": str(self.patient),
            "status": "active", "published_version_id": str(self.version_id),
        })
        await self.db.rehab_plan_versions.insert_one({
            "_id": self.version_id, "plan_id": str(self.plan_id),
            "patient_id": str(self.patient), "workflow": "patient_publication",
            "status": "published",
            "items_snapshot": [{"item_id": str(self.item_id), "name": "已发布运动项",
                                "intervention_type": "exercise"}],
        })
        await self.db.rehab_prescription_items.insert_one({
            "plan_id": str(self.plan_id), "version_id": str(self.version_id),
            "item_id": str(self.item_id), "name": "已发布处方项",
            "intervention_type": "exercise",
        })
        self.service = DeviceIngestionService(self.db)
        app = FastAPI()
        app.include_router(router_module.router)
        self.actor = SimpleNamespace(id=str(self.doctor), role="doctor", is_active=True)
        app.dependency_overrides[router_module.get_current_active_user] = lambda: self.actor
        app.dependency_overrides[router_module.get_database] = lambda: self.db
        app.dependency_overrides[router_module.get_device_service] = lambda: DeviceService(self.db)
        self.http = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.http.aclose()
        await self.client.drop_database(self.db.name)
        self.client.close()

    async def test_device_panel_options_expose_only_current_patient_publication_ids(self):
        await self.db.rehab_prescription_items.update_one(
            {"item_id": str(self.item_id)}, {"$set": {"name": "后来被修改的草稿内容"}})
        response = await self.http.get(f"/devices/{self.device_id}/publication-options")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [{
            "plan_id": str(self.plan_id), "plan_name": "康复方案",
            "version_id": str(self.version_id),
            "items": [{"item_id": str(self.item_id), "name": "已发布运动项"}],
        }])

    async def test_device_panel_options_do_not_truncate_after_200_plans(self):
        plans, versions, items = [], [], []
        for index in range(205):
            plan_id, version_id, item_id = [ObjectId() for _ in range(3)]
            plans.append({"_id": plan_id, "patient_id": str(self.patient),
                          "status": "active", "published_version_id": str(version_id),
                          "name": f"方案 {index}"})
            versions.append({"_id": version_id, "plan_id": str(plan_id),
                             "patient_id": str(self.patient),
                             "workflow": "patient_publication", "status": "published",
                             "items_snapshot": [{"item_id": str(item_id),
                                                 "name": f"运动 {index}",
                                                 "intervention_type": "exercise"}]})
        await self.db.rehab_plans.insert_many(plans)
        await self.db.rehab_plan_versions.insert_many(versions)

        response = await self.http.get(f"/devices/{self.device_id}/publication-options")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()), 206)
        self.assertEqual(len({row["plan_id"] for row in response.json()}), 206)

    async def test_device_panel_fails_closed_if_published_items_exceed_contract(self):
        extras = [{"item_id": str(ObjectId()), "name": f"运动 {index}",
                   "intervention_type": "exercise"} for index in range(200)]
        await self.db.rehab_plan_versions.update_one(
            {"_id": self.version_id}, {"$set": {"items_snapshot": extras + [
                {"item_id": str(self.item_id), "name": "已发布运动项",
                 "intervention_type": "exercise"}]}})
        response = await self.http.get(f"/devices/{self.device_id}/publication-options")
        self.assertEqual(response.status_code, 503, response.text)

    async def test_current_item_links_and_end_keeps_observation_out_of_old_progress(self):
        session = await self.service.start_collection_session(
            self.device, str(self.patient), plan_id=str(self.plan_id),
            version_id=str(self.version_id), prescription_item_id=str(self.item_id))
        self.assertEqual(session["linkage_status"], "linked")
        self.assertEqual(session["prescription_item_id"], str(self.item_id))

        await self.db.device_data.insert_one({
            "device_id": str(self.device_id), "timestamp": datetime.utcnow(),
            "metadata": {"source": "automated"}, "quality_flags": [],
        })
        ended = await self.service.end_collection_session(self.device, session["_id"])
        self.assertEqual(ended["summary"]["readings_count"], 1)
        plan = await self.db.rehab_plans.find_one({"_id": self.plan_id})
        self.assertNotIn("exercises", plan)
        self.assertNotIn("rehab_progress", await self.db.list_collection_names())

    async def test_other_patient_plan_is_rejected(self):
        with self.assertRaises(DeviceIngestionError) as caught:
            await self.service.start_collection_session(
                self.device, str(self.other_patient), plan_id=str(self.plan_id),
                version_id=str(self.version_id), prescription_item_id=str(self.item_id))
        self.assertEqual(caught.exception.status_code, 404)

    async def test_withdrawn_plan_or_version_is_rejected(self):
        await self.db.rehab_plans.update_one(
            {"_id": self.plan_id}, {"$set": {"status": "archived"}})
        with self.assertRaises(DeviceIngestionError):
            await self.service.start_collection_session(
                self.device, str(self.patient), plan_id=str(self.plan_id),
                version_id=str(self.version_id), prescription_item_id=str(self.item_id))
        await self.db.rehab_plans.update_one(
            {"_id": self.plan_id}, {"$set": {"status": "active"}})
        await self.db.rehab_plan_versions.update_one(
            {"_id": self.version_id}, {"$set": {"status": "withdrawn"}})
        with self.assertRaises(DeviceIngestionError):
            await self.service.start_collection_session(
                self.device, str(self.patient), plan_id=str(self.plan_id),
                version_id=str(self.version_id), prescription_item_id=str(self.item_id))

    async def test_snapshot_membership_wins_over_mutable_items_and_foreign_item_is_rejected(self):
        with self.assertRaises(DeviceIngestionError):
            await self.service.start_collection_session(
                self.device, str(self.patient), plan_id=str(self.plan_id),
                version_id=str(ObjectId()), prescription_item_id=str(self.item_id))
        await self.db.rehab_prescription_items.update_one(
            {"item_id": str(self.item_id)}, {"$set": {"version_id": str(ObjectId())}})
        linked = await self.service.start_collection_session(
            self.device, str(self.patient), plan_id=str(self.plan_id),
            version_id=str(self.version_id), prescription_item_id=str(self.item_id))
        self.assertEqual(linked["linkage_status"], "linked")
        await self.service.end_collection_session(self.device, linked["_id"])
        await self.db.rehab_plan_versions.update_one(
            {"_id": self.version_id},
            {"$set": {"items_snapshot": [{"item_id": str(ObjectId()),
                                             "name": "未发布运动项",
                                             "intervention_type": "exercise"}]}})
        with self.assertRaises(DeviceIngestionError):
            await self.service.start_collection_session(
                self.device, str(self.patient), plan_id=str(self.plan_id),
                version_id=str(self.version_id), prescription_item_id=str(self.item_id))


if __name__ == "__main__":
    unittest.main()
