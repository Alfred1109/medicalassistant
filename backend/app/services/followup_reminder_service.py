"""Fixed 24-hour in-app reminders with durable, transactional deduplication.

Legacy reminder_before/days_before fields are deliberately not consulted.
"""
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import AppBaseException
from app.db.transactions import run_followup_transaction
from app.services.followup_service import FollowupService

logger = logging.getLogger(__name__)
DELIVERIES = "followup_reminder_deliveries"
STATUSES = ["scheduled", "awaiting_fill"]
POLICY = "inapp-24h-v1"


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def as_utc(value):
    if not isinstance(value, datetime):
        return None
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def reminder_key(record, slot):
    # Returning to exactly the same plan never resurrects an already sent event.
    provider = record.get("provider_id")
    provider = provider if isinstance(provider, str) else None
    if provider and ObjectId.is_valid(provider):
        provider = str(ObjectId(provider))
    value = [POLICY, str(record["_id"]), as_utc(record["scheduled_date"]).isoformat(),
             str(record.get("patient_id", "")), provider if slot == "provider" else None, slot]
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


async def ensure_reminder_storage(db):
    hello = await db.client.admin.command("hello")
    if not hello.get("setName"):
        raise AppBaseException("提醒需要 MongoDB 副本集事务", status_code=503,
                               error_code="REMINDER_TRANSACTIONS_REQUIRED")
    # _id is the immutable event key, so no read-before-insert deduplication gap.
    await db[DELIVERIES].create_index([("patient_id", 1), ("checked_at", -1)], name="reminder_patient_history")
    await FollowupService(db).ensure_reminder_scan_index()


