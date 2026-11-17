"""End-to-end F300 upload acceptance against an isolated Mongo replica set.

Run only with REHAB_TEST_VEEPOO_F300_URI pointed at a disposable local replica
set. The test uses real signed bearer tokens and the production router/services.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient

from app.api.routers.device_router import router as device_router
from app.api.routers.device_router import get_device_ingestion_service
from app.core.config import settings
from app.core.exceptions import AppBaseException
from app.main import app_exception_handler
from app.db.mongodb import get_database
from app.services.device_ingestion_service import DeviceIngestionService


URI = os.getenv("REHAB_TEST_VEEPOO_F300_URI")
pytestmark = pytest.mark.skipif(not URI, reason="requires isolated Mongo replica-set URI")


def _token(user_id):
    return jwt.encode({
        "sub": str(user_id), "token_type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def test_authenticated_f300_bind_upload_dedup_and_scope():
    # Fail closed unless this points at a loopback replica set. The database
    # name is generated per run and dropped at teardown.
    uri = urlsplit(URI)
    assert uri.hostname in {"127.0.0.1", "localhost", "::1"}
    assert uri.port and uri.port != 27017, "use a dedicated test port, not the app Mongo port"
    assert parse_qs(uri.query).get("directConnection") == ["true"], \
        "directConnection=true prevents discovery outside the isolated test port"
    sync_client = MongoClient(URI, serverSelectionTimeoutMS=3000)
    hello = sync_client.admin.command("hello")
    assert hello.get("setName"), "test Mongo must be a replica set"
    hosts = hello.get("hosts") or []
    assert hosts and all(host.startswith(("127.0.0.1:", "localhost:")) for host in hosts), \
        "test Mongo must be isolated on loopback"
    database_name = f"rehab_veepoo_f300_test_{uuid.uuid4().hex}"
    sync_db = sync_client[database_name]
    async_client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
    async_db = async_client[database_name]

    patient_id = ObjectId()
    other_patient_id = ObjectId()
    device_hardware_id = "F300-手环-设备-001"
    now = datetime.now(timezone.utc)
    sync_db.users.insert_many([
        {"_id": patient_id, "email": f"f300-{patient_id}@example.com", "name": "F300 Test",
         "role": "patient", "is_active": True, "created_at": now, "updated_at": now,
         "practitioners": [], "health_managers": []},
        {"_id": other_patient_id, "email": f"other-{other_patient_id}@example.com", "name": "Other",
         "role": "patient", "is_active": True, "created_at": now, "updated_at": now,
         "practitioners": [], "health_managers": []},
    ])

    service = DeviceIngestionService(db=async_db)
    app = FastAPI()
    app.add_exception_handler(AppBaseException, app_exception_handler)
    app.include_router(device_router, prefix="/api")
    app.dependency_overrides[get_database] = lambda: async_db
    app.dependency_overrides[get_device_ingestion_service] = lambda: service
    try:
        with TestClient(app) as client:
            patient_headers = {"Authorization": f"Bearer {_token(patient_id)}"}
            other_headers = {"Authorization": f"Bearer {_token(other_patient_id)}"}

            bind = client.post("/api/devices/bind", headers=patient_headers, json={
                "device_type": "手环", "name": "F300 实机测试", "manufacturer": "Veepoo",
                "model": "F300", "connection_type": "bluetooth",
                "settings": {"claimed_hardware_id": device_hardware_id},
            })
            assert bind.status_code == 200, bind.text
            device_id = bind.json()["id"]
            bound_document = sync_db.devices.find_one({"_id": ObjectId(device_id)})
            assert str(bound_document["patient_id"]) == str(patient_id)

            timestamp = datetime.now(timezone.utc).isoformat()
            payload = {
                "hardware_id": device_hardware_id,
                "readings": [{
                    "data_type": "heart_rate", "value": 82, "unit": "bpm",
                    "measured_at": timestamp, "sdk_type": 51,
                    "record_key": f"{device_hardware_id}:heart_rate:e2e-1",
                    "raw_payload": {"heartRate": 82},
                }],
            }
            upload_url = f"/api/devices/{device_id}/veepoo/readings"
            claimed_mismatch = {**payload, "hardware_id": "F3:00:AA:BB:CC:DD"}
            claim_rejected = client.post(upload_url, headers=patient_headers,
                                         json=claimed_mismatch)
            assert claim_rejected.status_code == 409, claim_rejected.text
            assert "veepoo_hardware_id" not in sync_db.devices.find_one(
                {"_id": ObjectId(device_id)}).get("settings", {})

            first = client.post(upload_url, headers=patient_headers, json=payload)
            assert first.status_code == 200, first.text
            assert first.json()["accepted_count"] == 1
            assert first.json()["clinical_facts_created"] == 1

            stored_device = sync_db.devices.find_one({"_id": ObjectId(device_id)})
            raw = list(sync_db.device_data.find({"device_id": device_id}))
            facts = list(sync_db.health_data.find({"patient_id": str(patient_id)}))
            assert stored_device["settings"]["veepoo_hardware_id"] == device_hardware_id
            assert len(raw) == 1 and raw[0]["metadata"]["source"] == "veepoo_wechat"
            assert len(facts) == 1
            assert facts[0]["data"]["type"] == "heart_rate"
            assert facts[0]["data"]["value"] == 82

            duplicate = client.post(upload_url, headers=patient_headers, json=payload)
            assert duplicate.status_code == 200, duplicate.text
            assert duplicate.json()["duplicate_count"] == 1
            assert sync_db.device_data.count_documents({"device_id": device_id}) == 1
            assert sync_db.health_data.count_documents({"patient_id": str(patient_id)}) == 1

            mismatched_hardware = {**payload, "hardware_id": "F3:00:AA:BB:CC:DD"}
            rejected_hardware = client.post(upload_url, headers=patient_headers,
                                            json=mismatched_hardware)
            assert rejected_hardware.status_code == 409, rejected_hardware.text

            # Simulate a binding change after the route loaded the expected
            # identifier but before the reading transaction begins.
            original_pin = service.pin_veepoo_hardware_id

            async def pin_then_change_binding(device, hardware_id, *, actor):
                pinned = await original_pin(device, hardware_id, actor=actor)
                sync_db.devices.update_one(
                    {"_id": ObjectId(device_id)},
                    {"$set": {"settings.veepoo_hardware_id": "F3:00:AA:BB:CC:DD"}})
                return pinned

            service.pin_veepoo_hardware_id = pin_then_change_binding
            raced_payload = {
                **payload,
                "readings": [{**payload["readings"][0],
                              "measured_at": datetime.now(timezone.utc).isoformat(),
                              "record_key": f"{device_hardware_id}:heart_rate:e2e-race"}],
            }
            changed_during_upload = client.post(
                upload_url, headers=patient_headers, json=raced_payload)
            service.pin_veepoo_hardware_id = original_pin
            assert changed_during_upload.status_code == 409, changed_during_upload.text

            denied = client.post(upload_url, headers=other_headers, json=payload)
            assert denied.status_code == 403, denied.text
            assert denied.json()["message"] == "无权访问该患者的数据"
            assert sync_db.device_data.count_documents({"device_id": device_id}) == 1
            assert sync_db.health_data.count_documents({"patient_id": str(patient_id)}) == 1
    finally:
        async_client.close()
        sync_client.drop_database(database_name)
        sync_client.close()
