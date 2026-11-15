"""T66：统计/质控聚合的患者域感知专项（隔离副本集）。

覆盖两类无法用纯内存打桩如实验证的聚合（$lookup / 真实聚合语义）：

1. analytics_service.get_stats_overview 患者聚合源按域分派：
   - legacy（无状态文档）：users + role=="patient"，口径与历史版本逐字等价；
   - canonical（状态文档 mode=canonical）：clinical_patients +
     status=="active"，无账号患者（create_from_source 形态，无 users 文档）
     被如实计入（T55 演练实证的 patientCount 少算缺口）。

2. quality_process_queries.monitoring_pipeline 患者引用核验按域分派：
   - legacy：$lookup users 双键判定（停用用户 valid 但 issue_eligible=False）；
   - canonical：$lookup clinical_patients 主键判定（valid = 命中恰一篇且
     status=="active" 且引用一致；停用临床记录落入 not_found——canonical
     绝不复活 legacy 关系；missing/invalid 判定分支不变）；
   - 纯构造器契约（无库依赖，不门控）：默认 legacy 保持既有调用方行为
     逐字不变；非合法 patient_domain 一律 ValueError（不猜测域）。

门控：REHAB_TEST_PATIENT_AGGREGATE_URI（mongodb://127.0.0.1:<port>/...?
replicaSet=<name>），未显式提供时回退沿用 REHAB_TEST_PATIENT_MIGRATION_URI
（同一本机副本集惯例），两者都缺省时副本集用例全部跳过。每个用例使用独立
临时库（uuid 后缀）并在 teardown drop，只触碰 URI 指向实例上自己创建的库。

口径差异声明（T12 审计登记）：legacy created_at = 账号注册时间；canonical
的 created_at 对迁移患者继承 legacy 注册时间、对无账号患者是建档时间——
「新增患者」类序列跨域不可比，域切换瞬间存在口径漂移（已知限制）。
"""
import os
import unittest
from datetime import datetime, timedelta
from uuid import uuid4

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from app.patients.repository import SCHEMA_VERSION, STATE_ID
from app.services.analytics_service import AnalyticsService
from app.services.quality_process_queries import monitoring_pipeline

URI = (os.environ.get("REHAB_TEST_PATIENT_AGGREGATE_URI")
       or os.environ.get("REHAB_TEST_PATIENT_MIGRATION_URI"))
PATIENTS = "clinical_patients"


def _clinical_patient(patient_id, *, status="active", created_at=None):
    """canonical clinical_patients 文档最小形态（patient_id == str(_id) 主键
    不变量由迁移与 create_from_source 共同保证，见 patients/repository.py）。"""
    return {"_id": patient_id, "patient_id": patient_id, "schema_version": SCHEMA_VERSION,
            "status": status, "name": None, "practitioners": [], "health_managers": [],
            "created_at": created_at or datetime.utcnow()}


def _followup(patient_id, *, status="awaiting_fill"):
    doc = {"_id": ObjectId(), "patient_id": patient_id, "status": status,
           "scheduled_date": datetime.utcnow() + timedelta(days=1)}
    if patient_id is None:
        del doc["patient_id"]
    return doc


class MonitoringPipelineConstructorContractTests(unittest.TestCase):
    """纯构造器契约：不依赖数据库，任何环境都执行（不门控）。"""

    def test_default_domain_is_legacy_and_matches_legacy_stages(self):
        """默认 patient_domain="legacy"：与显式 legacy 的管道完全一致
        （既有调用方未传该参，行为逐字不变）。"""
        default = monitoring_pipeline("followup", None)
        explicit = monitoring_pipeline("followup", None, patient_domain="legacy")
        self.assertEqual(default, explicit)
        lookups = [stage["$lookup"]["from"] for stage in default
                   if "$lookup" in stage]
        self.assertTrue(lookups)  # 存在患者 $lookup
        self.assertIn("users", lookups)

    def test_canonical_domain_swaps_lookup_carrier(self):
        canonical = monitoring_pipeline("followup", None, patient_domain="canonical")
        lookups = [stage["$lookup"]["from"] for stage in canonical
                   if "$lookup" in stage]
        self.assertIn(PATIENTS, lookups)
        self.assertNotIn("users", lookups)

    def test_unknown_domain_refuses_to_guess(self):
        """非合法 patient_domain 一律 ValueError：构造器不读域开关也不猜域。"""
        for bad in ("unknown", "canonical ", "", None, "CLINICAL"):
            with self.assertRaises(ValueError):
                monitoring_pipeline("followup", None, patient_domain=bad)


