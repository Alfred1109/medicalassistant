import asyncio
import unittest
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bson import ObjectId

from app.services.report_scheduler_runtime import ReportScheduleRuntime
from app.services.report_scheduler_service import ReportSchedulerService


class AtomicScheduleCollection:
    def __init__(self, schedule):
        self.schedule = deepcopy(schedule)
        self.lock = asyncio.Lock()
        self.claim_calls = 0

    async def find_one_and_update(self, query, update, **kwargs):
        async with self.lock:
            self.claim_calls += 1
            if self.schedule is None or self.schedule.get("executionVersion") != 1:
                return None
            assert query["nextRunTime"]["$type"] == "date"
            if not self.schedule.get("enabled") or self.schedule.get("claimId"):
                return None
            self.schedule["retryCount"] = self.schedule.get("retryCount", 0) + 1
            self.schedule.update(update["$set"])
            return deepcopy(self.schedule)

    async def update_one(self, query, update):
        if self.schedule and self.schedule.get("claimId") == query["claimId"]:
            self.schedule.update(update.get("$set", {}))
            for field in update.get("$unset", {}):
                self.schedule.pop(field, None)
            return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)


class ReportScheduleRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def test_monthly_occurrence_respects_real_month_length(self):
        schedule = {"frequency": "monthly", "monthDay": 31, "time": "09:00"}
        self.assertEqual(ReportSchedulerService._next_occurrence(
            schedule, datetime(2026, 1, 1)), datetime(2026, 1, 31, 9))
        self.assertEqual(ReportSchedulerService._next_occurrence(
            schedule, datetime(2026, 2, 1)), datetime(2026, 2, 28, 9))
        self.assertEqual(ReportSchedulerService._next_occurrence(
            schedule, datetime(2024, 2, 1)), datetime(2024, 2, 29, 9))

    async def test_two_workers_atomically_claim_one_delivery(self):
        now = datetime(2026, 11, 20, 10)
        schedule = {"_id": ObjectId(), "executionVersion": 1, "enabled": True,
                    "nextRunTime": now - timedelta(minutes=1), "frequency": "once",
                    "retryCount": 0, "recipients": [str(ObjectId())],
                    "createdBy": str(ObjectId())}
        schedules = AtomicScheduleCollection(schedule)
        db = SimpleNamespace(report_schedules=schedules,
                             users=SimpleNamespace(count_documents=AsyncMock(return_value=2)))
        a, b = ReportScheduleRuntime(), ReportScheduleRuntime()
        a._db = b._db = db
        with patch("app.services.report_scheduler_runtime.ReportSchedulerService.execute_claimed_schedule",
                   new=AsyncMock()) as execute:
            outcomes = await asyncio.gather(a.run_due(now), b.run_due(now))
        self.assertEqual(sorted(outcomes), [False, True])
        execute.assert_awaited_once()
        self.assertFalse(schedules.schedule["enabled"])
        self.assertEqual(schedules.schedule["lastRunStatus"], "success")
        self.assertNotIn("claimId", schedules.schedule)

    async def test_legacy_schedule_is_outside_atomic_claim_filter(self):
        runtime = ReportScheduleRuntime()
        schedules = AtomicScheduleCollection({"_id": ObjectId(), "enabled": True,
            "nextRunTime": datetime.utcnow(), "retryCount": 0})
        runtime._db = SimpleNamespace(report_schedules=schedules)
        self.assertIsNone(await runtime._claim(datetime.utcnow()))
        self.assertEqual(schedules.claim_calls, 2)  # normal attempts plus expired-final-lease recovery
        self.assertNotIn("claimId", schedules.schedule)

    async def test_expired_final_lease_recovers_without_a_fourth_generation(self):
        now = datetime(2026, 11, 20, 10)
        schedule = {"_id": ObjectId(), "claimId": "recovery", "recoveryOnly": True,
                    "retryCount": 3, "frequency": "once", "enabled": True,
                    "nextRunTime": now - timedelta(hours=1)}
        rows = []

        class ScheduleRuns:
            async def find_one(self, query):
                return None

        class Schedules:
            async def update_one(self, query, update):
                rows.append(update)
                return SimpleNamespace(modified_count=1)

        runtime = ReportScheduleRuntime()
        runtime._db = SimpleNamespace(report_schedules=Schedules(), report_schedule_runs=ScheduleRuns())
        runtime._claim = AsyncMock(return_value=schedule)
        with patch("app.services.report_scheduler_runtime.ReportSchedulerService.execute_claimed_schedule",
                   new=AsyncMock()) as execute:
            self.assertTrue(await runtime.run_due(now))
        execute.assert_not_awaited()
        self.assertFalse(rows[0]["$set"]["enabled"])
        self.assertEqual(rows[0]["$set"]["lastRunStatus"], "error")
