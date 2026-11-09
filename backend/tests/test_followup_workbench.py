"""Authorized workbench contract; real pagination uses a disposable local Mongo."""
import os
import importlib
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from bson import ObjectId
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.exceptions import AppBaseException
from app.models.health_record import FollowUpRecord
from app.services.followup_service import FollowupService

URI = os.environ.get("REHAB_TEST_WORKBENCH_MONGO_URI")
routes = importlib.import_module("app.api.routers.health_record_router")


def application(actor, service):
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    app.dependency_overrides[routes.get_current_user] = lambda: actor
    app.dependency_overrides[routes.get_followup_service] = lambda: service

    @app.exception_handler(AppBaseException)
    async def domain_error(request, error):
        return JSONResponse(status_code=error.status_code, content={"code": error.error_code})
    return app


class WorkbenchValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_medical_roles_cannot_enumerate_workbench(self):
        for role in ("patient", "researcher", "organization_admin"):
            service = SimpleNamespace(list_workbench=AsyncMock())
            app = application(SimpleNamespace(id="user", role=role), service)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/health-records/followup-workbench")
            self.assertEqual(response.status_code, 403)
            service.list_workbench.assert_not_awaited()

    async def test_invalid_dates_and_pagination_are_rejected_before_database(self):
        service = SimpleNamespace(list_workbench=AsyncMock())
        app = application(SimpleNamespace(id="doctor", role="doctor"), service)
        invalid = ({"start_date": "2026-11-09T00:00:00"}, {"skip": -1},
                   {"limit": 101}, {"sort_order": "random"}, {"status": "unknown"},
                   {"start_date": "2026-11-09T00:00:00Z", "end_date": "2026-11-08T00:00:00Z"})
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for params in invalid:
                result = await client.get("/api/health-records/followup-workbench", params=params)
                self.assertEqual(result.status_code, 422, params)
        service.list_workbench.assert_not_awaited()


@unittest.skipUnless(URI, "set isolated local REHAB_TEST_WORKBENCH_MONGO_URI")
class WorkbenchMongoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue(URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")))
        self.mongo = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.mongo["rehab_workbench_test_" + uuid4().hex]
        self.doctor, self.manager, self.other = map(str, (ObjectId(), ObjectId(), ObjectId()))
        self.patient, self.second, self.outside = map(str, (ObjectId(), ObjectId(), ObjectId()))
        await self.db.users.insert_many([
            {"_id": ObjectId(self.patient), "role": "patient", "name": "Alpha [1]",
             "practitioners": [self.doctor], "health_managers": [self.manager],
             "password": "must-not-be-returned", "email": "private@example.test"},
            {"_id": ObjectId(self.second), "role": "patient", "name": "Beta",
             "practitioners": [ObjectId(self.doctor)]},
            {"_id": ObjectId(self.outside), "role": "patient", "name": "Alpha [1] outsider",
             "practitioners": [self.other], "health_managers": [self.other]},
        ])
        self.service = FollowupService(self.db)
        self.actor = SimpleNamespace(id=self.doctor, role="doctor")
        self.app = application(self.actor, self.service)
        self.client = AsyncClient(transport=ASGITransport(app=self.app), base_url="http://test")
        self.when = datetime(2026, 11, 9, 8)

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.mongo.drop_database(self.db.name)
        self.mongo.close()

    async def insert(self, patient_id=None, *, when=None, status="scheduled", deleted=False, kind="phone"):
        model = FollowUpRecord(patient_id=patient_id or self.patient, created_by=self.doctor,
                               follow_up_type=kind, scheduled_date=when or self.when, status=status,
                               notes="review evidence stays on the existing detail path")
        document = model.to_mongo()
        document["deleted"] = deleted
        await self.db.followup_records.insert_one(document)
        return str(document["_id"])

    async def get(self, **params):
        return await self.client.get("/api/health-records/followup-workbench", params=params)

    async def test_more_than_100_records_have_true_total_and_stable_nonoverlapping_pages(self):
        ids = [await self.insert() for _ in range(125)]
        await self.insert(self.outside)
        await self.insert(deleted=True)
        first = await self.get(limit=100)
        second = await self.get(skip=100, limit=100)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["total"], 125)
        self.assertEqual(second.json()["total"], 125)
        returned = [row["id"] for row in first.json()["items"] + second.json()["items"]]
        self.assertEqual(returned, sorted(ids, reverse=True))
        self.assertEqual(len(set(returned)), 125)
        self.assertEqual(first.headers["cache-control"], "no-store")
        row = first.json()["items"][0]
        self.assertEqual(row["patient_name"], "Alpha [1]")
        self.assertNotIn("password", row)
        self.assertNotIn("email", row)
        empty = await self.get(skip=150, limit=10)
        self.assertEqual(empty.json()["items"], [])
        self.assertEqual(empty.json()["total"], 125)

    async def test_filters_total_and_items_share_half_open_utc_range(self):
        # Requested local [09 Nov 16:00, 10 Nov 16:00) is UTC [08:00, 08:00).
        first = await self.insert(status="in_review")
        await self.insert(when=self.when + timedelta(days=1), status="in_review")
        await self.insert(when=self.when - timedelta(microseconds=1), status="in_review")
        await self.insert(status="scheduled")
        await self.insert(self.second, status="in_review")
        result = await self.get(status="in_review", patient_name="[1]", follow_up_type="phone",
            start_date="2026-11-09T16:00:00+08:00", end_date="2026-11-10T16:00:00+08:00")
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["total"], 1)
        self.assertEqual([row["id"] for row in result.json()["items"]], [first])

    async def test_explicit_other_patient_is_denied_and_search_never_broadens_scope(self):
        await self.insert(self.outside)
        denied = await self.get(patient_id=self.outside)
        self.assertEqual(denied.status_code, 403)
        result = await self.get(patient_name="outsider")
        self.assertEqual(result.json()["total"], 0)
        self.assertEqual(result.json()["items"], [])

    async def test_health_manager_uses_own_assignment_and_doctor_empty_scope_is_empty(self):
        await self.insert()
        await self.insert(self.second)
        self.actor.id, self.actor.role = self.manager, "health_manager"
        result = await self.get()
        self.assertEqual(result.json()["total"], 1)
        self.assertEqual(result.json()["items"][0]["patient_id"], self.patient)
        self.assertEqual((await self.get(patient_id=self.second)).status_code, 403)
        self.actor.id, self.actor.role = str(ObjectId()), "doctor"
        self.assertEqual((await self.get()).json()["total"], 0)

    async def test_admin_and_ascending_order_use_same_authorized_query(self):
        early = await self.insert(when=self.when - timedelta(days=1))
        later = await self.insert(self.outside)
        self.actor.role = "admin"
        result = await self.get(sort_order="asc", limit=1)
        self.assertEqual(result.json()["total"], 2)
        self.assertEqual(result.json()["items"][0]["id"], early)
        selected = await self.get(patient_id=self.outside)
        self.assertEqual([row["id"] for row in selected.json()["items"]], [later])
