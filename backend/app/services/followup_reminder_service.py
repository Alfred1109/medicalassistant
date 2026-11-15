"""Fixed 24-hour in-app reminders with durable, transactional deduplication.

Legacy reminder_before/days_before fields are deliberately not consulted.
波次 3（T65）：收件人解析与栅栏载体按患者域分派——legacy 走 users 同文档
（LegacyPatientRepository + _reminder_fence），canonical 走 patient_account_links
verified 链接 + 双载体栅栏（AccountFenceStore + PatientFenceStore）；
显式 legacy 状态文档（回拨 SOP 载体）与无文档 legacy 行为完全一致。
"""
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import AppBaseException
from app.core.fences import AccountFenceStore, PatientFenceStore, legacy_document_fence
from app.core.patient_access import patient_domain_mode
from app.core.patient_identity import resolve_unique_account
from app.db.transactions import run_followup_transaction
from app.patients.legacy import LegacyPatientRepository
from app.patients.repository import ACCOUNT_LINKS, ClinicalPatientRepository
from app.services.followup_service import FollowupService, FOLLOWUP_REMINDER_DELIVERIES

logger = logging.getLogger(__name__)
# 提醒投递台账集合名唯一来源在 followup_service（T73 失访判定统计投递次数需同源）
DELIVERIES = FOLLOWUP_REMINDER_DELIVERIES
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
        # 账号层读取（医护 provider 与 canonical 患者链接账号共用）：双键直查
        # users 的存在性与启停判断是账号语义，不是患者资料读取。
        # legacy 患者账号读取仍收敛到 LegacyPatientRepository（见 _recipients）；
        # canonical 患者账号读取经 patient_account_links（见 _canonical_recipients）。
        # （R1-A3 收敛：唯一账号解析迁 core/patient_identity.resolve_unique_account
        # ——统一为 identity_key 归组口径，同键多文档返回 None 由调用方的
        # PROVIDER/PATIENT_ACCOUNT_UNAVAILABLE 防护兜住。非字符串/空标识的
        # 前置守卫语义等价保留。）
        if not isinstance(identifier, str) or not identifier:
            return None
        return await resolve_unique_account(self.db, identifier, session=session)

    async def _fence(self, collection, document, session):
        """legacy 专属 users 载体栅栏（canonical 走双载体 fence store，见 dispatch_one）。

        （R1-A2 收敛：骨架迁 fences.legacy_document_fence；本调用点无 CAS
        复核与附加条件，行为逐字不变。）A real write is essential: Mongo
        no-op updates do not fence a stale transaction against concurrent
        cancellation or permission revocation.
        """
        await legacy_document_fence(collection, document, "_reminder_fence",
            session=session, error_code="REMINDER_INVALID_FENCE",
            error_message="提醒并发字段无效")

    async def _recipients(self, record, session, mode):
        if mode == "canonical":
            return await self._canonical_recipients(record, session)
        # legacy：患者账号读取收敛到 legacy 患者适配器（LegacyPatientRepository.get）：
        # ObjectId/字符串双字面兼容，同键多文档由适配器 fail-closed
        # （PATIENT_IDENTITY_AMBIGUOUS），role=patient 由适配器保证；is_active
        # 判断按既有语义保留。账号缺失仍维持 PATIENT_ACCOUNT_UNAVAILABLE 兜底，
        # 收件人（recipient_id）依旧是账号 ID（见 app/patients/README.md）。
        identifier = record.get("patient_id")
        patient = (await LegacyPatientRepository(self.db).get(identifier, session=session)
                   if isinstance(identifier, str) and identifier else None)
        if not patient or patient.get("is_active") is not True:
            return [("patient", None, "PATIENT_ACCOUNT_UNAVAILABLE"),
                    ("provider", None, "PATIENT_ACCOUNT_UNAVAILABLE")], []
        slots, provider_accounts = await self._provider_slots(record, patient, session)
        return [("patient", patient, None)] + slots, [patient] + provider_accounts

    async def _canonical_recipients(self, record, session):
        # canonical（波次 3）：患者收件人解析经 patient_account_links——
        # clinical_patients 文档（可用性载体是 status 字段，不是 users.is_active）
        # → verified 链接 → 账号 is_active 校验。无链接、链接禁用、账号缺失或
        # 停用一律跳过患者收件人槽位，复用 legacy 的 PATIENT_ACCOUNT_UNAVAILABLE
        # 兜底语义（不新增错误码：该 reason 只进 DELIVERIES ledger 的诊断字段，
        # 收件人不可用的根因在两种域下对外语义一致）。
        # 患者临床文档缺失/停用时两个槽位一并跳过：legacy 语义下 provider 通知
        # 以患者上下文为前提，canonical 保持同构。
        identifier = record.get("patient_id")
        patient = (await ClinicalPatientRepository(self.db).get(identifier, session=session)
                   if isinstance(identifier, str) and identifier else None)
        if not patient or patient.get("status") != "active":
            return [("patient", None, "PATIENT_ACCOUNT_UNAVAILABLE"),
                    ("provider", None, "PATIENT_ACCOUNT_UNAVAILABLE")], []
        link = await self.db[ACCOUNT_LINKS].find_one(
            {"patient_id": str(identifier), "status": "verified"}, session=session)
        account = None
        if link:
            # 账号校验对齐 legacy is_active 语义（is_active 必须显式为 True）；
            # role=patient 防御校验：verified 链接只应指向患者账号。
            candidate = await self._account(str(link.get("account_id")), session)
            if (candidate and candidate.get("is_active") is True
                    and candidate.get("role") == "patient"):
                account = candidate
        slots, provider_accounts = await self._provider_slots(record, patient, session)
        if account is None:
            return [("patient", None, "PATIENT_ACCOUNT_UNAVAILABLE")] + slots, provider_accounts
        return [("patient", account, None)] + slots, [account] + provider_accounts

    async def _provider_slots(self, record, patient, session):
        """医护收件人槽位（两种域同构）：provider 是账号身份（users 直查），
        归属校验读患者文档的归属字段——legacy 读 users 同文档归属列表，
        canonical 读 clinical_patients 迁移保留的同名归属列表。返回除患者槽位
        外的槽位与账号列表（患者账号由调用方按域补齐）。"""
        provider = await self._account(record.get("provider_id"), session)
        reason = None
        if not provider or provider.get("is_active") is not True or provider.get("role") not in {"doctor", "health_manager"}:
            reason = "PROVIDER_ACCOUNT_UNAVAILABLE"
        else:
            field = "practitioners" if provider["role"] == "doctor" else "health_managers"
            assignments = patient.get(field)
            if not isinstance(assignments, list) or str(provider["_id"]) not in {str(item) for item in assignments}:
                reason = "PROVIDER_NOT_ASSIGNED"
        return [("provider", provider if not reason else None, reason)], \
            [provider] if not reason else []

    async def dispatch_one(self, followup_id):
        async def transaction(session):
            now = as_utc(self.clock())
            record = await self.followups.get_reminder_source(followup_id, session=session)
            if not record or record.get("deleted") or record.get("status") not in STATUSES:
                return {"outcome": "ineligible", "notifications": []}
            planned = as_utc(record.get("scheduled_date"))
            if not planned or planned > now + timedelta(hours=24):
                return {"outcome": "not_due", "notifications": []}
            # 域分派（波次 3 落地，T38 门闩已移除）：模式读取一次并贯穿本事务
            # （收件人解析与栅栏载体选择同源，避免两次读取间的状态翻转歧义）。
            # 显式 legacy 状态文档 {mode:"legacy"} 是回拨 SOP 载体，行为与无文档
            # legacy 完全一致；canonical 走链接解析 + 双载体栅栏；状态读取失败/
            # 未知状态时 patient_domain_mode 自然传播 503（fail-closed）。
            mode = await patient_domain_mode(self.db, session=session)
            slots, accounts = await self._recipients(record, session, mode)
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
                if mode == "canonical":
                    # 栅栏双载体（canonical）：随访来源文档自身的栅栏不动（载体
                    # 不是 users），账号侧计数落 account_fences（AccountFenceStore），
                    # 患者侧落 clinical_patients._fence_reminder
                    # （PatientFenceStore）。两跳在同一事务内整体提交/回滚，先后
                    # 顺序不承载语义。栅栏计数不迁移（core/fences.py §为什么栅栏
                    # 计数不迁移）：切换窗口内 legacy users 载体必须停止递增，
                    # canonical 载体从 0 重新起算——回拨后旧计数即失效，这是
                    # 切换窗口的硬约束（用户文档在 canonical 期保持只读）。
                    await PatientFenceStore(self.db).bump(
                        str(record["patient_id"]), "reminder", session=session)
                    for account in accounts:
                        await AccountFenceStore(self.db).bump(
                            str(account["_id"]), "reminder", session=session)
                else:
                    for account in accounts:
                        await self._fence(self.db.users, account, session)
            notifications = []
            for key, slot, account, reason in pending:
                # DELIVERIES ledger 的 patient_id 语义：取随访来源文档的
                # patient_id 字符串（legacy ID 主键），不是账号 ID——legacy 域
                # 二者同文档同值；canonical 域迁移患者的 clinical patient_id
                # 保留 legacy _id 字面量，无账号患者则是 clinical 主键本身。
                # 随访计划文档 patient_id 主键跨域不变（见
                # followup_service.py 扫描区声明），ledger 键随之一致，历史
                # 记录无需迁移。
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
        # 域分派逐记录进行：scan 本身只负责窗口游标与失败记账，canonical/
        # legacy 的收件人解析与栅栏载体差异全部收敛在 dispatch_one 事务内
        # （T38 的 scan 门闩已随波次 3 链接解析落地移除）。显式 legacy 状态
        # 文档 {mode:"legacy"} 是回拨 SOP 载体，行为与无文档 legacy 完全一致。
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