class FollowupReminderService:
    def __init__(self, db, *, clock=utc_now):
        self.db, self.clock = db, clock
        self.followups = FollowupService(db)

    async def _account(self, identifier, session):
        if not isinstance(identifier, str) or not identifier:
            return None
        keys = [identifier]
        if ObjectId.is_valid(identifier):
            keys.append(ObjectId(identifier))
        rows = await self.db.users.find({"_id": {"$in": keys}}, session=session).to_list(length=2)
        return rows[0] if len(rows) == 1 else None

    async def _fence(self, collection, document, session):
        value = document.get("_reminder_fence", 0)
        if type(value) is not int or value < 0:
            raise AppBaseException("提醒并发字段无效", status_code=503,
                                   error_code="REMINDER_INVALID_FENCE")
        # A real write is essential: Mongo no-op updates do not fence a stale
        # transaction against concurrent cancellation or permission revocation.
        await collection.update_one({"_id": document["_id"]},
                                    {"$inc": {"_reminder_fence": 1}}, session=session)

    async def _recipients(self, record, session):
        patient = await self._account(record.get("patient_id"), session)
        if not patient or patient.get("role") != "patient" or patient.get("is_active") is not True:
            return [("patient", None, "PATIENT_ACCOUNT_UNAVAILABLE"),
                    ("provider", None, "PATIENT_ACCOUNT_UNAVAILABLE")], []
        provider = await self._account(record.get("provider_id"), session)
        reason = None
        if not provider or provider.get("is_active") is not True or provider.get("role") not in {"doctor", "health_manager"}:
            reason = "PROVIDER_ACCOUNT_UNAVAILABLE"
        else:
            field = "practitioners" if provider["role"] == "doctor" else "health_managers"
            assignments = patient.get(field)
            if not isinstance(assignments, list) or str(provider["_id"]) not in {str(item) for item in assignments}:
                reason = "PROVIDER_NOT_ASSIGNED"
        slots = [("patient", patient, None), ("provider", provider if not reason else None, reason)]
        return slots, [patient] + ([provider] if not reason else [])

    async def dispatch_one(self, followup_id):
        async def transaction(session):
            now = as_utc(self.clock())
            record = await self.followups.get_reminder_source(followup_id, session=session)
            if not record or record.get("deleted") or record.get("status") not in STATUSES:
                return {"outcome": "ineligible", "notifications": []}
            planned = as_utc(record.get("scheduled_date"))
            if not planned or planned > now + timedelta(hours=24):
                return {"outcome": "not_due", "notifications": []}
            # Canonical patients cannot be mapped back to accounts by ID.
            mode = await self.db.patient_domain_state.find_one({"_id": "clinical-patients-v1"}, session=session)
            if mode is not None:
                raise AppBaseException("当前患者域尚未接入提醒账号解析", status_code=503,
                                       error_code="REMINDER_PATIENT_DOMAIN_UNSUPPORTED")
            slots, accounts = await self._recipients(record, session)
            now = as_utc(self.clock())
            if planned <= now:
                slots, accounts = [(slot, None, "PLAN_PASSED") for slot, _, _ in slots], []
            pending = []
            for slot, account, reason in slots:
                key = reminder_key(record, slot)
                prior = await self.db[DELIVERIES].find_one({"_id": key}, session=session)
                if prior and prior.get("status") == "persisted":
                    continue
                pending.append((key, slot, account, reason))
            if any(account is not None for _, _, account, _ in pending):
                await self.followups.fence_reminder_source(record, session)
                for account in accounts:
                    await self._fence(self.db.users, account, session)
            notifications = []
            for key, slot, account, reason in pending:
                entry = {"policy": POLICY, "followup_id": str(record["_id"]),
                         "patient_id": str(record["patient_id"]), "slot": slot,
                         "planned_at": planned, "checked_at": now,
                         "status": "skipped" if reason else "persisted", "reason": reason}
                if account is not None:
                    notification = {"_id": ObjectId(), "title": "随访计划提醒",
                        "content": "一项随访计划将在24小时内开始，请查看随访安排。",
                        "sender_id": "system:followup-reminders", "sender_name": "随访提醒",
                        "sender_role": "system", "recipient_id": str(account["_id"]),
                        "time": now, "read": False, "notification_type": "followup",
                        "priority": "normal", "related_entity_type": "followup",
                        "related_entity_id": str(record["_id"])}
                    await self.db.notifications.insert_one(notification, session=session)
                    entry.update(recipient_id=str(account["_id"]), notification_id=str(notification["_id"]))
                    notifications.append(notification)
                await self.db[DELIVERIES].update_one({"_id": key}, {"$set": entry}, upsert=True, session=session)
            return {"outcome": "checked", "notifications": notifications}

        # Concurrent first attempts may race on the immutable _id. Re-read the
        # winner; there is never an insert without the same transaction's ledger.
        for attempt in range(3):
            try:
                result = await run_followup_transaction(self.db, transaction)
                break
            except AppBaseException as error:
                if not isinstance(error.__cause__, DuplicateKeyError) or attempt == 2:
                    raise
        for notification in result["notifications"]:
            try:
                from app.api.websockets import get_connection_manager
                manager = get_connection_manager()
                payload = {key: value for key, value in notification.items() if key not in {"_id", "recipient_id"}}
                payload.update(id=str(notification["_id"]), time=notification["time"].replace(tzinfo=timezone.utc).isoformat())
                await manager.send_notification(payload, notification["recipient_id"])
                # A successful send only means a realtime hint was attempted.
            except Exception:
                logger.warning("Reminder realtime hint failed; persisted notification remains available")
        return {"outcome": result["outcome"], "generated": len(result["notifications"])}

    async def scan(self):
        now = as_utc(self.clock())
        if await self.db.patient_domain_state.find_one({"_id": "clinical-patients-v1"}):
            raise AppBaseException("当前患者域尚未接入提醒账号解析", status_code=503,
                                   error_code="REMINDER_PATIENT_DOMAIN_UNSUPPORTED")
        count = 0
        failed = False
        # Future only: startup never catches up reminders after their plan time.
        cursor = self.followups.reminder_candidate_cursor(now)
        async for record in cursor:
            try:
                result = await self.dispatch_one(str(record["_id"]))
                count += result["generated"]
            except Exception:
                failed = True
                logger.exception("Follow-up reminder persistence failed; record will be retried")
                # Failure history is retryable and must never replace a possibly
                # committed winner after an unknown transaction outcome.
                for slot in ("patient", "provider"):
                    try:
                        key = reminder_key(record, slot)
                        await self.db[DELIVERIES].update_one(
                            {"_id": key, "status": {"$ne": "persisted"}},
                            {"$set": {"policy": POLICY, "followup_id": str(record["_id"]),
                                "patient_id": str(record["patient_id"]), "slot": slot,
                                "planned_at": as_utc(record["scheduled_date"]),
                                "checked_at": as_utc(self.clock()), "status": "failed",
                                "reason": "PERSISTENCE_FAILED"}, "$inc": {"failure_attempts": 1}},
                            upsert=True)
                    except DuplicateKeyError:
                        pass
                    except Exception:
                        logger.warning("Reminder failure history could not be stored")
        if failed:
            raise AppBaseException("部分提醒暂未能生成，将自动重试", status_code=503,
                                   error_code="REMINDER_SCAN_FAILED")
        return count


class ReminderRuntime:
    def __init__(self):
        self.task = None
        self.status = {"enabled": False, "running": False, "state": "disabled",
                       "last_checked_at": None, "last_success_at": None, "last_error_code": None}

    async def start(self, db, *, enabled, interval):
        await self.stop()
        self.status.update(enabled=enabled, state="starting" if enabled else "disabled", last_error_code=None)
        if not enabled:
            return
        try:
            await ensure_reminder_storage(db)
        except Exception:
            self.status.update(state="error", last_error_code="REMINDER_STORAGE_UNAVAILABLE")
            logger.exception("Follow-up reminders disabled: storage requirements not met")
            return
        self.task = asyncio.create_task(self._run(FollowupReminderService(db), interval))

    async def _run(self, service, interval):
        self.status.update(running=True)
        try:
            while True:
                self.status["last_checked_at"] = utc_now()
                try:
                    await service.scan()
                    self.status.update(state="ready", last_success_at=utc_now(), last_error_code=None)
                except Exception as error:
                    self.status.update(state="error", last_error_code=(error.error_code
                        if isinstance(error, AppBaseException) else "REMINDER_SCAN_FAILED"))
                    logger.exception("Follow-up reminder scan failed; will retry")
                await asyncio.sleep(interval)
        finally:
            self.status["running"] = False

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        self.status["running"] = False


reminder_runtime = ReminderRuntime()
