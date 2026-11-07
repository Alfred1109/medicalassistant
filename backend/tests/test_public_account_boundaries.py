"""Public/self-service DTOs cannot write administrative identity fields."""
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
from fastapi import FastAPI

from app.api.routers.user_router import router
from app.core.dependencies import get_current_user, get_user_service
from app.schemas.user import UserResponse


class PublicAccountBoundariesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.include_router(router, prefix="/users")
        self.user = UserResponse(id="507f1f77bcf86cd799439011", email="patient@example.com",
                                 name="Patient", role="patient", is_active=True,
                                 createdAt=datetime.utcnow(), updatedAt=datetime.utcnow())
        self.service = MagicMock()
        self.service.create_user = AsyncMock(return_value=self.user)
        self.service.update_user = AsyncMock(return_value=self.user)
        self.app.dependency_overrides[get_current_user] = lambda: self.user
        self.app.dependency_overrides[get_user_service] = lambda: self.service
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_public_registration_cannot_set_permissions_status_or_other_roles(self):
        base = {"email": "patient@example.com", "name": "Patient", "password": "test password"}
        for extra in ({"permissions": ["user:manage"]}, {"is_active": True},
                      {"role": "admin"}, {"unknown": "ignored"}):
            with self.subTest(extra=extra):
                response = await self.client.post("/users/register", json={**base, **extra})
                self.assertEqual(response.status_code, 422)
        self.service.create_user.assert_not_awaited()

    async def test_patient_registration_uses_server_assigned_authority(self):
        response = await self.client.post("/users/register", json={"email": "patient@example.com",
            "name": "Patient", "password": "test password", "role": "patient"})
        self.assertEqual(response.status_code, 201)
        candidate = self.service.create_user.await_args.args[0]
        self.assertEqual(candidate.role, "patient")
        self.assertIsNone(candidate.permissions)
        self.assertTrue(candidate.is_active)

    async def test_self_service_cannot_change_credentials_authorization_or_unknown_fields(self):
        for change in ({"password": "new password"}, {"email": "other@example.com"},
                       {"is_active": False}, {"role": "admin"}, {"permissions": ["user:manage"]},
                       {"currentPassword": "a", "newPassword": "b"}):
            with self.subTest(field=list(change)):
                response = await self.client.put("/users/me", json=change)
                self.assertEqual(response.status_code, 422)
        self.service.update_user.assert_not_awaited()

    async def test_legacy_local_display_name_remains_available(self):
        response = await self.client.put("/users/me", json={"name": "New display name"})
        self.assertEqual(response.status_code, 200)
        identifier, data = self.service.update_user.await_args.args
        self.assertEqual(identifier, self.user.id)
        self.assertEqual(data.name, "New display name")
        self.assertIsNone(data.password)


if __name__ == "__main__":
    unittest.main()