@unittest.skipUnless(URI, "set REHAB_TEST_PATIENT_AGGREGATE_URI to an isolated local replica set")
class PatientAggregateDomainReplicaTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if not URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")):
            self.fail("only an explicit loopback test URI is accepted")
        self.client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.client["rehab_patient_aggregate_" + uuid4().hex]

    async def asyncTearDown(self):
        await self.client.drop_database(self.db.name)
        self.client.close()

    async def _seed_canonical_state(self):
        await self.db["patient_domain_state"].insert_one(
            {"_id": STATE_ID, "mode": "canonical", "schema_version": SCHEMA_VERSION})

    # ---- analytics 概览 ----

    async def test_legacy_overview_reads_users_without_state_document(self):
        now = datetime.utcnow()
        await self.db.users.insert_many([
            {"_id": ObjectId(), "role": "patient", "created_at": now - timedelta(days=30)},
            {"_id": ObjectId(), "role": "patient", "created_at": now},
            {"_id": ObjectId(), "role": "doctor", "created_at": now},
        ])
        stats = await AnalyticsService(self.db).get_stats_overview()
        self.assertEqual(stats["patientCount"], 2)
        self.assertEqual(stats["doctorCount"], 1)
        self.assertNotIn("patientCount", stats["dataAvailable"])  # 无降级标记

    async def test_canonical_overview_counts_accountless_clinical_patients(self):
        now = datetime.utcnow()
        await self._seed_canonical_state()
        await self.db[PATIENTS].insert_many([
            _clinical_patient(str(ObjectId()), created_at=now - timedelta(days=30)),
            _clinical_patient(str(ObjectId())),  # 无账号患者：无 users 文档
            _clinical_patient(str(ObjectId()), status="inactive", created_at=now),
        ])
        await self.db.users.insert_one(
            {"_id": ObjectId(), "role": "patient", "created_at": now})
        await self.db.users.insert_one(
            {"_id": ObjectId(), "role": "doctor", "created_at": now})

        stats = await AnalyticsService(self.db).get_stats_overview()
        self.assertEqual(stats["patientCount"], 2)  # active 临床患者含无账号；停用不计
        self.assertEqual(stats["doctorCount"], 1)
        self.assertNotIn("patientCount", stats["dataAvailable"])

    # ---- 质控引用核验 ----

    async def test_legacy_reference_judgment_unchanged(self):
        """legacy：users 双键判定口径不变（停用用户 valid 但不具备开单资格）。"""
        patient_oid = ObjectId()
        inactive_oid = ObjectId()
        await self.db.users.insert_many([
            {"_id": patient_oid, "role": "patient", "is_active": True},
            {"_id": inactive_oid, "role": "patient", "is_active": False},
        ])
        await self.db.followup_records.insert_many([
            _followup(str(patient_oid)),
            _followup(str(inactive_oid)),  # 停用用户
        ])
        rows = await self.db.followup_records.aggregate(
            monitoring_pipeline("followup", None, patient_domain="legacy",
                                include_items=True)).to_list(1)
        references = {row["_id"]: row["count"]
                      for row in rows[0]["patient_references"]}
        self.assertEqual(references.get("valid"), 2)
        items = sorted(rows[0]["items"], key=lambda item: item["issue_eligible"])
        self.assertFalse(items[0]["issue_eligible"])  # 停用用户引用
        self.assertTrue(items[1]["issue_eligible"])

    async def test_canonical_reference_judgment_follows_clinical_status(self):
        """canonical：clinical_patients 主键判定——active 命中=valid 且具备开单
        资格；停用临床记录=not_found（绝不复活）；缺引用=missing。"""
        active_id, inactive_id = str(ObjectId()), str(ObjectId())
        await self._seed_canonical_state()
        await self.db[PATIENTS].insert_many([
            _clinical_patient(active_id),
            _clinical_patient(inactive_id, status="inactive"),
        ])
        await self.db.followup_records.insert_many([
            _followup(active_id),
            _followup(inactive_id),
            _followup(None),  # 缺 patient_id
        ])

        rows = await self.db.followup_records.aggregate(
            monitoring_pipeline("followup", None, patient_domain="canonical",
                                include_items=True)).to_list(1)
        references = {row["_id"]: row["count"]
                      for row in rows[0]["patient_references"]}
        self.assertEqual(references.get("valid"), 1)
        self.assertEqual(references.get("not_found"), 1)  # 停用临床记录
        self.assertEqual(references.get("missing"), 1)

        eligible = {item["patient_id"]: item["issue_eligible"]
                    for item in rows[0]["items"]}
        self.assertEqual(eligible, {active_id: True, inactive_id: False, None: False})

    async def test_canonical_reference_judgment_never_reads_users(self):
        """canonical 载体是 clinical_patients：users 里的患者账号同文档不参与
        判定（无账号患者的引用不因 users 缺文档而误判）。"""
        clinical_id = str(ObjectId())
        await self._seed_canonical_state()
        await self.db[PATIENTS].insert_one(_clinical_patient(clinical_id))
        # 同字面量 users 文档存在（迁移存量账号），canonical 下不得据此判定
        await self.db.users.insert_one(
            {"_id": ObjectId(clinical_id), "role": "patient", "is_active": True})
        await self.db.followup_records.insert_one(_followup(clinical_id))

        rows = await self.db.followup_records.aggregate(
            monitoring_pipeline("followup", None, patient_domain="canonical")).to_list(1)
        references = {row["_id"]: row["count"]
                      for row in rows[0]["patient_references"]}
        self.assertEqual(references.get("valid"), 1)


if __name__ == "__main__":
    unittest.main()
