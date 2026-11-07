"""Audit API contract checks; Mongo tests require an explicit isolated loopback URI.

Run with MEDICALASSISTANT_AUDIT_TEST_MONGO_URL=mongodb://127.0.0.1:37018.
Every integration test owns and removes a unique audit_contract_* database.
"""
import os
import unittest
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from bson import ObjectId
from fastapi import FastAPI
from jose import jwt
from motor.motor_asyncio import AsyncIOMotorClient
from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import ValidationError
from pymongo.errors import AutoReconnect

from app.api.routers.audit_log_router import router
from app.core.config import settings
from app.db.mongodb import get_database
from app.schemas.audit_log import AuditLogCreate, AuditLogFilter
from app.services.audit_log_service import AuditLogService


MONGO_URI = os.environ.get("MEDICALASSISTANT_AUDIT_TEST_MONGO_URL")


class AuditSchemaTests(unittest.TestCase):
    def test_naive_legacy_dates_and_explicit_offsets_normalize_to_utc(self):
        query = AuditLogFilter(
            start_date="2026-11-30T00:00:00+08:00", end_date="2026-11-30T04:00:00",
        )
        self.assertEqual(query.start_date, datetime(2026, 11, 29, 16, tzinfo=timezone.utc))
        self.assertEqual(query.end_date, datetime(2026, 11, 30, 4, tzinfo=timezone.utc))

    def test_reversed_range_is_rejected(self):
        with self.assertRaises(ValidationError):
            AuditLogFilter(start_date="2026-12-01T00:00:00Z", end_date="2026-11-01T00:00:00Z")


class AuditMetadataTests(unittest.IsolatedAsyncioTestCase):
    async def test_additional_details_cannot_replace_authoritative_permission_identity(self):
        service = AuditLogService(MagicMock())
        service.create_log = AsyncMock(return_value={})
        await service.log_permission_change(
            "actor", "target", "patient:read", "grant",
            details={"permission": "forged", "target_user_id": "other", "note": "test"},
        )
        entry = service.create_log.await_args.args[0]
        self.assertEqual(entry.details, {
            "permission": "patient:read", "target_user_id": "target", "note": "test",
        })


