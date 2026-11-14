"""Patient/account separation and request-database device policy regressions."""
import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from bson import ObjectId
from fastapi import HTTPException
import httpx
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

from app.core.device_access import device_patient_scope, ensure_device_access, resolve_device_patient
from app.core.patient_access import PatientAccessError, ensure_self_patient_access, resolve_self_patient_id
from app.patients.legacy import LegacyPatientIdentityError, LegacyPatientRepository
from app.services.device_service import DeviceService


class LegacySelfPolicyTests(unittest.TestCase):
    def test_only_a_patient_account_has_a_self_patient_relation(self):
        identifier = str(ObjectId())
        self.assertEqual(resolve_self_patient_id(SimpleNamespace(id=identifier, role="patient")), identifier)
        self.assertEqual(resolve_self_patient_id(SimpleNamespace(id=ObjectId(identifier), role="patient"), identifier), identifier)
        for role in ("doctor", "health_manager", "admin", "unknown"):
            with self.subTest(role=role), self.assertRaises(PatientAccessError):
                resolve_self_patient_id(SimpleNamespace(id=identifier, role=role), identifier)

    def test_missing_or_malformed_identifiers_never_become_a_self_identity(self):
        for identifier in (None, "", {}, []):
            with self.subTest(identifier=identifier), self.assertRaises(PatientAccessError):
                resolve_self_patient_id(SimpleNamespace(id=identifier, role="patient"))
        actor = SimpleNamespace(id="legacy-patient", role="patient")
        for target in ("other-patient", {}, []):
            with self.subTest(target=target), self.assertRaises(PatientAccessError):
                resolve_self_patient_id(actor, target)


class DeviceRolePolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_an_unrelated_role_cannot_use_a_matching_device_patient_id(self):
        actor = SimpleNamespace(id="collision", role="unknown")
        with self.assertRaises(HTTPException) as error:
            await ensure_device_access(None, {"patient_id": "collision"}, actor, ("doctor", "admin"))
        self.assertEqual(error.exception.status_code, 403)

    async def test_medical_binding_requires_an_explicit_patient(self):
        for role in ("doctor", "health_manager", "admin"):
            with self.subTest(role=role), self.assertRaises(HTTPException) as error:
                await resolve_device_patient(None, SimpleNamespace(id="actor", role=role))
            self.assertEqual(error.exception.status_code, 422)


URI = os.environ.get("REHAB_TEST_DEVICE_MONGO_URI")


