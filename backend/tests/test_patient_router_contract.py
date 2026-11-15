"""Patient-facing rehabilitation reads use the published-plan domain."""
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

import httpx
from bson import ObjectId

from app.core.auth import get_current_active_user
from app.main import app
from app.schemas.user import UserResponse


class PatientRehabContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.actor = UserResponse(id=str(ObjectId()), email="patient@example.com", name="患者",
            role="patient", is_active=True, createdAt=datetime.utcnow(), updatedAt=datetime.utcnow())
        app.dependency_overrides[get_current_active_user] = lambda: self.actor
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()

    async def test_my_plans_uses_authenticated_actor_and_publication_projection(self):
        expected = {"items": [{"id": "plan-id", "content": {"name": "方案"}, "items": []}],
                    "total": 1, "skip": 0, "limit": 20}
        with patch("app.api.routers.rehab_publication_router.RehabPublicationService.patient_list",
                   new=AsyncMock(return_value=expected)) as patient_list:
            response = await self.client.get("/api/rehabilitation/publications/my-plans")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), expected)
        self.assertEqual(patient_list.await_args.args[0], self.actor)

    async def test_legacy_patient_progress_routes_are_removed(self):
        for path in ("/api/patients/statistics", "/api/patients/rehab-progress"):
            with self.subTest(path=path):
                response = await self.client.get(path)
                self.assertEqual(response.status_code, 404, response.text)


if __name__ == "__main__":
    unittest.main()
