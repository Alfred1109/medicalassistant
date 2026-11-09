"""Shared exercise catalogue mutations require medical/admin roles."""
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from bson import ObjectId
from jose import jwt

from app.core.config import settings
from app.core.dependencies import get_rehabilitation_service
from app.db.mongodb import get_database
from app.main import app
from app.schemas.user import UserResponse
from app.services.user_service import UserService


class ExerciseCatalogRoleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = SimpleNamespace(create_exercise=AsyncMock(return_value={"id": "exercise"}),
            update_exercise=AsyncMock(return_value={"id": "exercise"}), delete_exercise=AsyncMock(return_value=True),
            get_exercise=AsyncMock(return_value={"id": "exercise"}), list_exercises=AsyncMock(return_value=[]))
        app.dependency_overrides[get_rehabilitation_service] = lambda: self.service
        app.dependency_overrides[get_database] = lambda: SimpleNamespace(users=None, audit_logs=None)
        self.lookup = AsyncMock()
        self.patcher = patch.object(UserService, "get_user_by_id", new=self.lookup)
        self.patcher.start()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        self.patcher.stop()
        app.dependency_overrides.clear()

    def auth(self, role):
        now, identifier = datetime.utcnow(), str(ObjectId())
        self.lookup.return_value = UserResponse(id=identifier, role=role, name="synthetic",
            email="actor@example.com", is_active=True, createdAt=now, updatedAt=now)
        return {"Authorization": "Bearer " + jwt.encode({"sub": identifier, "token_type": "access",
            "exp": now + timedelta(minutes=5)}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)}

    def mutations(self):
        return [("POST", "/api/rehabilitation/exercises", {"name": "synthetic", "description": "entered by staff",
            "body_part": "explicit", "difficulty": "Easy", "duration_minutes": 1, "instructions": []}),
            ("PUT", "/api/rehabilitation/exercises/example", {"name": "edited"}),
            ("DELETE", "/api/rehabilitation/exercises/example", None)]

    async def test_patient_and_unrecognized_roles_cannot_write_shared_catalogue(self):
        for role in ("patient", "researcher", "organization_admin", "unknown"):
            for method, url, body in self.mutations():
                response = await self.client.request(method, url, json=body, headers=self.auth(role))
                self.assertEqual(response.status_code, 403, (role, response.text))
        for action in (self.service.create_exercise, self.service.update_exercise, self.service.delete_exercise):
            action.assert_not_awaited()

    async def test_authorized_medical_and_admin_roles_keep_all_mutations(self):
        for role in ("doctor", "health_manager", "admin"):
            for method, url, body in self.mutations():
                response = await self.client.request(method, url, json=body, headers=self.auth(role))
                self.assertIn(response.status_code, (200, 204), (role, response.text))

    async def test_patient_read_and_anonymous_denial_are_preserved(self):
        headers = self.auth("patient")
        self.assertEqual((await self.client.get("/api/rehabilitation/exercises/example", headers=headers)).status_code, 200)
        self.assertEqual((await self.client.post("/api/rehabilitation/exercises/list", json={}, headers=headers)).status_code, 200)
        for method, url, body in self.mutations():
            self.assertEqual((await self.client.request(method, url, json=body)).status_code, 401)