@unittest.skipUnless(URI, "explicit isolated replica-set REHAB_TEST_DEVICE_MONGO_URI required")
class PatientDeviceMongoArchitectureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if not URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")):
            self.fail("only an explicit local isolated instance is allowed")
        self.mongo = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=4000)
        self.db = self.mongo["rehab_device_architecture_" + uuid4().hex]
        self.other = self.mongo["rehab_device_decoy_" + uuid4().hex]
        self.doctor_id, self.patient_id = ObjectId(), ObjectId()
        self.actor = SimpleNamespace(id=str(self.doctor_id), role="doctor")
        await self.db.users.insert_many([
            {"_id": self.doctor_id, "role": "doctor", "is_active": True},
            {"_id": self.patient_id, "role": "patient", "practitioners": [str(self.doctor_id)]},
        ])
        self.service = DeviceService(self.db)

    async def asyncTearDown(self):
        await self.mongo.drop_database(self.db.name)
        await self.mongo.drop_database(self.other.name)
        self.mongo.close()

    async def bind(self):
        return await self.service.bind_device(str(self.patient_id),
            {"device_type": "血压计", "name": "synthetic"}, actor=self.actor)

    async def test_injected_device_analysis_and_repair_stay_in_request_database(self):
        from app.core.dependencies import get_device_service, get_device_analysis_service, get_device_repair_service
        device = await get_device_service(db=self.db)
        analysis = await get_device_analysis_service(db=self.db)
        repair = await get_device_repair_service(db=self.db)
        with patch("app.services.device_service.get_db", AsyncMock(return_value=self.other)) as global_device, \
             patch("app.services.device_analysis_service.get_db", AsyncMock(return_value=self.other)) as global_analysis, \
             patch("app.services.device_repair_service.get_db", AsyncMock(return_value=self.other)) as global_repair:
            created = await device.bind_device(str(self.patient_id),
                {"device_type": "血压计", "name": "request-store"}, actor=self.actor)
            self.assertEqual(await self.db.devices.count_documents({}), 1)
            self.assertEqual(await self.other.devices.count_documents({}), 0)
            self.assertEqual(await analysis.detect_data_anomalies(created["_id"]), [])
            await self.db.device_repair_logs.insert_one({"device_id": created["_id"], "repair_time": 1})
            self.assertEqual(len(await repair.get_repair_history(created["_id"])), 1)
            global_device.assert_not_awaited()
            global_analysis.assert_not_awaited()
            global_repair.assert_not_awaited()

    async def test_doctor_and_health_manager_bind_to_patient_not_to_own_account(self):
        manager_id = ObjectId()
        await self.db.users.insert_one({"_id": manager_id, "role": "health_manager", "is_active": True})
        await self.db.users.update_one({"_id": self.patient_id}, {"$set": {"health_managers": [str(manager_id)]}})
        for actor in (self.actor, SimpleNamespace(id=str(manager_id), role="health_manager")):
            result = await self.service.bind_device(str(self.patient_id),
                {"device_type": "血压计", "name": "patient-only"}, actor=actor)
            self.assertEqual(result["patient_id"], str(self.patient_id))
            self.assertTrue(await self.service.unbind_device(str(self.patient_id), result["_id"], actor=actor))
        with self.assertRaises(PatientAccessError) as denied:
            await self.service.bind_device(str(self.doctor_id),
                {"device_type": "血压计", "name": "wrong-target"}, actor=self.actor)
        self.assertEqual(denied.exception.status_code, 404)
        self.assertEqual(await self.db.devices.count_documents({"patient_id": str(self.doctor_id)}), 0)

    async def test_api_management_flow_uses_selected_assigned_patient(self):
        from fastapi import FastAPI
        from app.api.routers.device_router import router
        from app.core.auth import get_current_active_user
        from app.core.dependencies import get_device_service
        from app.db.mongodb import get_database
        application = FastAPI()
        application.include_router(router, prefix="/api")
        application.dependency_overrides[get_current_active_user] = lambda: self.actor
        application.dependency_overrides[get_database] = lambda: self.db
        application.dependency_overrides[get_device_service] = lambda: self.service
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="https://synthetic") as client:
            missing = await client.post("/api/devices/bind", json={"device_type": "血压计", "name": "synthetic"})
            self.assertEqual(missing.status_code, 422)
            response = await client.post("/api/devices/bind", json={
                "patient_id": str(self.patient_id), "device_type": "血压计", "name": "managed"})
            self.assertEqual(response.status_code, 200, response.text)
            device = response.json()
            self.assertEqual(device["patient_id"], str(self.patient_id))
            listed = await client.get("/api/devices/")
            self.assertEqual(listed.status_code, 200, listed.text)
            self.assertEqual([row["id"] for row in listed.json()], [device["id"]])
            response = await client.delete(f"/api/devices/{device['id']}/unbind")
            self.assertEqual(response.status_code, 200, response.text)
            stored = await self.db.devices.find_one({"_id": ObjectId(device["id"])})
            self.assertEqual(stored["status"], "deleted")

    async def test_legacy_non_patient_binding_is_retained_for_admin_inventory_only(self):
        admin_id, device_id = ObjectId(), ObjectId()
        await self.db.users.insert_one({"_id": admin_id, "role": "admin", "is_active": True})
        await self.db.devices.insert_one({"_id": device_id, "patient_id": str(self.doctor_id), "status": "active"})
        admin = SimpleNamespace(id=str(admin_id), role="admin")
        await ensure_device_access(self.db, {"patient_id": str(self.doctor_id)}, admin, ("admin",))
        with self.assertRaises(PatientAccessError) as denied:
            await self.service.unbind_device(str(self.doctor_id), str(device_id), actor=admin)
        self.assertEqual(denied.exception.status_code, 404)
        self.assertEqual((await self.db.devices.find_one({"_id": device_id}))["status"], "active")

    async def test_cross_role_id_alias_is_rejected_for_scope_detail_and_self(self):
        await self.db.users.insert_one({"_id": str(self.patient_id), "role": "doctor"})
        for operation in (
            lambda: LegacyPatientRepository(self.db).get(str(self.patient_id)),
            lambda: device_patient_scope(self.db, self.actor),
            lambda: ensure_self_patient_access(self.db, SimpleNamespace(id=str(self.patient_id), role="patient")),
            self.bind,
        ):
            with self.assertRaises(LegacyPatientIdentityError):
                await operation()
        self.assertEqual(await self.db.devices.count_documents({}), 0)

    async def _revoke_during_fence(self, operation):
        reached, released = asyncio.Event(), asyncio.Event()
        original = AsyncIOMotorCollection.update_one
        paused = False
        async def intercept(collection, query, update, **options):
            nonlocal paused
            if (not paused and collection.database.name == self.db.name and collection.name == "users"
                    and query.get("_id") == self.patient_id and "_device_access_fence" in update.get("$inc", {})):
                paused = True
                reached.set()
                await asyncio.wait_for(released.wait(), 10)
            return await original(collection, query, update, **options)
        with patch.object(AsyncIOMotorCollection, "update_one", intercept):
            task = asyncio.create_task(operation())
            try:
                await asyncio.wait_for(reached.wait(), 10)
                await self.db.users.update_one({"_id": self.patient_id}, {"$set": {"practitioners": []}})
            finally:
                released.set()
            with self.assertRaises(PatientAccessError) as denied:
                await task
            self.assertEqual(denied.exception.status_code, 403)

    async def test_concurrent_assignment_removal_aborts_binding(self):
        await self._revoke_during_fence(self.bind)
        self.assertEqual(await self.db.devices.count_documents({}), 0)

    async def test_concurrent_assignment_removal_aborts_unbinding(self):
        device = await self.bind()
        await self._revoke_during_fence(lambda: self.service.unbind_device(
            str(self.patient_id), device["_id"], actor=self.actor))
        stored = await self.db.devices.find_one({"_id": ObjectId(device["_id"])})
        self.assertEqual(stored["status"], "active")
