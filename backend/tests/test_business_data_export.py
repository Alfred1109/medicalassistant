"""Bounded business export retains patient data and claims no recoverability."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.operations.data_export import EXPORT_COLLECTIONS, data_export_bytes
from app.operations.runtime import BackupSchedule, build_backup, public_settings

from bson import ObjectId
from pymongo.errors import PyMongoError
from app.patients.repository import SCHEMA_VERSION, STATE as DOMAIN_STATE, STATE_ID, PatientDomainError
from app.operations.data_export import EXPORT_COLLECTIONS, data_export_bytes
from app.operations.runtime import BackupSchedule, build_backup, public_settings


class Collection:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def find(self, query):
        async def cursor():
            for row in self.rows:
                yield deepcopy(row)
        return cursor()


class Database:
    def __init__(self, rows=None, settings=None):
        self.rows = rows or {}
        self.setting_row = deepcopy(settings or {})
        self.system_settings = AsyncMock()
        self.system_settings.find_one.side_effect = self.read_settings
        self.system_settings.update_one.side_effect = self.write_settings

    async def read_settings(self, query):
        return deepcopy(self.setting_row)

    async def write_settings(self, query, update, **options):
        self.setting_row.update(update["$set"])

    def __getitem__(self, name):
        return Collection(self.rows.get(name, []))


class DomainStateCollection:
    """patient_domain_state 集合的最小假件（T53 域感知 manifest 断言用）。"""

    def __init__(self, doc=None, error=None):
        self.doc = doc
        self.error = error

    async def find_one(self, query):
        if self.error is not None:
            raise self.error
        return deepcopy(self.doc)


class DomainDatabase(Database):
    def __init__(self, rows=None, settings=None, state_doc=None, state_error=None):
        super().__init__(rows, settings)
        self.patient_domain_state = DomainStateCollection(state_doc, state_error)


class PatientDomainModeManifestTests(unittest.IsolatedAsyncioTestCase):
    """T53（B4）：导出 manifest 记录患者域模式（legacy / canonical / unknown）。

    域状态读取失败必须 fail-safe 标注 unknown，绝不阻断导出本体。
    """

    async def manifest(self, db):
        return json.loads(await data_export_bytes(db))["manifest"]

    async def test_database_without_state_document_reports_legacy(self):
        manifest = await self.manifest(Database({"users": [{"role": "patient"}]}))
        self.assertEqual(manifest["patient_domain_mode"], "legacy")

    async def test_canonical_state_is_recorded_without_changing_scope(self):
        db = DomainDatabase(state_doc={"_id": STATE_ID, "mode": "canonical",
                                       "schema_version": SCHEMA_VERSION})
        manifest = await self.manifest(db)
        self.assertEqual(manifest["patient_domain_mode"], "canonical")
        # 感知不改清单：canonical 的集合波次调整属患者域后续工作，scope 保持
        # legacy 全量形态（以 manifest 的 limitations 说明为准解读）
        self.assertEqual(manifest["collection_scope"], list(EXPORT_COLLECTIONS))

    async def test_broken_domain_state_reports_unknown_without_blocking_export(self):
        db = DomainDatabase(rows={"users": [{"role": "patient"}]},
                            state_error=PatientDomainError("PATIENT_DOMAIN_STATE_UNAVAILABLE"))
        value = json.loads(await data_export_bytes(db))
        self.assertEqual(value["manifest"]["patient_domain_mode"], "unknown")
        self.assertEqual(value["collections"]["users"]["count"], 1)

    async def test_transport_failure_reports_unknown(self):
        db = DomainDatabase(state_error=PyMongoError("connection reset"))
        manifest = await self.manifest(db)
        self.assertEqual(manifest["patient_domain_mode"], "unknown")


class BusinessExportTests(unittest.IsolatedAsyncioTestCase):
    async def test_manifest_distinguishes_limit_from_actual_truncation(self):
        db = Database({"users": [{"_id": ObjectId(), "name": "Synthetic patient", "hashed_password": "secret",
            "nested": {"access_token": "token", "value": "kept"}}] * 2001,
            "tags": [{"name": "tag"}] * 2000})
        value = json.loads(await data_export_bytes(db))
        manifest = value["manifest"]
        self.assertFalse(manifest["restorable"])
        self.assertTrue(manifest["contains_patient_information"])
        self.assertEqual(manifest["collection_scope"], list(EXPORT_COLLECTIONS))
        self.assertEqual(manifest["truncated_collections"], ["users"])
        self.assertEqual(value["collections"]["users"]["count"], 2000)
        self.assertFalse(value["collections"]["tags"]["truncated"])
        row = value["collections"]["users"]["rows"][0]
        self.assertIsInstance(row["_id"], str)
        self.assertEqual(row["name"], "Synthetic patient")
        self.assertEqual(row["nested"], {"value": "kept"})
        self.assertNotIn("hashed_password", row)

    async def test_manual_download_preserves_compatibility_and_scheduled_time(self):
        last = datetime.now(timezone.utc)
        db = Database(settings={"last_backup_at": last, "last_scheduled_export_at": last})
        response = await build_backup(db)
        self.assertEqual(response.headers["content-disposition"], "attachment; filename=rehab-backup.json")
        self.assertEqual(response.headers["x-database-restorable"], "false")
        self.assertEqual(db.setting_row["last_backup_at"], last)
        self.assertEqual(db.setting_row["last_scheduled_export_at"], last)
        self.assertIn("last_data_export_at", db.setting_row)
        self.assertIn("collections", json.loads(response.body))

    async def test_scheduler_reads_legacy_time_but_manual_download_cannot_postpone_it(self):
        now = datetime.now(timezone.utc)
        for settings in ({"last_backup_at": now}, {"last_scheduled_export_at": now}):
            db = Database(settings=settings)
            with patch("app.operations.runtime.backup_bytes", new_callable=AsyncMock) as export:
                await BackupSchedule().run_if_due(db)
                export.assert_not_called()
        value = public_settings({"last_backup_at": now})
        self.assertEqual(value["last_backup_at"], now)
        self.assertIsNone(value["last_scheduled_export_at"])


# 与 runtime.py 领取条件中的非 date 标量类型清单保持一致（B1）
LEGACY_SCALAR_TYPES = ["string", "int", "long", "double"]

# BSON $type 值到 Python 类型的近似映射（fake 只需覆盖用例用到的形态）
_BSON_TYPE_OF = {
    datetime: "date",
    str: "string",
    float: "double",
}


def _bson_type_of(value):
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        # Python int 按 BSON 编码可能是 int32 或 int64，fake 两种都认
        return "int"
    return _BSON_TYPE_OF.get(type(value))


def _leg_matches(doc, leg):
    """对 T37 领取条件的单个 $or 分支做 Mongo 语义匹配（仅覆盖用到的算子）。"""
    for field, cond in leg.items():
        present = doc is not None and field in doc
        value = doc.get(field) if doc is not None else None
        if isinstance(cond, dict):
            if "$exists" in cond and cond["$exists"] != present:
                return False
            if "$type" in cond:
                allowed = cond["$type"] if isinstance(cond["$type"], list) else [cond["$type"]]
                if value is None or _bson_type_of(value) not in allowed:
                    return False
            if "$lte" in cond:
                # 类型限定：非 datetime（含 null/缺失）不匹配 $lte
                if not isinstance(value, datetime) or value > cond["$lte"]:
                    return False
            if "$eq" in cond and value != cond["$eq"]:
                return False
        elif value != cond:
            # 等值匹配：Mongo 的 field: None 同时匹配缺失与 null
            return False
    return True


def _claim_query_matches(doc, query):
    for field, cond in query.items():
        if field == "$or":
            if not any(_leg_matches(doc, leg) for leg in cond):
                return False
        elif doc is None or doc.get(field) != cond:
            return False
    return True


class ClaimSettingsCollection:
    """system_settings 的最小假件：记录领取调用，按当前文档求值 find_one_and_update。"""

    def __init__(self, doc=None):
        self.doc = dict(doc) if doc else None
        self.claims = []
        # 模拟并发方在本进程 find_one 之后、领取之前抢先改写文档
        self.concurrent_doc = None

    async def find_one(self, query):
        return deepcopy(self.doc)

    async def find_one_and_update(self, query, update, upsert=False, return_document=None):
        self.claims.append(deepcopy(query))
        if self.concurrent_doc is not None:
            self.doc = deepcopy(self.concurrent_doc)
        if self.doc is None:
            # 真 Mongo：文档缺失 + upsert → 无条件插入并返回（ReturnDocument.AFTER）
            if upsert:
                self.doc = {"_id": query["_id"], **update["$set"]}
                return deepcopy(self.doc)
            return None
        if not _claim_query_matches(self.doc, query):
            if upsert:
                # 文档存在但 filter 落空 + upsert → 撞唯一 _id（真 Mongo 的输家路径）
                from pymongo.errors import DuplicateKeyError
                raise DuplicateKeyError("E11000 duplicate key: _id system")
            return None
        self.doc = {"_id": query["_id"], **self.doc, **update["$set"]}
        return deepcopy(self.doc)


class ScheduledClaimTests(unittest.IsolatedAsyncioTestCase):
    """T37：备份调度原子领取的条件构造（无 Mongo，纯单元）。"""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rehab-t37-unit-")
        os.makedirs(os.path.join(self.root, "app", "operations"), exist_ok=True)
        self.fake_file = os.path.join(self.root, "app", "operations", "runtime.py")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def db(self, doc=None, concurrent_doc=None):
        settings = ClaimSettingsCollection(doc)
        settings.concurrent_doc = concurrent_doc
        return SimpleNamespace(system_settings=settings), settings

    async def run_schedule(self, db, export_calls):
        async def counting_backup_bytes(mock_db):
            export_calls.append(mock_db)
            return b"{}"

        with patch("app.operations.runtime.backup_bytes", counting_backup_bytes), \
             patch("app.operations.runtime.__file__", self.fake_file):
            await BackupSchedule().run_if_due(db)
        folder = os.path.join(self.root, "data", "backups")
        return os.listdir(folder) if os.path.isdir(folder) else []

    async def test_due_row_claims_with_upsert_and_exports_once(self):
        old = datetime.now(timezone.utc) - timedelta(hours=2)
        db, settings = self.db({"_id": "system", "backup_frequency": "hourly",
                                "last_scheduled_export_at": old})
        files = await self.run_schedule(db, [])
        # 领取条件：_id 锁定 system + 到点 $or 分支；upsert 保持首次初始化语义
        self.assertEqual(len(settings.claims), 1)
        claim = settings.claims[0]
        self.assertEqual(claim["_id"], "system")
        legs = claim["$or"]
        self.assertEqual(len(legs), 6)
        # 主分支的 cutoff 按 hourly 频率取 now - 1h（领取先于导出的 $set 时间戳）
        cutoff = legs[0]["last_scheduled_export_at"]["$lte"]
        self.assertAlmostEqual((datetime.now(timezone.utc) - cutoff).total_seconds(),
                               3600, delta=15)
        # B1：date 主分支带显式 $type 栅栏；非 date 标量（legacy 外部写入的
        # string/int/long/double 时间戳）单列到点分支，避免跨类型 $lte 落空
        self.assertEqual(legs[0], {"last_scheduled_export_at": {"$type": "date", "$lte": cutoff}})
        self.assertEqual(legs[1], {"last_scheduled_export_at": {"$type": LEGACY_SCALAR_TYPES}})
        self.assertEqual(legs[2], {"last_scheduled_export_at": None,
                                   "last_backup_at": {"$type": "date", "$lte": cutoff}})
        self.assertEqual(legs[3], {"last_scheduled_export_at": None,
                                   "last_backup_at": {"$type": LEGACY_SCALAR_TYPES}})
        self.assertEqual(legs[4], {"last_scheduled_export_at": None,
                                   "last_backup_at": None})
        self.assertEqual(legs[5], {"last_scheduled_export_at": {"$eq": None, "$exists": True}})
        # $set 领取时间戳（领取先于导出）
        self.assertIn("last_scheduled_export_at", settings.doc)
        self.assertGreater(settings.doc["last_scheduled_export_at"], old)
        self.assertEqual(len(files), 1)

    async def test_not_due_row_never_attempts_claim(self):
        recent = datetime.now(timezone.utc) - timedelta(minutes=10)
        db, settings = self.db({"_id": "system", "backup_frequency": "daily",
                                "last_scheduled_export_at": recent})
        calls = []
        files = await self.run_schedule(db, calls)
        self.assertEqual(settings.claims, [])
        self.assertEqual(files, [])

    async def test_legacy_row_claims_through_backup_at_fallback(self):
        # 无 backup_frequency 的行走 daily 默认窗口，种子须超 24h
        old = datetime.now(timezone.utc) - timedelta(hours=48)
        db, settings = self.db({"_id": "system", "last_backup_at": old})
        calls = []
        files = await self.run_schedule(db, calls)
        self.assertEqual(len(settings.claims), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(files), 1)
        # 领取写入 last_scheduled_export_at，legacy last_backup_at 不被改写
        self.assertGreater(settings.doc["last_scheduled_export_at"], old)
        self.assertEqual(settings.doc["last_backup_at"], old)

    async def test_recent_legacy_row_skips(self):
        recent = datetime.now(timezone.utc) - timedelta(minutes=10)
        db, settings = self.db({"_id": "system", "last_backup_at": recent})
        calls = []
        files = await self.run_schedule(db, calls)
        self.assertEqual(settings.claims, [])
        self.assertEqual(calls, [])
        self.assertEqual(files, [])

    async def test_string_timestamp_row_claims_and_normalizes_to_date(self):
        # B1 回归：legacy 外部脚本把调度时间戳写成字符串——Python 预判视同到点，
        # Mongo 领取必须命中非 date 标量分支并完成领取（修复前 $lte 跨类型落空
        # → upsert 撞 _id → DuplicateKeyError 静默 return → 永久停摆）
        db, settings = self.db({"_id": "system", "backup_frequency": "hourly",
                                "last_scheduled_export_at": "2026-01-01T00:00:00Z"})
        calls = []
        files = await self.run_schedule(db, calls)
        self.assertEqual(len(settings.claims), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(files), 1)
        # 领取写回 date，字符串形态被归一化
        self.assertIsInstance(settings.doc["last_scheduled_export_at"], datetime)
        self.assertEqual(settings.doc["last_scheduled_export_at"].tzinfo, timezone.utc)

    async def test_int_timestamp_row_claims_and_normalizes_to_date(self):
        # B1 回归：整型（epoch 秒）形态的 legacy 时间戳同样到点领取并归一化
        db, settings = self.db({"_id": "system", "backup_frequency": "hourly",
                                "last_scheduled_export_at": 1760000000})
        calls = []
        files = await self.run_schedule(db, calls)
        self.assertEqual(len(settings.claims), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(files), 1)
        self.assertIsInstance(settings.doc["last_scheduled_export_at"], datetime)

    async def test_int_backup_at_fallback_row_claims(self):
        # B1：调度时间戳缺失、legacy last_backup_at 为整型形态时同样到点
        db, settings = self.db({"_id": "system", "backup_frequency": "hourly",
                                "last_backup_at": 0})
        calls = []
        files = await self.run_schedule(db, calls)
        self.assertEqual(len(settings.claims), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(files), 1)
        self.assertIsInstance(settings.doc["last_scheduled_export_at"], datetime)
        # legacy last_backup_at 本身不被改写
        self.assertEqual(settings.doc["last_backup_at"], 0)

    async def test_missing_row_upserts_and_exports(self):
        db, settings = self.db(None)
        calls = []
        files = await self.run_schedule(db, calls)
        self.assertEqual(len(settings.claims), 1)
        self.assertEqual(settings.claims[0]["_id"], "system")
        self.assertEqual(settings.doc["_id"], "system")
        self.assertIn("last_scheduled_export_at", settings.doc)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(files), 1)

    async def test_lost_claim_to_concurrent_writer_skips_export(self):
        # find_one 读到旧行后，并发方抢先领取；领取 filter 对新文档落空
        #（真 Mongo 走 upsert 撞唯一 _id 的 DuplicateKeyError 路径），
        # 本进程必须安静跳过、绝不执行导出。
        old = datetime.now(timezone.utc) - timedelta(hours=2)
        winner_ts = datetime.now(timezone.utc)
        db, settings = self.db(
            {"_id": "system", "backup_frequency": "hourly",
             "last_scheduled_export_at": old},
            concurrent_doc={"_id": "system", "backup_frequency": "hourly",
                            "last_scheduled_export_at": winner_ts})
        calls = []
        files = await self.run_schedule(db, calls)
        self.assertEqual(len(settings.claims), 1)
        self.assertEqual(calls, [])
        self.assertEqual(files, [])
        # 赢家的领取时间戳未被本进程覆盖
        self.assertEqual(settings.doc["last_scheduled_export_at"], winner_ts)
