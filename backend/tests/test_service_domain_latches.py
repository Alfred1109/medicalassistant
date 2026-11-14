"""服务域分派的显式 legacy 兼容与 fail-closed 验收（fake 内存库）。

T35 显式 legacy（{mode:"legacy", schema_version:1} 回拨 SOP 载体）落地后的
联动验收。T65（波次 3）后 reminder dispatch_one/scan 的
REMINDER_PATIENT_DOMAIN_UNSUPPORTED 门闩已移除（canonical 收件人解析经
patient_account_links），本文件的提醒用例改为验证：显式 legacy 与无文档
legacy 行为完全一致（users 载体栅栏）、canonical 域下不可解析的患者槽位
fail-closed 跳过（不投递不报错）、状态读取失败经 patient_domain_mode
fail-closed 传播 503。

rehab_publication 的 REHAB_PATIENT_DOMAIN_UNSUPPORTED 门闩已在患者域
波次 2 移除（canonical 分派落地，见 rehab_publication_service._authorize），
其门闩用例随之删除；显式 legacy 不误伤 503 的语义由该服务的域分派实现
本身与康复域副本集测试覆盖。

全部使用内存 fake（不依赖真实 Mongo），fake 语义参照
test_patient_domain_dispatch.py（$in 严格相等、状态单例集合）。
"""
import unittest
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

from bson import ObjectId
from pymongo.errors import PyMongoError

from test_patient_domain_dispatch import FakeCollection, FakeCursor, _matches

from app.core.exceptions import AppBaseException
from app.patients.repository import SCHEMA_VERSION, STATE_ID
from app.services.followup_reminder_service import FollowupReminderService
from app.services.quality_issue_service import QualityIssueService
from app.services.quality_monitoring_service import QualityMonitoringService

EXPLICIT_LEGACY_STATE = {"_id": STATE_ID, "mode": "legacy", "schema_version": SCHEMA_VERSION}
CANONICAL_STATE = {"_id": STATE_ID, "mode": "canonical", "schema_version": SCHEMA_VERSION}
DOCTOR_ID, PATIENT_ID = str(ObjectId()), str(ObjectId())


class LatchCursor(FakeCursor):
    """补齐 followup 候选游标的 sort 链式调用。"""

    def sort(self, *args, **kwargs):
        return self


class LatchCollection(FakeCollection):
    """dispatch fake 基础上补齐提醒派发所需的写入与排序接口。"""

    def find(self, query, projection=None, **kwargs):
        return LatchCursor([deepcopy(document) for document in self.documents
                            if _matches(document, query)])

    async def insert_one(self, document, *args, **kwargs):
        self.documents.append(deepcopy(document))
        return SimpleNamespace(inserted_id=document.get("_id"))

    async def update_one(self, query, update, *args, upsert=False, **kwargs):
        for document in self.documents:
            if _matches(document, query):
                for key, value in (update.get("$set") or {}).items():
                    document[key] = deepcopy(value)
                for key, value in (update.get("$inc") or {}).items():
                    document[key] = document.get(key, 0) + value
                return SimpleNamespace(modified_count=1, matched_count=1, upserted_id=None)
        if upsert:
            document = {"_id": query.get("_id"), **deepcopy(update.get("$set") or {})}
            self.documents.append(document)
            return SimpleNamespace(modified_count=0, matched_count=0, upserted_id=document["_id"])
        return SimpleNamespace(modified_count=0, matched_count=0, upserted_id=None)

    async def count_documents(self, query, *args, **kwargs):
        return sum(1 for document in self.documents if _matches(document, query))


class BrokenStateCollection(LatchCollection):
    """模拟状态读取的传输层失败（fail-closed 传播断言用）。"""

    async def find_one(self, query, *args, **kwargs):
        raise PyMongoError("synthetic state read failure")


class LatchSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def with_transaction(self, callback, **kwargs):
        return await callback(self)


class LatchClient:
    def __init__(self, database):
        self._database = database

    async def start_session(self):
        return LatchSession()


