"""Shared provisional follow-up metrics retain facts and historical spellings."""
import unittest
from collections import Counter
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.core.followup_semantics import (
    FOLLOWUP_COMPLETION_POLICY, FOLLOWUP_STATUSES, FollowUpStatus, followup_completion)
from app.schemas.followup import FollowUpStatus as SchemaFollowUpStatus
from app.services.icf_service import _compute_followup_completion, update_metric_config
from app.services.quality_monitoring_service import QualityMonitoringService, process_csv
from app.services.followup_service import FollowupService


class FollowupMetricTests(unittest.TestCase):
    def test_single_status_enum_and_read_only_historical_semantics(self):
        self.assertIs(SchemaFollowUpStatus, FollowUpStatus)
        for alias in ("done", "finished", "cancelled", "void", "pending"):
            self.assertIn(alias, FOLLOWUP_STATUSES)
        with self.assertRaises(ValueError):
            FollowUpStatus("done")  # Alias compatibility does not create a writable state.

    def test_conservative_default_counts_every_non_void_status_as_unfinished(self):
        states = ["completed", "done", "finished", "in_review", "pending", "lost", "new_status", None,
                  "canceled", "cancelled", "void"]
        expected = followup_completion(Counter(states))
        self.assertEqual((expected["completed"], expected["total"], expected["excluded"]), (3, 8, 3))
        self.assertEqual(expected["value"], 0.375)
        result = _compute_followup_completion([{"status": state} for state in states], {})
        self.assertEqual(result["value"], expected["value"])
        self.assertEqual(result["detail"][0], expected)
        self.assertIn("待临床确认", result["message"])

    def test_no_denominator_is_unavailable_and_success_remains_provisional(self):
        result = _compute_followup_completion([{"status": "void"}], {})
        self.assertEqual(result["state"], "insufficient_data")
        self.assertIsNone(result["value"])
        self.assertIn("待临床确认", result["message"])
        success = _compute_followup_completion([{"status": "completed"}], {})
        self.assertEqual(success["state"], "ok")
        self.assertIn("待临床确认", success["message"])
        with self.assertRaises(ValueError):
            followup_completion({}, {"completion_policy": "assume_reviewed_complete"})

    def test_threshold_uses_unrounded_fraction(self):
        rows = [{"status": "completed"}] * 6 + [{"status": "in_review"}]
        result = _compute_followup_completion(rows, {"min_rate": 0.85713})
        self.assertEqual(result["value"], 0.8571)
        self.assertEqual(result["state"], "ok")


class FollowupMetricConfigurationTests(unittest.IsolatedAsyncioTestCase):
    async def test_sample_preserves_unknown_status_and_is_bounded_and_patient_scoped(self):
        rows = [{"status": "done"}, {"status": "new_state"}, {"status": None}]
        cursor = MagicMock()
        cursor.sort.return_value = cursor
        cursor.limit.return_value = cursor
        cursor.to_list = AsyncMock(return_value=rows)
        collection = MagicMock()
        collection.find.return_value = cursor
        svc = FollowupService({"followup_records": collection, "medical_timelines": MagicMock()})
        self.assertEqual(await svc.metric_status_sample("patient", limit=3), rows)
        collection.find.assert_called_once_with(
            {"patient_id": "patient", "deleted": {"$ne": True}}, {"_id": 0, "status": 1})
        cursor.sort.assert_called_once_with("scheduled_date", 1)
        cursor.limit.assert_called_once_with(3)
        with self.assertRaises(ValueError):
            await svc.metric_status_sample("patient", limit=501)

    async def test_invalid_policy_or_threshold_cannot_be_written(self):
        collection = SimpleNamespace(find_one=AsyncMock(return_value={"metric_key": "followup_completion_rate"}),
                                     update_one=AsyncMock())
        db = SimpleNamespace(icf_metric_configs=collection)
        for params in ({"completion_policy": "all"}, {"min_rate": -1}, {"min_rate": True}, {"min_rate": float("nan")}):
            with self.assertRaises(HTTPException) as caught:
                await update_metric_config(db, SimpleNamespace(role="doctor", id="doctor"),
                                           "followup_completion_rate", params=params)
            self.assertEqual(caught.exception.status_code, 422)
        collection.update_one.assert_not_awaited()

    async def test_quality_and_icf_share_counts_and_report_policy(self):
        counts = {"done": 2, "in_review": 1, "void": 1, "__unknown__": 1}
        rows = {"statuses": [{"_id": key, "count": value} for key, value in counts.items()],
                "total": [{"count": 5}], "scope": [{"count": 5}]}
        db = SimpleNamespace(icf_metric_configs=SimpleNamespace(find_one=AsyncMock(return_value={
            "params": {"completion_policy": FOLLOWUP_COMPLETION_POLICY}})))
        with patch("app.services.quality_monitoring_service.FollowupService"), \
                patch("app.services.quality_monitoring_service.RehabPublicationService"):
            svc = QualityMonitoringService(db)
        with patch.object(svc, "scope", AsyncMock(return_value=["patient"])), \
                patch.object(svc, "_read", AsyncMock(side_effect=[rows, {}])):
            overview = await svc.overview(SimpleNamespace(role="doctor"))
        self.assertEqual(overview.followups.completion.model_dump(), followup_completion(counts))
        self.assertEqual(overview.followups.in_review_count, 1)
        report = process_csv(overview, None).decode("utf-8-sig")
        self.assertIn("completion:policy", report)
        self.assertIn("待临床确认", report)
