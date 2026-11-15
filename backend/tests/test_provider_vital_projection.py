from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from bson import ObjectId

from app.api.dependencies import get_health_record_for_patient
from app.api.routers.doctor_router import load_provider_health_record


class ProviderVitalProjectionTests(IsolatedAsyncioTestCase):
    async def test_fact_projection_ignores_embedded_vitals_and_retains_quality(self):
        db = MagicMock()
        cursor = db.__getitem__.return_value.find.return_value
        cursor.sort.return_value = cursor
        cursor.limit.return_value = cursor
        cursor.to_list = AsyncMock(return_value=[{
            "_id": ObjectId(), "patient_id": "patient-entity", "data_type": "vital_sign",
            "data": {"type": "blood_pressure_systolic", "value": 120, "unit": "mmHg"},
            "metadata": {"quality_flags": ["out_of_range"]},
        }])
        with patch("app.api.routers.doctor_router.ensure_patient_access", new=AsyncMock(return_value={"name": "Patient", "emergency_contact": {}})), \
             patch("app.api.routers.doctor_router.get_health_record_for_patient", new=AsyncMock(return_value={
                 "vital_signs": [{"bp": "obsolete"}]})):
            result = await load_provider_health_record(db, "patient-entity", "doctor", "doctor")
        self.assertEqual(result["name"], "Patient")
        self.assertEqual(result["emergencyContact"], "未设置")
        self.assertEqual(result["vitalSigns"][0]["data"]["value"], 120)
        self.assertEqual(result["vitalSigns"][0]["metadata"]["quality_flags"], ["out_of_range"])
        self.assertNotIn("bp", result["vitalSigns"][0])
        db["health_data"].find.assert_called_once_with({"patient_id": "patient-entity", "data_type": "vital_sign", "deleted": {"$ne": True}})

    async def test_patient_domain_failure_is_not_hidden_as_empty_record(self):
        db = MagicMock()
        with patch("app.api.dependencies.load_patient_doc", new=AsyncMock(side_effect=RuntimeError("domain unavailable"))):
            with self.assertRaisesRegex(RuntimeError, "domain unavailable"):
                await get_health_record_for_patient("patient-entity", db)