class LatchDatabase:
    """属性与下标均可取集合；未知集合惰性创建（对齐 motor 代理语义）。"""

    def __init__(self, state=None, users=(), state_collection=None):
        self.patient_domain_state = (state_collection if state_collection is not None
                                     else LatchCollection([state] if state else []))
        self.users = LatchCollection(list(users))

    @property
    def client(self):
        return LatchClient(self)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        collection = LatchCollection()
        self.__dict__[name] = collection
        return collection

    def __getitem__(self, name):
        return getattr(self, name)


def doctor_document():
    return {"_id": ObjectId(DOCTOR_ID), "role": "doctor", "is_active": True, "name": "Clinician"}


def patient_document():
    return {"_id": ObjectId(PATIENT_ID), "role": "patient", "is_active": True,
            "name": "Patient", "practitioners": [DOCTOR_ID], "health_managers": []}


class QualityIssueLatchTests(unittest.IsolatedAsyncioTestCase):
    """quality_issue_service 的域分派判定（T63 波次 2 门闩移除后）。

    canonical 不再拒绝 actor 账号复核（账号域仍在 users）；患者实体读取
    经内核 load_patient_doc 分派，状态读取失败仍 fail-closed 503 透传。
    """

    async def test_explicit_legacy_state_keeps_actor_gate_working(self):
        svc = QualityIssueService(LatchDatabase(state=dict(EXPLICIT_LEGACY_STATE),
                                                users=[doctor_document()]))
        account = await svc._actor(SimpleNamespace(id=DOCTOR_ID, role="doctor"), write=True)
        self.assertEqual(str(account["_id"]), DOCTOR_ID)

    async def test_canonical_state_actor_check_proceeds_and_patient_read_fails_closed(self):
        svc = QualityIssueService(LatchDatabase(state=dict(CANONICAL_STATE),
                                                users=[doctor_document()]))
        account = await svc._actor(SimpleNamespace(id=DOCTOR_ID, role="doctor"), write=True)
        self.assertEqual(str(account["_id"]), DOCTOR_ID)
        # 患者域分派：canonical 状态下患者实体走 clinical_patients（fake 为
        # 空 → 映射回本域 404），绝不回读 users。
        with self.assertRaises(AppBaseException) as unavailable:
            await svc._patient(str(ObjectId()), SimpleNamespace(id=DOCTOR_ID, role="doctor"), write=True)
        self.assertEqual(unavailable.exception.status_code, 404)
        self.assertEqual(unavailable.exception.error_code, "QUALITY_PATIENT_UNAVAILABLE")

    async def test_unreadable_state_propagates_fail_closed_503(self):
        db = LatchDatabase(state_collection=BrokenStateCollection(), users=[doctor_document()])
        svc = QualityIssueService(db)
        with self.assertRaises(AppBaseException) as caught:
            await svc._patient(str(ObjectId()), SimpleNamespace(id=DOCTOR_ID, role="doctor"), write=True)
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(caught.exception.error_code, "PATIENT_DOMAIN_STATE_UNAVAILABLE")


class QualityMonitoringLatchTests(unittest.IsolatedAsyncioTestCase):
    """quality_monitoring_service.scope 的域分派判定（T63 波次 3 门闩移除后）。

    canonical 范围解析走域感知内核（clinical_patients），不再 503；legacy
    （无状态文档与显式 legacy 载体）行为不变。
    """

    async def test_explicit_legacy_state_keeps_scope_resolution_working(self):
        svc = QualityMonitoringService(LatchDatabase(
            state=dict(EXPLICIT_LEGACY_STATE), users=[doctor_document(), patient_document()]))
        scope = await svc.scope(SimpleNamespace(id=DOCTOR_ID, role="doctor"))
        self.assertEqual(scope, [PATIENT_ID])

    async def test_canonical_state_scope_resolves_from_clinical_domain(self):
        # clinical_patients 为空（fake 惰性建集合）：canonical 范围解析执行于
        # clinical_patients 并返回空集，而不是回读 users 里的患者文档。
        svc = QualityMonitoringService(LatchDatabase(
            state=dict(CANONICAL_STATE), users=[doctor_document(), patient_document()]))
        self.assertEqual(await svc.scope(SimpleNamespace(id=DOCTOR_ID, role="doctor")), [])

    async def test_unreadable_state_propagates_fail_closed_503(self):
        svc = QualityMonitoringService(LatchDatabase(
            state_collection=BrokenStateCollection(), users=[doctor_document(), patient_document()]))
        with self.assertRaises(AppBaseException) as caught:
            await svc.scope(SimpleNamespace(id=DOCTOR_ID, role="doctor"))
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(caught.exception.error_code, "PATIENT_DOMAIN_STATE_UNAVAILABLE")