@unittest.skipUnless(MONGO_URI, "explicit isolated MongoDB test URI required")
class AuditLogRouteIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if urlparse(MONGO_URI).hostname not in {"127.0.0.1", "localhost", "::1"}:
            self.fail("Audit contract tests only allow an isolated loopback MongoDB")
        self.mongo = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        await self.mongo.admin.command("ping")
        self.database_name = "audit_contract_" + uuid4().hex
        self.db = self.mongo[self.database_name]
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api")

        async def test_database():
            yield self.db

        self.app.dependency_overrides[get_database] = test_database
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://audit-test",
        )
        now = datetime.now(timezone.utc)
        self.admin_id, self.patient_id = str(ObjectId()), str(ObjectId())
        for user_id, role in [(self.admin_id, "admin"), (self.patient_id, "patient")]:
            await self.db.users.insert_one({
                "_id": ObjectId(user_id), "name": "Audit test " + role,
                "email": role + "@example.com", "role": role, "is_active": True,
                "created_at": now, "updated_at": now,
            })
        self.log_id = ObjectId()
        await self.db.audit_logs.insert_one({
            "_id": self.log_id, "user_id": self.patient_id, "action": "view",
            "resource_type": "patient", "resource_id": "fixture-patient",
            "status": "success", "created_at": datetime(2026, 11, 30, 4, tzinfo=timezone.utc),
            "details": {"note": "Synthetic audit fixture"},
        })

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.mongo.drop_database(self.database_name)
        self.mongo.close()

    def headers(self, user_id):
        token = jwt.encode(
            {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
             "token_type": "access"},
            settings.SECRET_KEY, algorithm=settings.ALGORITHM,
        )
        return {"Authorization": "Bearer " + token}

    async def test_admin_list_is_paginated_and_records_query(self):
        response = await self.client.get(
            "/api/audit-logs/", params={"resource_type": "patient", "skip": 0, "limit": 1},
            headers=self.headers(self.admin_id),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["items"][0]["id"], str(self.log_id))
        query_log = await self.db.audit_logs.find_one({"user_id": self.admin_id, "action": "query"})
        self.assertIsNotNone(query_log)
        self.assertEqual(query_log["details"]["results_count"], 1)

    async def test_admin_detail_records_view_and_has_utc_timestamp(self):
        response = await self.client.get(
            f"/api/audit-logs/{self.log_id}", headers=self.headers(self.admin_id),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["id"], str(self.log_id))
        self.assertIn(response.json()["created_at"][-6:], {"+00:00", "00:00Z"})
        self.assertIsNotNone(await self.db.audit_logs.find_one({
            "user_id": self.admin_id, "action": "view", "resource_id": str(self.log_id),
        }))

    async def test_admin_recent_other_user_records_query(self):
        response = await self.client.get(
            f"/api/audit-logs/user/{self.patient_id}/recent", headers=self.headers(self.admin_id),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()[0]["id"], str(self.log_id))
        self.assertIsNotNone(await self.db.audit_logs.find_one({
            "user_id": self.admin_id, "action": "query", "resource_id": self.patient_id,
        }))

    async def test_patient_cannot_read_global_list_and_denial_is_audited(self):
        response = await self.client.get("/api/audit-logs/", headers=self.headers(self.patient_id))
        self.assertEqual(response.status_code, 403, response.text)
        denied = await self.db.audit_logs.find_one({
            "user_id": self.patient_id, "resource_type": "permission", "status": "failure",
        })
        self.assertIsNotNone(denied)
        self.assertEqual(denied["details"]["permission"], "system:admin")

    async def test_patient_recent_is_self_only(self):
        own = await self.client.get(
            f"/api/audit-logs/user/{self.patient_id}/recent", headers=self.headers(self.patient_id),
        )
        self.assertEqual(own.status_code, 200, own.text)
        own_query = await self.db.audit_logs.find_one({
            "user_id": self.patient_id, "action": "query", "resource_type": "audit_log",
        })
        self.assertTrue(own_query["details"]["self_query"])
        other = await self.client.get(
            f"/api/audit-logs/user/{self.admin_id}/recent", headers=self.headers(self.patient_id),
        )
        self.assertEqual(other.status_code, 403, other.text)

    async def test_unauthenticated_access_is_rejected(self):
        response = await self.client.get("/api/audit-logs/")
        self.assertEqual(response.status_code, 401, response.text)

    async def test_inclusive_timezone_range_uses_real_bson_dates(self):
        response = await self.client.get(
            "/api/audit-logs/", headers=self.headers(self.admin_id), params={
                "resource_type": "patient", "start_date": "2026-11-30T00:00:00+08:00",
                "end_date": "2026-11-30T23:59:59.999+08:00",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["total"], 1)

    async def test_invalid_dates_range_sort_and_id_are_client_errors(self):
        for params in [
            {"start_date": "not-a-date"},
            {"start_date": "2026-12-01T00:00:00Z", "end_date": "2026-11-01T00:00:00Z"},
            {"sort_order": 0}, {"sort_by": "$where"}, {"limit": 101}, {"skip": -1},
        ]:
            response = await self.client.get(
                "/api/audit-logs/", params=params, headers=self.headers(self.admin_id),
            )
            self.assertEqual(response.status_code, 422, (params, response.text))
        response = await self.client.get(
            "/api/audit-logs/not-an-object-id", headers=self.headers(self.admin_id),
        )
        self.assertEqual(response.status_code, 422, response.text)

    async def test_well_formed_missing_id_is_not_found(self):
        missing_id = str(ObjectId())
        response = await self.client.get(
            f"/api/audit-logs/{missing_id}", headers=self.headers(self.admin_id),
        )
        self.assertEqual(response.status_code, 404, response.text)
        self.assertIsNotNone(await self.db.audit_logs.find_one({
            "user_id": self.admin_id, "action": "view", "resource_id": missing_id, "status": "failure",
        }))

    async def test_audit_storage_failure_does_not_return_protected_records(self):
        with patch.object(AsyncIOMotorCollection, "insert_one", new=AsyncMock(side_effect=AutoReconnect("test outage"))):
            response = await self.client.get(
                "/api/audit-logs/", params={"resource_type": "patient"}, headers=self.headers(self.admin_id),
            )
        self.assertEqual(response.status_code, 503, response.text)
        self.assertNotIn("Synthetic audit fixture", response.text)
        self.assertNotIn("test outage", response.text)

    async def test_same_timestamp_pagination_is_deterministic(self):
        timestamp = datetime(2026, 11, 30, tzinfo=timezone.utc)
        ids = [ObjectId(), ObjectId(), ObjectId()]
        for identifier in ids:
            await self.db.audit_logs.insert_one({
                "_id": identifier, "user_id": self.patient_id, "action": "view",
                "resource_type": "tie-test", "status": "success", "created_at": timestamp,
            })
        response = await self.client.get(
            "/api/audit-logs/", headers=self.headers(self.admin_id),
            params={"resource_type": "tie-test", "skip": 1, "limit": 1, "sort_order": -1},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["total"], 3)
        self.assertEqual(response.json()["items"][0]["id"], str(sorted(ids, reverse=True)[1]))

    async def test_range_boundaries_are_inclusive_at_bson_millisecond_precision(self):
        begin = datetime(2026, 11, 29, 16, tzinfo=timezone.utc)
        end = datetime(2026, 11, 30, 15, 59, 59, 999000, tzinfo=timezone.utc)
        for label, timestamp in [
            ("start", begin), ("end", end),
            ("before", begin - timedelta(milliseconds=1)), ("after", end + timedelta(milliseconds=1)),
        ]:
            await self.db.audit_logs.insert_one({
                "user_id": self.patient_id, "action": label, "resource_type": "boundary-test",
                "status": "success", "created_at": timestamp,
            })
        response = await self.client.get(
            "/api/audit-logs/", headers=self.headers(self.admin_id), params={
                "resource_type": "boundary-test", "start_date": begin.isoformat(), "end_date": end.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual({row["action"] for row in response.json()["items"]}, {"start", "end"})

    async def test_service_write_returns_public_id_without_bson_internal_id(self):
        result = await AuditLogService(self.db).create_log(AuditLogCreate(
            user_id=self.admin_id, action="query", resource_type="service-test",
        ))
        self.assertNotIn("_id", result)
        self.assertTrue(ObjectId.is_valid(result["id"]))
        self.assertEqual(result["created_at"].utcoffset(), timedelta(0))
