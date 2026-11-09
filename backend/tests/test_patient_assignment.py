"""Role-specific patient assignment follows the actual relationship writer."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bson import ObjectId

from app.core.patient_access import (
    PatientAccessError, assigned_patient_query, ensure_patient_access,
)


class PatientAssignmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_medical_role_uses_its_own_field_and_objectid_values(self):
        actor_id = str(ObjectId())
        patient_id = str(ObjectId())
        for role, field in (("doctor", "practitioners"), ("health_manager", "health_managers")):
            with self.subTest(role=role):
                patient = {"_id": ObjectId(patient_id), "role": "patient", field: [ObjectId(actor_id)]}
                db = SimpleNamespace(users=SimpleNamespace(find_one=AsyncMock(return_value=patient)))
                self.assertIs(await ensure_patient_access(db, patient_id, actor_id, role), patient)
                query = assigned_patient_query(actor_id, role)
                self.assertEqual(set(query), {"role", field})
                self.assertEqual(query[field]["$in"], [actor_id, ObjectId(actor_id)])
                patient[field] = []
                with self.assertRaises(PatientAccessError) as denied:
                    await ensure_patient_access(db, patient_id, actor_id, role)
                self.assertEqual(denied.exception.status_code, 403)

    async def test_wrong_role_field_cannot_grant_access(self):
        for role, wrong_field in (("doctor", "health_managers"), ("health_manager", "practitioners")):
            with self.subTest(role=role):
                db = SimpleNamespace(users=SimpleNamespace(find_one=AsyncMock(
                    return_value={"_id": "patient", "role": "patient", wrong_field: ["actor"]})))
                with self.assertRaises(PatientAccessError):
                    await ensure_patient_access(db, "patient", "actor", role)

    async def test_non_medical_roles_cannot_borrow_assignment_and_admin_behavior_is_preserved(self):
        db = SimpleNamespace(users=SimpleNamespace(find_one=AsyncMock()))
        for role in ("patient", "unknown"):
            with self.subTest(role=role):
                with self.assertRaises(PatientAccessError):
                    assigned_patient_query("actor", role)
                with self.assertRaises(PatientAccessError):
                    await ensure_patient_access(db, "patient", "actor", role)
        self.assertEqual(await ensure_patient_access(db, "patient", "actor", "admin"), {})
        db.users.find_one.assert_not_awaited()
