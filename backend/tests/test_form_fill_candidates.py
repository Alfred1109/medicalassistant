import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from bson import ObjectId
from fastapi import HTTPException

from app.core.patient_access import PatientAccessError
from app.integrations.forms.candidates import list_fill_candidates


OPERATOR_ID = "507f1f77bcf86cd799439011"
SOURCE_ORIGIN = "https://forms.example"


class FakeCursor:
    def __init__(self, page):
        self.page = page

    async def to_list(self, length=None):
        return self.page[:length]


def make_database(*, canonical=True, page=None):
    context = SimpleNamespace(is_canonical=canonical,
                              ensure_patient_access=AsyncMock(return_value={}))
    collection = MagicMock()
    collection.aggregate.return_value = FakeCursor(page or [{
        "patients": [{
            "patient_id": "patient-1", "name": "患者甲", "references": [{
                "project_id": 2, "center_id": 3, "subject_id": 4,
                "forms": [{"binding_id": "binding-1", "form_id": 5,
                           "version": 1, "purpose": "followup", "title": "测试表单"}],
            }],
        }],
        "total": [{"count": 1}],
    }])
    database = SimpleNamespace(
        clinical_patients=collection,
        users=collection,
    )
    return database, context, collection


class FillCandidateTests(unittest.IsolatedAsyncioTestCase):
    async def test_doctor_scope_and_minimal_reviewed_response(self):
        database, context, collection = make_database(canonical=True)
        actor = SimpleNamespace(id=OPERATOR_ID, role="doctor")

        with unittest.mock.patch(
                "app.integrations.forms.candidates.patient_domain_context",
                new=AsyncMock(return_value=context)):
            result = await list_fill_candidates(database, actor, SOURCE_ORIGIN, skip=0, limit=25)

        pipeline = collection.aggregate.call_args.args[0]
        self.assertEqual(pipeline[0]["$match"], {
            "status": "active",
            "practitioners": {"$in": [OPERATOR_ID, ObjectId(OPERATOR_ID)]},
        })
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["patients"][0]["references"][0]["forms"][0]["binding_id"], "binding-1")
        context.ensure_patient_access.assert_awaited_once_with("patient-1", OPERATOR_ID, "doctor")
        self.assertEqual(set(result), {"patients", "skip", "limit", "total"})
        self.assertIn("external_patient_links", str(pipeline))
        self.assertIn("external_form_bindings", str(pipeline))
        self.assertIn("verified", str(pipeline))
        self.assertIn(SOURCE_ORIGIN, str(pipeline))

    async def test_health_manager_uses_legacy_patient_assignment_scope(self):
        database, context, collection = make_database(canonical=False)
        actor = SimpleNamespace(id=OPERATOR_ID, role="health_manager")

        with unittest.mock.patch(
                "app.integrations.forms.candidates.patient_domain_context",
                new=AsyncMock(return_value=context)):
            await list_fill_candidates(database, actor, SOURCE_ORIGIN)

        self.assertEqual(collection.aggregate.call_args.args[0][0]["$match"], {
            "role": "patient", "is_active": True,
            "health_managers": {"$in": [OPERATOR_ID, ObjectId(OPERATOR_ID)]},
        })
        context.ensure_patient_access.assert_awaited_once_with(
            "patient-1", OPERATOR_ID, "health_manager")

    async def test_admin_can_read_candidates_but_patient_cannot(self):
        database, context, collection = make_database(canonical=False)
        with unittest.mock.patch(
                "app.integrations.forms.candidates.patient_domain_context",
                new=AsyncMock(return_value=context)):
            await list_fill_candidates(database, SimpleNamespace(id="admin", role="admin"), SOURCE_ORIGIN)
            self.assertEqual(collection.aggregate.call_args.args[0][0]["$match"], {
                "role": "patient", "is_active": True,
            })
            with self.assertRaises(HTTPException) as raised:
                await list_fill_candidates(database, SimpleNamespace(id="patient", role="patient"), SOURCE_ORIGIN)

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(collection.aggregate.call_count, 1)

    async def test_pagination_is_bounded_and_passed_to_facet(self):
        database, context, collection = make_database()
        actor = SimpleNamespace(id=OPERATOR_ID, role="doctor")
        with unittest.mock.patch(
                "app.integrations.forms.candidates.patient_domain_context",
                new=AsyncMock(return_value=context)):
            for kwargs in ({"skip": -1}, {"skip": 10_001}, {"limit": 0}, {"limit": 101}):
                with self.subTest(kwargs=kwargs), self.assertRaises(HTTPException) as raised:
                    await list_fill_candidates(database, actor, SOURCE_ORIGIN, **kwargs)
                self.assertEqual(raised.exception.status_code, 422)
            await list_fill_candidates(database, actor, SOURCE_ORIGIN, skip=75, limit=50)

        self.assertEqual(collection.aggregate.call_args.args[0][-1]["$facet"]["patients"], [
            {"$skip": 75}, {"$limit": 50},
            {"$project": {"_id": 0, "patient_id": "$_id", "name": 1, "references": 1}},
        ])

    async def test_candidate_is_removed_if_shared_access_check_rejects_it(self):
        database, context, _ = make_database()
        context.ensure_patient_access = AsyncMock(side_effect=PatientAccessError(
            "未分配", error_code="PATIENT_NOT_ASSIGNED", status_code=403))
        with unittest.mock.patch(
                "app.integrations.forms.candidates.patient_domain_context",
                new=AsyncMock(return_value=context)):
            result = await list_fill_candidates(
                database, SimpleNamespace(id=OPERATOR_ID, role="doctor"), SOURCE_ORIGIN)

        self.assertEqual(result["patients"], [])
        context.ensure_patient_access.assert_awaited_once_with(
            "patient-1", OPERATOR_ID, "doctor")


if __name__ == "__main__":
    unittest.main()
