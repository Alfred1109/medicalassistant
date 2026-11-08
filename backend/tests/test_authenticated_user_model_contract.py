"""Mounted APIs consume the actual UserResponse authentication contract.

Domain services are isolated; tests verify actor attribution and existing role /
ownership denials rather than substituting Mongo dictionaries for authentication.
"""
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from bson import ObjectId

from app.core.auth import get_current_user
from app.core.dependencies import get_health_alert_service
from app.db.mongodb import get_database
from app.main import app
from app.schemas.user import UserResponse


class AuthenticatedUserModelContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.user = UserResponse(id=str(ObjectId()), name="Reviewed actor", email="actor@example.com",
            role="doctor", createdAt=datetime.utcnow(), updatedAt=datetime.utcnow())
        self.db = MagicMock()
        app.dependency_overrides[get_current_user] = lambda: self.user
        app.dependency_overrides[get_database] = lambda: self.db
        self.client = httpx.AsyncClient(app=app, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()

    async def test_patient_dashboard_endpoints_receive_canonical_actor(self):
        self.user.role = "patient"
        cases = (("dashboard-data", "get_all_dashboard_data", {}),
                 ("health-metrics", "get_health_metrics", []),
                 ("todo-items", "get_todo_items", []),
                 ("rehab-progress", "get_rehab_progress", {"progress": 5}))
        for path, method, value in cases:
            with self.subTest(path=path), patch("app.api.routers.patient_router.DashboardService." + method,
                                               new=AsyncMock(return_value=value)) as domain:
                result = await self.client.get("/api/patients/" + path)
                self.assertEqual(result.status_code, 200)
                domain.assert_awaited_once_with(self.db, self.user.id)
        self.user.role = "doctor"
        self.assertEqual((await self.client.get("/api/patients/dashboard-data")).status_code, 403)

    async def test_report_creation_uses_authenticated_actor_and_existing_role_guard(self):
        body = dict(name="Report", reportId="existing-report", frequency="daily",
                    recipients=["recipient@example.com"], format="pdf", createdBy="forged")
        with patch("app.api.routers.report_scheduler_router.report_scheduler_service.create_schedule",
                   new=AsyncMock(return_value="schedule-id")) as domain:
            self.assertEqual((await self.client.post("/api/report-schedules", json=body)).status_code, 200)
            self.assertEqual(domain.call_args.args[0]["createdBy"], self.user.id)
            self.user.role = "patient"
            self.assertEqual((await self.client.post("/api/report-schedules", json=body)).status_code, 403)
            self.assertEqual(domain.await_count, 1)

    async def test_report_owner_guard_rejects_another_actor(self):
        with patch("app.api.routers.report_scheduler_router.report_scheduler_service.get_schedule",
                   new=AsyncMock(return_value={"createdBy": str(ObjectId())})), patch(
                   "app.api.routers.report_scheduler_router.report_scheduler_service.update_schedule",
                   new=AsyncMock()) as domain:
            self.assertEqual((await self.client.put("/api/report-schedules/existing", json={"name": "forged"})).status_code, 403)
            domain.assert_not_awaited()

    async def test_filter_creation_attributes_actor_and_denies_global_scope(self):
        body = dict(name="Filter", collection="rehab_plans", conditions=[], global_=False)
        body["global"] = body.pop("global_")
        with patch("app.api.routers.data_filter_router.data_filter_service.save_filter",
                   new=AsyncMock(return_value="filter-id")) as domain:
            self.assertEqual((await self.client.post("/api/data-filters/save", json=body)).status_code, 200)
            data = domain.call_args.args[0]
            self.assertEqual(data["createdBy"], self.user.id)
            self.assertEqual(data["createdByName"], self.user.name)
            body["global"] = True
            self.assertEqual((await self.client.post("/api/data-filters/save", json=body)).status_code, 403)
            self.assertEqual(domain.await_count, 1)

    async def test_health_threshold_actor_cannot_be_forged_in_payload(self):
        response = dict(id="threshold-id", name="Threshold", data_type="custom", created_by=self.user.id)
        service = SimpleNamespace(create_threshold=AsyncMock(return_value=response))
        app.dependency_overrides[get_health_alert_service] = lambda: service
        result = await self.client.post("/api/health/alerts/thresholds",
            json={"name": "Threshold", "data_type": "custom", "created_by": "forged"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(service.create_threshold.call_args.kwargs["created_by"], self.user.id)
