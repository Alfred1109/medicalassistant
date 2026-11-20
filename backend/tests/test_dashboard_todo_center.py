import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.dashboard_service import DashboardService


class DashboardTodoCenterTests(unittest.IsolatedAsyncioTestCase):
    async def test_aggregates_only_actionable_stored_tasks_and_pending_consents(self):
        tasks = {"items": [
            {"id": "assigned-id", "status": "assigned", "visitName": "初诊问卷", "createdAt": "2026-11-01"},
            {"id": "active-id", "status": "active", "visitName": "复诊问卷"},
            {"id": "submitted-id", "status": "submitted", "visitName": "已提交问卷"},
        ], "total": 3}
        consents = [{"id": "pending-id", "title": "知情同意"}]
        actor = SimpleNamespace(id="account-id", role="patient")
        with patch("app.services.dashboard_service.patient_self.list_tasks", new=AsyncMock(return_value=tasks)) as list_tasks, \
             patch("app.services.dashboard_service.list_pending_consent_summaries",
                   new=AsyncMock(return_value=consents)) as list_consents:
            result = await DashboardService.get_todo_center(object(), actor)

        self.assertEqual([row["type"] for row in result["items"]], ["questionnaire", "questionnaire", "consent"])
        self.assertEqual(result["source_errors"], [])
        self.assertEqual(result["items"][0]["href"], "/app/patient/questionnaires/assigned-id")
        self.assertEqual(result["items"][2]["href"], "/app/patient/documents/pending-id")
        list_tasks.assert_awaited_once()
        list_consents.assert_awaited_once_with(unittest.mock.ANY, actor)

    async def test_source_failure_does_not_hide_other_source(self):
        actor = SimpleNamespace(id="account-id", role="patient")
        with patch("app.services.dashboard_service.patient_self.list_tasks", new=AsyncMock(side_effect=RuntimeError())), \
             patch("app.services.dashboard_service.list_pending_consent_summaries", new=AsyncMock(return_value=[
                 {"id": "pending-id", "title": "知情同意"}
             ])):
            result = await DashboardService.get_todo_center(object(), actor)

        self.assertEqual(result["source_errors"], ["questionnaires_unavailable"])
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["type"], "consent")


if __name__ == "__main__":
    unittest.main()
