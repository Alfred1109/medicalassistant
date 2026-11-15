from datetime import datetime
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from bson import ObjectId

from app.services.dashboard_service import DashboardService


class DashboardHealthMetricsTests(IsolatedAsyncioTestCase):
    async def test_reads_patient_entity_vitals_not_account_or_orphan_collection(self):
        db = MagicMock()
        cursor = db.health_data.find.return_value
        cursor.sort.return_value = cursor
        cursor.limit.return_value = cursor
        cursor.to_list = AsyncMock(return_value=[{
            "_id": ObjectId(), "patient_id": "patient-entity", "data_type": "vital_sign",
            "data": {"type": "heart_rate", "value": 72, "unit": "bpm"},
            "metadata": {"quality_flags": ["out_of_range"]},
            "recorded_at": datetime(2026, 1, 1),
        }])
        with patch("app.services.dashboard_service.resolve_self_patient_entity",
                   new=AsyncMock(return_value="patient-entity")) as resolve:
            result = await DashboardService.get_health_metrics(db, "account-id")
        self.assertEqual(resolve.await_args.args[1].id, "account-id")
        db.health_data.find.assert_called_once_with({"patient_id": "patient-entity", "data_type": "vital_sign", "deleted": {"$ne": True}})
        db.health_metrics.find.assert_not_called()
        self.assertEqual(result[0]["value"], 72)
        self.assertEqual(result[0]["name"], "heart_rate")
        self.assertEqual(result[0]["quality_flags"], ["out_of_range"])
        self.assertNotIn("status", result[0])

    async def test_identity_failure_is_not_converted_to_an_empty_dashboard(self):
        db = MagicMock()
        with patch("app.services.dashboard_service.resolve_self_patient_entity",
                   new=AsyncMock(side_effect=RuntimeError("identity unavailable"))):
            with self.assertRaisesRegex(RuntimeError, "identity unavailable"):
                await DashboardService.get_health_metrics(db, "account-id")
        db.health_data.find.assert_not_called()