class FollowupDispositionRuntime:
    """逾期自动标记/失访自动判定的后台循环（T73）。

    独立于提醒运行时（不依赖 FOLLOWUP_REMINDERS_ENABLED）：每轮调用
    FollowupService.run_automated_disposition_scan（内部重读规则文档，含
    enabled 总开关与阈值，全部口径待临床确认）。单轮失败只记状态，循环继续。
    """

    def __init__(self):
        self.task = None
        self.status = {"enabled": False, "running": False, "state": "disabled",
                       "last_checked_at": None, "last_success_at": None,
                       "last_result": None, "last_error_code": None}

    async def start(self, db, *, interval):
        await self.stop()
        self.status.update(enabled=True, state="starting", last_error_code=None)
        try:
            await FollowupService(db).ensure_reminder_scan_index()
        except Exception:
            self.status.update(state="error", last_error_code="FOLLOWUP_DISPOSITION_STORAGE_UNAVAILABLE")
            logger.exception("Follow-up disposition scan disabled: storage requirements not met")
            return
        self.task = asyncio.create_task(self._run(db, interval))

    async def _run(self, db, interval):
        self.status.update(running=True)
        service = FollowupService(db)
        try:
            while True:
                self.status["last_checked_at"] = utc_now()
                try:
                    result = await service.run_automated_disposition_scan()
                    self.status.update(state="ready", last_success_at=utc_now(),
                                       last_result=result, last_error_code=None)
                except Exception as error:
                    self.status.update(state="error", last_error_code=(
                        error.error_code if isinstance(error, AppBaseException)
                        else "FOLLOWUP_DISPOSITION_SCAN_FAILED"))
                    logger.exception("Follow-up disposition scan failed; will retry")
                await asyncio.sleep(interval)
        finally:
            self.status["running"] = False

    async def stop(self):
        self.status.update(enabled=False)
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        self.status["running"] = False


disposition_runtime = FollowupDispositionRuntime()
