"""Real route and service query authorization, using synthetic in-memory reads."""
import copy
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
from app.services.rehabilitation_service import RehabilitationService
from app.services.user_service import UserService


DOCTOR = str(ObjectId())
MANAGER = str(ObjectId())
PATIENT_A, PATIENT_B, PATIENT_C = [str(ObjectId()) for _ in range(3)]


def matches(document, query):
    for key, expected in query.items():
        actual = document.get(key)
        if isinstance(expected, dict) and "$in" in expected:
            values = actual if isinstance(actual, list) else [actual]
            if not any(value in expected["$in"] for value in values):
                return False
        elif actual != expected:
            return False
    return True


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def skip(self, count):
        self.rows = self.rows[count:]
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    def __aiter__(self):
        async def rows():
            for row in self.rows:
                yield copy.deepcopy(row)
        return rows()


class Collection:
    def __init__(self, documents):
        self.documents = documents
        self.queries = []

    def find(self, query, projection=None):
        self.queries.append(copy.deepcopy(query))
        return Cursor([row for row in self.documents if matches(row, query)])

    async def find_one(self, query):
        return next((copy.deepcopy(row) for row in self.documents if matches(row, query)), None)


class RehabPlanListScopeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.database = SimpleNamespace(
            users=Collection([
                {"_id": ObjectId(PATIENT_A), "role": "patient", "practitioners": [ObjectId(DOCTOR)],
                 "health_managers": [MANAGER]},
                {"_id": ObjectId(PATIENT_B), "role": "patient", "practitioners": [DOCTOR],
                 "health_managers": []},
                {"_id": ObjectId(PATIENT_C), "role": "patient", "practitioners": ["other-doctor"],
                 "health_managers": [ObjectId(MANAGER)]},
            ]),
            rehab_plans=Collection([
                {"_id": ObjectId(), "patient_id": PATIENT_C, "name": "C"},
                {"_id": ObjectId(), "patient_id": PATIENT_A, "name": "A1"},
                {"_id": ObjectId(), "patient_id": PATIENT_B, "name": "B"},
                {"_id": ObjectId(), "patient_id": PATIENT_A, "name": "A2"},
            ]), exercises=None, rehab_assessments=None, agents=None, audit_logs=None)
        self.service = RehabilitationService(self.database)
        app.dependency_overrides[get_database] = lambda: self.database
        app.dependency_overrides[get_rehabilitation_service] = lambda: self.service
        self.actor_lookup = AsyncMock()
        self.lookup = patch.object(UserService, "get_user_by_id", new=self.actor_lookup)
        self.lookup.start()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        self.lookup.stop()
        app.dependency_overrides.clear()

    def auth(self, role, identifier):
        now = datetime.utcnow()
        self.actor_lookup.return_value = UserResponse(
            id=identifier, role=role, name="synthetic", email="actor@example.com",
            is_active=True, createdAt=now, updatedAt=now)
        token = jwt.encode({"sub": identifier, "token_type": "access", "exp": now + timedelta(minutes=5)},
                           settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return {"Authorization": "Bearer " + token}

    async def get(self, role, identifier, query=""):
        return await self.client.get("/api/rehabilitation/plans" + query,
                                     headers=self.auth(role, identifier))

    async def test_unfiltered_medical_scope_is_applied_before_pagination(self):
        response = await self.get("doctor", DOCTOR, "?skip=1&limit=1")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([row["name"] for row in response.json()], ["B"])
        self.assertEqual(self.database.rehab_plans.queries[-1],
                         {"patient_id": {"$in": [PATIENT_A, PATIENT_B]}})
        response = await self.get("health_manager", MANAGER)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["name"] for row in response.json()], ["C", "A1", "A2"])

    async def test_patient_cannot_read_raw_plans_with_or_without_filter(self):
        for query in ("", "?patient_id=", "?patient_id=" + PATIENT_B):
            response = await self.get("patient", PATIENT_B, query)
            self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.database.rehab_plans.queries, [])
        before = len(self.database.rehab_plans.queries)
        response = await self.get("patient", PATIENT_B, "?patient_id=" + PATIENT_A)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(self.database.rehab_plans.queries), before)

    async def test_explicit_medical_filter_requires_assignment(self):
        for role, identifier, permitted, forbidden in (
            ("doctor", DOCTOR, PATIENT_B, PATIENT_C),
            ("health_manager", MANAGER, PATIENT_C, PATIENT_B),
        ):
            response = await self.get(role, identifier, "?patient_id=" + permitted)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual({row["patient_id"] for row in response.json()}, {permitted})
            before = len(self.database.rehab_plans.queries)
            response = await self.get(role, identifier, "?patient_id=" + forbidden)
            self.assertEqual(response.status_code, 403)
            self.assertEqual(len(self.database.rehab_plans.queries), before)

    async def test_empty_scope_and_cross_role_assignments_never_become_global(self):
        for role, identifier in (("doctor", str(ObjectId())), ("doctor", MANAGER),
                                 ("health_manager", DOCTOR)):
            response = await self.get(role, identifier)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), [])
            self.assertEqual(self.database.rehab_plans.queries[-1], {"patient_id": {"$in": []}})

    async def test_admin_retains_global_and_explicit_filters(self):
        response = await self.get("admin", str(ObjectId()))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 4)
        self.assertEqual(self.database.rehab_plans.queries[-1], {})
        response = await self.get("admin", str(ObjectId()), "?patient_id=" + PATIENT_A)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["name"] for row in response.json()], ["A1", "A2"])

    async def test_unknown_roles_and_invalid_pagination_are_rejected(self):
        response = await self.get("unrecognized_role", str(ObjectId()))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.database.rehab_plans.queries, [])
        for query in ("?skip=-1", "?limit=0"):
            response = await self.get("doctor", DOCTOR, query)
            self.assertEqual(response.status_code, 422)
        self.assertEqual(self.database.rehab_plans.queries, [])

    async def test_service_itself_refuses_unauthorized_explicit_filter(self):
        from app.core.patient_access import PatientAccessError
        with self.assertRaises(PatientAccessError):
            await self.service.list_rehab_plans(PATIENT_C, actor_id=DOCTOR, actor_role="doctor")
        with self.assertRaises(PatientAccessError):
            await self.service.list_rehab_plans(actor_id=DOCTOR, actor_role="unknown")
        self.assertEqual(self.database.rehab_plans.queries, [])