class ReminderLatchTests(unittest.IsolatedAsyncioTestCase):
    """followup_reminder_service 域分派（波次 3 后无 503 门闩）。

    T65 起提醒链路 canonical 分支经 patient_account_links 解析收件人、栅栏走
    双载体（fence store），域门闩已移除：本类只验证——显式 legacy 与无文档
    legacy 行为一致（users 载体栅栏）、canonical 域下无临床文档的患者槽位
    fail-closed 跳过（fake 无 clinical_patients 数据即全体不可用，不投递不报
    错）、状态读取失败经 patient_domain_mode 传播 503。canonical 全流程见
    test_followup_reminders.py 与 test_canonical_accountless_loop.py。
    """

    def reminder_record(self, now):
        from datetime import timedelta
        return {"_id": ObjectId(), "deleted": False, "status": "scheduled",
                "scheduled_date": now + timedelta(hours=2), "patient_id": PATIENT_ID}

    async def test_explicit_legacy_state_keeps_dispatch_and_scan_working(self):
        now = datetime(2026, 11, 14, 8)
        db = LatchDatabase(state=dict(EXPLICIT_LEGACY_STATE),
                           users=[doctor_document(), patient_document()])
        record = self.reminder_record(now)
        await db["followup_records"].insert_one(record)
        svc = FollowupReminderService(db, clock=lambda: now)
        self.assertEqual(await svc.scan(), 0)
        result = await svc.dispatch_one(str(record["_id"]))
        self.assertEqual(result, {"outcome": "checked", "generated": 1})
        self.assertEqual(await db.notifications.count_documents({}), 1)
        persisted = await db["followup_reminder_deliveries"].find_one({"status": "persisted"})
        self.assertIsNotNone(persisted)
        fenced = await db.users.find_one({"_id": ObjectId(PATIENT_ID)})
        self.assertGreater(fenced.get("_reminder_fence", 0), 0)

    async def test_canonical_state_skips_unresolvable_patients_instead_of_503(self):
        now = datetime(2026, 11, 14, 8)
        db = LatchDatabase(state=dict(CANONICAL_STATE),
                           users=[doctor_document(), patient_document()])
        record = self.reminder_record(now)
        await db["followup_records"].insert_one(record)
        svc = FollowupReminderService(db, clock=lambda: now)
        self.assertEqual(await svc.scan(), 0)
        result = await svc.dispatch_one(str(record["_id"]))
        self.assertEqual(result, {"outcome": "checked", "generated": 0})
        self.assertEqual(await db.notifications.count_documents({}), 0)
        # 槽位全部不可用：不写 users 栅栏（canonical 不再打点 users 载体）
        fenced = await db.users.find_one({"_id": ObjectId(PATIENT_ID)})
        self.assertNotIn("_reminder_fence", fenced)
        skipped = await db["followup_reminder_deliveries"].find_one(
            {"slot": "patient", "reason": "PATIENT_ACCOUNT_UNAVAILABLE"})
        self.assertIsNotNone(skipped)

    async def test_unreadable_state_propagates_fail_closed_503(self):
        now = datetime(2026, 11, 14, 8)
        db = LatchDatabase(state_collection=BrokenStateCollection(),
                           users=[doctor_document(), patient_document()])
        record = self.reminder_record(now)
        await db["followup_records"].insert_one(record)
        svc = FollowupReminderService(db, clock=lambda: now)
        with self.assertRaises(AppBaseException) as caught:
            await svc.dispatch_one(str(record["_id"]))
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(caught.exception.error_code, "PATIENT_DOMAIN_STATE_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
