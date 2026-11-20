"""Multi-worker-safe runtime for explicitly opted-in analytics schedules."""
import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta

from pymongo import ReturnDocument
from bson import ObjectId

from app.services.report_scheduler_service import ReportSchedulerService

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
LEASE_SECONDS = 300
POLL_SECONDS = 30


class ReportScheduleRuntime:
    def __init__(self):
        self._task = None
        self._db = None

    async def start(self, db):
        if os.getenv("PYTEST_CURRENT_TEST"):
            return
        if self._task and not self._task.done():
            return
        self._db = db
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self):
        while True:
            try:
                await self.run_due()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("报表调度扫描失败")
            await asyncio.sleep(POLL_SECONDS)

    async def run_due(self, now=None):
        now = now or datetime.utcnow()
        service = ReportSchedulerService(self._db)
        # One claim per call keeps a slow/misconfigured schedule from starving peers.
        schedule = await self._claim(now)
        if not schedule:
            return False
        schedule_id = schedule["_id"]
        occurrence = schedule["nextRunTime"]
        claim_id = schedule["claimId"]
        try:
            if schedule.get("recoveryOnly"):
                key = service.occurrence_key(schedule_id, occurrence)
                prior_artifact = await self._db.report_schedule_runs.find_one({"_id": key})
                if prior_artifact:
                    await self._complete(schedule_id, claim_id, schedule, occurrence, now)
                    return True
                raise RuntimeError("第三次执行租约过期且未提交报表，已耗尽重试次数")
            users = self._db.users
            account_ids = set(schedule.get("recipients", []))
            account_ids.add(str(schedule.get("createdBy", "")))
            eligible = await users.count_documents({
                "_id": {"$in": [ObjectId(x) for x in account_ids if ObjectId.is_valid(x)]},
                "role": {"$in": ["admin", "doctor"]}, "is_active": {"$ne": False},
            })
            if eligible != len(account_ids):
                raise ValueError("计划创建者或收件人已失去全局数据访问权限")
            await asyncio.wait_for(service.execute_claimed_schedule(schedule, occurrence), timeout=LEASE_SECONDS - POLL_SECONDS)
            await self._complete(schedule_id, claim_id, schedule, occurrence, now)
        except Exception as exc:
            logger.exception("定时报表执行失败：%s", schedule_id)
            await self._fail(schedule_id, claim_id, schedule, occurrence, now, exc)
        return True

    async def _claim(self, now):
        claim_id = uuid.uuid4().hex
        due = {
            "enabled": True, "executionVersion": 1,
            "nextRunTime": {"$type": "date", "$lte": now},
            "$and": [
                {"$or": [{"leaseUntil": {"$exists": False}}, {"leaseUntil": None},
                         {"leaseUntil": {"$lte": now}}]},
                {"$or": [{"nextAttemptAt": {"$exists": False}}, {"nextAttemptAt": None},
                         {"nextAttemptAt": {"$lte": now}}]},
            ],
        }
        claimed = await self._db.report_schedules.find_one_and_update(
            {
                **due,
                "retryCount": {"$lt": MAX_ATTEMPTS},
            },
            {"$inc": {"retryCount": 1}, "$set": {
                "claimId": claim_id, "leaseUntil": now + timedelta(seconds=LEASE_SECONDS),
                "lastRunStatus": "running", "lastRunTime": now,
            }},
            sort=[("nextRunTime", 1), ("createdAt", 1)],
            return_document=ReturnDocument.AFTER,
        )
        if claimed:
            return claimed
        # If attempt three's process died while holding its lease, do not strand the
        # schedule in running forever. This recovery claim never starts generation.
        return await self._db.report_schedules.find_one_and_update(
            {**due, "retryCount": {"$gte": MAX_ATTEMPTS},
             "lastRunStatus": {"$in": ["running", "recovering"]}, "leaseUntil": {"$lte": now}},
            {"$set": {"claimId": claim_id,
                       "leaseUntil": now + timedelta(seconds=LEASE_SECONDS),
                       "recoveryOnly": True, "lastRunStatus": "recovering"}},
            sort=[("nextRunTime", 1), ("createdAt", 1)],
            return_document=ReturnDocument.AFTER,
        )

    async def _complete(self, schedule_id, claim_id, schedule, occurrence, now):
        if schedule.get("frequency") == "once":
            next_time, enabled = None, False
        else:
            next_time = ReportSchedulerService._next_occurrence(schedule, occurrence + timedelta(seconds=1))
            enabled = True
        await self._db.report_schedules.update_one(
            {"_id": schedule_id, "claimId": claim_id},
            {"$set": {"lastRunStatus": "success", "lastRunTime": now,
                       "nextRunTime": next_time, "enabled": enabled, "retryCount": 0},
             "$unset": {"claimId": "", "leaseUntil": "", "nextAttemptAt": "", "recoveryOnly": "", "lastRunError": ""}},
        )

    async def _fail(self, schedule_id, claim_id, schedule, occurrence, now, exc):
        attempts = int(schedule.get("retryCount", 1))
        exhausted = attempts >= MAX_ATTEMPTS
        set_fields = {"lastRunStatus": "error", "lastRunTime": now,
                      "lastRunError": str(exc)[:500]}
        if exhausted:
            if schedule.get("frequency") == "once":
                set_fields.update(nextRunTime=None, enabled=False)
            else:
                set_fields["nextRunTime"] = ReportSchedulerService._next_occurrence(
                    schedule, occurrence + timedelta(seconds=1))
            set_fields["retryCount"] = 0
        else:
            delay = min(60 * (2 ** (attempts - 1)), 900)
            set_fields["nextAttemptAt"] = now + timedelta(seconds=delay)
        await self._db.report_schedules.update_one(
            {"_id": schedule_id, "claimId": claim_id},
            {"$set": set_fields, "$unset": {"claimId": "", "leaseUntil": "", "recoveryOnly": ""}},
        )


report_schedule_runtime = ReportScheduleRuntime()
