"""T26 演练：患者域第二波段端到端验收链路（cutover plan G2 证据的测试化）。

门控：REHAB_TEST_PATIENT_E2E_URI（mongodb://127.0.0.1:<port>/...?replicaSet=<name>）。
迁移依赖快照事务、栅栏双载体依赖 run_transaction，standalone 无法执行；无 URI 全部跳过。
每个用例使用独立临时库（uuid 后缀）并在 teardown drop，只触碰 URI 指向实例上自己创建的库。

主链用例把「迁移→canonical 启用→内核域分派→业务域读取→栅栏双载体」串成一条链；
辅以 noop 漂移联动、回拨口径、失败注入三个分场景用例。断言依据
migration.py / repository.py / core/patient_access.py / core/followup_access.py /
core/device_access.py / core/fences.py 的真实语义；首轮演练发现的构件缺口
1（范围查询载体错位）与 2（canonical status 未被对象访问消费）已修复并以
修复后行为断言（见 test_business_scope_and_object_access_in_canonical_mode），
缺口 3（回拨 SOP）以 docs/patient-domain-cutover-plan.md 的回拨口径章节
收口，缺口 4（迁移失败残留空索引集合，良性运维残留）仍在对应用例注释中记录。
"""
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.device_access import device_patient_scope, resolve_device_patient
from app.core.fences import (ACCOUNT_FENCES, AccountFenceStore, FenceMismatch,
                             PatientFenceStore, create_account_fence_indexes, dual_bump)
from app.core.followup_access import ensure_followup_patient_access, followup_patient_scope
from app.core.patient_access import (PatientAccessError, assigned_scope_query,
                                     ensure_patient_access, ensure_self_patient_access,
                                     load_patient_doc, patient_domain_mode)
from app.db.transactions import run_transaction
from app.patients.migration import fingerprint, inspect_migration, migrate_legacy_patients
from app.patients.repository import (ACCOUNT_LINKS, PATIENTS, STATE, STATE_ID,
                                     ClinicalPatientRepository, PatientDomainError)

URI = os.environ.get("REHAB_TEST_PATIENT_E2E_URI")

DOCTOR = "drill-doctor"
OTHER_DOCTOR = "drill-doctor-unassigned"
MANAGER = "drill-manager"
MARKER = "e2e_drill_rollback_marker"


def actor(account_id, role):
    """最小认证主体替身：内核只消费 id/role 两个属性。"""
    return type("DrillActor", (), {"id": account_id, "role": role})()


class UsersReadSpy:
    """users 集合读计数代理：区分「读作患者文档」与「读作账号复核」。"""

    def __init__(self, collection):
        self._collection = collection
        self.find_calls = 0

    def find(self, *args, **kwargs):
        self.find_calls += 1
        return self._collection.find(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._collection, name)


class SpyDatabase:
    """只拦截 users 的透明数据库代理；其余集合/属性原样透传。"""

    def __init__(self, db):
        self._db = db
        self.users = UsersReadSpy(db.users)

    def __getitem__(self, name):
        return self._db[name]

    def __getattr__(self, name):
        return getattr(self._db, name)


@unittest.skipUnless(URI, "set REHAB_TEST_PATIENT_E2E_URI to an isolated local replica set")
class PatientDomainE2EDrillTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if not URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")):
            self.fail("only an explicit loopback test URI is accepted")
        self.client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.client["rehab_patient_e2e_drill_" + uuid4().hex]
        self.repo = ClinicalPatientRepository(self.db)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    async def asyncTearDown(self):
        await self.client.drop_database(self.db.name)
        self.client.close()
        self.temp.cleanup()

    @staticmethod
    def stopped():
        return {"application_stopped": True, "guard_reference": "e2e-drill-fixture"}

    async def migrate(self, **overrides):
        options = dict(expected_manifest=await inspect_migration(self.db),
                       backup_directory=self.root / uuid4().hex,
                       reviewer="e2e-drill-reviewer",
                       evidence_reference="e2e-drill-evidence",
                       maintenance_guard=self.stopped)
        options.update(overrides)
        return await migrate_legacy_patients(self.db, **options)

    async def seed_users(self, documents):
        await self.db.users.insert_many([deepcopy(item) for item in documents])

    async def users_snapshot(self):
        return await self.db.users.find({}).sort("_id", 1).to_list(None)

    async def domain_counts(self):
        return {"patients": await self.db[PATIENTS].count_documents({}),
                "links": await self.db[ACCOUNT_LINKS].count_documents({}),
                "state": await self.db[STATE].count_documents({})}

    def seed_documents(self):
        """合成 legacy 数据：ObjectId 与字符串 _id 双形态 + 医护账号。"""
        self.patient_oid = ObjectId()
        self.patient_str = "drill-string-patient"
        self.account_ids = [str(self.patient_oid), self.patient_str]
        return [
            {"_id": self.patient_oid, "role": "patient", "name": "演练对象一",
             "is_active": True, "email": "hidden@example.com",
             "password_hash": "do-not-project",
             "practitioners": [DOCTOR], "health_managers": [MANAGER],
             "medical_info": {"diagnosis": "stroke"},
             "demographic_info": {"gender": "female"}},
            {"_id": self.patient_str, "role": "patient", "name": "Drill Two",
             "practitioners": [DOCTOR]},
            {"_id": DOCTOR, "role": "doctor", "is_active": True},
            {"_id": OTHER_DOCTOR, "role": "doctor", "is_active": True},
            {"_id": MANAGER, "role": "health_manager", "is_active": True},
        ]

    # ---- 场景 7：迁移中途失败 → 全库零残留 → 重试干净完成 ----

    async def test_failure_injection_leaves_zero_residue_and_retry_completes(self):
        await self.seed_users(self.seed_documents())
        before_users = await self.users_snapshot()
        for phase in ("before_transaction", "after_insert", "before_commit"):
            with self.subTest(phase=phase):
                with self.assertRaises(RuntimeError):
                    await self.migrate(fail_at=phase)
                # 文档级零残留：canonical 三集合均无写入，users 不变。
                # （before_transaction 阶段在 create_patient_indexes 之后抛出，
                # 空索引集合会留下——属已知的良性运维残留，记录为缺口 4。）
                self.assertEqual(await self.domain_counts(),
                                 {"patients": 0, "links": 0, "state": 0})
                self.assertEqual(await self.users_snapshot(), before_users)
        result = await self.migrate()
        self.assertEqual(result["migrated_count"], 2)
        self.assertEqual(result["account_links_created"], 2)
        self.assertFalse(result["users_modified"])
        self.assertEqual((await self.repo.resolve_self(str(self.patient_oid)))["_id"],
                         self.patient_oid)
        self.assertEqual((await self.repo.resolve_self(self.patient_str))["patient_id"],
                         self.patient_str)

    # ---- 场景 1+2+4+5 主链：迁移→canonical→内核分派→双载体栅栏→noop ----

    async def test_full_cutover_chain_migration_kernel_and_dual_fence(self):
        await self.seed_users(self.seed_documents())
        before_users = await self.users_snapshot()

        # -- 场景 1：迁移 --
        manifest = await inspect_migration(self.db)
        self.assertEqual(manifest["mode"], "not_migrated")
        self.assertEqual(manifest["legacy_count"], 2)
        result = await self.migrate()
        self.assertFalse(result["verified_noop"])
        self.assertEqual(result["migrated_count"], 2)
        self.assertEqual(result["account_links_created"], 2)
        self.assertFalse(result["users_modified"])
        self.assertEqual(await self.users_snapshot(), before_users)

        state = await self.db[STATE].find_one({"_id": STATE_ID})
        self.assertEqual(state["mode"], "canonical")
        self.assertEqual(state["migrated_count"], 2)
        self.assertEqual(state["account_links_created"], 2)

        # 链接完整：逐账号 legacy_same_document、verified、审计封套一致
        links = {item["account_id"]: item
                 for item in await self.db[ACCOUNT_LINKS].find({}).to_list(None)}
        self.assertEqual(set(links), set(self.account_ids))
        for account_id in self.account_ids:
            link = links[account_id]
            self.assertEqual(link["_id"], "legacy:" + account_id)
            self.assertEqual(link["source"], "legacy_same_document")
            self.assertEqual(link["patient_id"], account_id)
            self.assertEqual(link["status"], "verified")
            self.assertEqual(link["audit"]["operation"], "legacy_same_document_migration")

        # 校验和一致：实际投影/链接与 manifest/state 记录指纹对齐
        actual = await self.db[PATIENTS].find({}).sort("_id", 1).to_list(None)
        self.assertEqual(fingerprint(actual), manifest["projection_sha256"])
        self.assertEqual(state["legacy_sha256"], manifest["legacy_sha256"])
        self.assertEqual(state["projection_sha256"], manifest["projection_sha256"])
        legacy = await self.db.users.find({"role": "patient"}).sort("_id", 1).to_list(None)
        self.assertEqual(fingerprint(legacy), manifest["legacy_sha256"])

        # -- 场景 2：内核四入口在 canonical 分派（users 不再被读作患者文档）--
        spy = SpyDatabase(self.db)
        patient_id = str(self.patient_oid)

        doc = await load_patient_doc(spy, patient_id)
        self.assertEqual(doc["patient_id"], patient_id)
        self.assertEqual(doc["status"], "active")
        self.assertFalse({"role", "email", "password_hash", "is_active"} & set(doc))
        self.assertEqual(spy.users.find_calls, 0)  # canonical 对象读取不触碰 users

        granted = await ensure_patient_access(spy, patient_id, DOCTOR, "doctor")
        self.assertEqual(granted["patient_id"], patient_id)
        with self.assertRaises(PatientAccessError) as denied:
            await ensure_patient_access(spy, patient_id, OTHER_DOCTOR, "doctor")
        self.assertEqual(denied.exception.status_code, 403)
        self.assertEqual(spy.users.find_calls, 0)  # 归属校验同样不触碰 users

        scope = await assigned_scope_query(spy, DOCTOR, "doctor")
        self.assertEqual(scope, {"status": "active", "practitioners": {"$in": [DOCTOR]}})
        self.assertEqual(spy.users.find_calls, 0)

        # self 解析：verified 账号成功；唯一一次 users 读取是账号复核
        # （is_active/role 有效性），不是把 users 当患者文档解析。
        self.assertEqual(await ensure_self_patient_access(spy, actor(patient_id, "patient")),
                         patient_id)
        self.assertEqual(spy.users.find_calls, 1)

        # -- 场景 3（仓库层读取链）：status=active 过滤 + 停用收窄 --
        assigned = await self.repo.list_assigned(DOCTOR, "doctor")
        self.assertEqual({item["patient_id"] for item in assigned}, set(self.account_ids))
        self.assertTrue(all(item["status"] == "active" for item in assigned))
        self.assertEqual(await self.repo.matching_name_ids("演练", operator_id=DOCTOR,
                                                          operator_role="doctor"),
                         {str(self.patient_oid)})
        self.assertEqual(await self.repo.matching_name_ids("DRILL TWO",
                                                          operator_id=DOCTOR,
                                                          operator_role="doctor"),
                         {self.patient_str})

        # -- 场景 4：栅栏双载体（run_transaction 内 dual_bump）--
        await create_account_fence_indexes(self.db)  # 部署侧维护职责，非启动路径
        patient_id_str = patient_id  # 患者/账号同文档迁移：同一标识两种载体定位

        async def positive(session):
            marker = {"n": "positive"}
            await self.db[MARKER].insert_one(marker, session=session)
            counts = await dual_bump(
                (AccountFenceStore(self.db), patient_id, "access"),
                (PatientFenceStore(self.db), patient_id_str, "access"), session=session)
            return counts

        account_count, patient_count = await run_transaction(
            self.db, positive, error_code="DRILL_TRANSACTION_UNAVAILABLE",
            error_message="drill")
        self.assertEqual((account_count, patient_count), (1, 1))
        fence_doc = await self.db[ACCOUNT_FENCES].find_one(
            {"account_id": patient_id, "fence_name": "access"})
        self.assertEqual(fence_doc["count"], 1)  # 账号 hop 用真实账号 ID
        clinical = await self.db[PATIENTS].find_one({"patient_id": patient_id_str})
        self.assertEqual(clinical["_fence_access"], 1)  # 患者 hop 落在临床文档载体
        self.assertEqual(await self.db[MARKER].count_documents({}), 1)

        # 并发侧模拟账号停用：事务外写者先完成（users 停用 + 账号载体递增），
        # 事务回调持过期快照 expected → CAS miss → FenceMismatch → 整体回滚。
        # （并发写必须在事务外完成：若在事务内插入外部写，会造成快照读与
        # 外部写的写写冲突，触发 TransientTransactionError 无限重试而非
        # 干净的 CAS miss——这也是栅栏 CAS 语义的正确用法。）
        stale_expected = (await self.db[ACCOUNT_FENCES].find_one(
            {"account_id": patient_id, "fence_name": "access"}, {"count": 1}))["count"]
        stale_patient_fence = 1  # positive 递增后、被拒绝事务前的患者载体计数
        await self.db.users.update_one({"_id": self.patient_oid},
                                       {"$set": {"is_active": False}})
        await AccountFenceStore(self.db).bump(patient_id, "access")

        async def concurrent_deactivation(session):
            await self.db[MARKER].insert_one({"n": "revoked"}, session=session)
            return await dual_bump(
                (AccountFenceStore(self.db), patient_id, "access", stale_expected),
                (PatientFenceStore(self.db), patient_id_str, "access",
                 stale_patient_fence), session=session)

        with self.assertRaises(FenceMismatch) as rejected:
            await run_transaction(self.db, concurrent_deactivation,
                                  error_code="DRILL_TRANSACTION_UNAVAILABLE",
                                  error_message="drill")
        self.assertEqual(rejected.exception.details.get("hop"), "account")
        self.assertEqual(rejected.exception.status_code, 409)
        # 回滚断言：事务内 marker 未落盘、患者载体未递增；账号载体只剩并发侧
        # 那次递增；users 停用（并发侧已提交）与 canonical 数据保持原样。
        self.assertEqual(await self.db[MARKER].count_documents({}), 1)
        self.assertEqual((await self.db[ACCOUNT_FENCES].find_one(
            {"account_id": patient_id, "fence_name": "access"}))["count"],
            stale_expected + 1)
        self.assertEqual((await self.db[PATIENTS].find_one(
            {"patient_id": patient_id_str}))["_fence_access"], 1)
        self.assertEqual((await self.db.users.find_one({"_id": self.patient_oid}))
                         ["is_active"], False)

        # 账号恢复后同一链路用新快照干净递增（计数从新载体重新起算语义）。
        await self.db.users.update_one({"_id": self.patient_oid},
                                       {"$set": {"is_active": True}})
        async def resumed(session):
            current = await self.db[ACCOUNT_FENCES].find_one(
                {"account_id": patient_id, "fence_name": "access"}, {"count": 1},
                session=session)
            return await dual_bump(
                (AccountFenceStore(self.db), patient_id, "access", current["count"]),
                (PatientFenceStore(self.db), patient_id_str, "access", 1),
                session=session)

        account_count, patient_count = await run_transaction(
            self.db, resumed, error_code="DRILL_TRANSACTION_UNAVAILABLE",
            error_message="drill")
        self.assertEqual((account_count, patient_count), (stale_expected + 2, 2))

        # 患者 hop 归属快照复核：停用临床患者后，把 status=active 折入
        # extra_query（dual_bump 不支持 extra_query，按模块文档直接调用
        # PatientFenceStore）→ 归属快照不再匹配 → 患者侧拒绝；账号 hop 已
        # 递增的写入随事务整体回滚。
        patient_fence_expected = (await self.db[PATIENTS].find_one(
            {"patient_id": patient_id_str}, {"_fence_access": 1}))["_fence_access"]
        await self.db[PATIENTS].update_one({"patient_id": patient_id_str},
                                           {"$set": {"status": "inactive"}})
        async def patient_side_revoked(session):
            await AccountFenceStore(self.db).bump(patient_id, "access", session=session)
            return await PatientFenceStore(self.db).check(
                patient_id_str, "access", patient_fence_expected, session=session,
                extra_query={"status": "active"})

        with self.assertRaises(FenceMismatch) as patient_denied:
            await run_transaction(self.db, patient_side_revoked,
                                  error_code="DRILL_TRANSACTION_UNAVAILABLE",
                                  error_message="drill")
        self.assertEqual(patient_denied.exception.details.get("carrier"), "patient")
        self.assertEqual(patient_denied.exception.status_code, 409)
        self.assertEqual((await self.db[ACCOUNT_FENCES].find_one(
            {"account_id": patient_id, "fence_name": "access"}))["count"],
            stale_expected + 2)
        self.assertEqual((await self.db[PATIENTS].find_one(
            {"patient_id": patient_id_str}))["_fence_access"], 2)
        self.assertEqual(await self.db[MARKER].count_documents({}), 1)

        # -- 场景 5：干净 noop 重跑（基线未漂移、无晚到者）--
        clean = await self.migrate()
        self.assertTrue(clean["verified_noop"])
        self.assertEqual(clean["latecomer_ids"], [])
        self.assertFalse(clean["users_modified"])
        self.assertEqual(await self.db[PATIENTS].count_documents({}), 2)
        self.assertEqual(await self.db[ACCOUNT_LINKS].count_documents({}), 2)

    # ---- 场景 3（业务域读取链）：范围载体与对象可用性的修复后语义 ----

    async def test_business_scope_and_object_access_in_canonical_mode(self):
        await self.seed_users(self.seed_documents())
        await self.migrate()
        patient_id = str(self.patient_oid)
        string_id = self.patient_str

        # 患者自取范围：canonical 链路经 ensure_self_patient_access 正常返回。
        self.assertEqual(await followup_patient_scope(self.db, actor(patient_id, "patient")),
                         [patient_id])
        self.assertEqual(await device_patient_scope(self.db, actor(patient_id, "patient")),
                         [patient_id])
        # 无关患者账号不得自取他人 ID
        with self.assertRaises(HTTPException) as forbidden:
            await ensure_followup_patient_access(self.db, string_id,
                                                 actor(patient_id, "patient"), write=True)
        self.assertEqual(forbidden.exception.status_code, 403)

        # 缺口 1 修复验证：followup_patient_scope / device_patient_scope
        # 经内核 assigned_scope_ids「构造+执行」一体解析，canonical 查询
        # 执行于 clinical_patients（patient_id 由唯一索引防重），医护范围
        # 返回完整 clinical 范围且不触碰 users；legacy 分支保持
        # assigned_patient_query + assigned_ids 原路径（歧义防护不变）。
        spy = SpyDatabase(self.db)
        self.assertEqual(set(await followup_patient_scope(spy, actor(DOCTOR, "doctor"))),
                         {patient_id, string_id})
        self.assertEqual(set(await device_patient_scope(spy, actor(DOCTOR, "doctor"))),
                         {patient_id, string_id})
        self.assertEqual(spy.users.find_calls, 0)  # 范围执行不再落在 users
        # 对照：仓库层同一 canonical 归属条件与范围函数结果一致
        self.assertEqual({item["patient_id"] for item in await self.repo.list_assigned(
            DOCTOR, "doctor")}, {patient_id, string_id})

        # 缺口 2 修复验证：canonical 停用临床患者（status=inactive）后，
        # load_patient_doc / ensure_patient_access 的 canonical 分支执行
        # status=="active" 校验（文档无 is_active 字段，缺校验会恒放行），
        # 停用患者对象级访问按不存在处理（404，与 legacy 设备消费方对
        # is_active=False 的 404 语义对齐）。
        await self.db[PATIENTS].update_one({"patient_id": string_id},
                                           {"$set": {"status": "inactive"}})
        with self.assertRaises(PatientAccessError) as unavailable:
            await ensure_patient_access(self.db, string_id, DOCTOR, "doctor")
        self.assertEqual(unavailable.exception.status_code, 404)
        self.assertEqual(unavailable.exception.error_code, "PATIENT_NOT_FOUND")
        with self.assertRaises(PatientAccessError) as device_denied:
            await resolve_device_patient(self.db, actor(DOCTOR, "doctor"), string_id)
        self.assertEqual(device_denied.exception.status_code, 404)
        # 范围层随之收窄：canonical 范围内建 status=active，停用者不再出现
        # （legacy 语义中设备的 is_active 过滤等价生效于 canonical status）
        self.assertEqual(set(await followup_patient_scope(self.db, actor(DOCTOR, "doctor"))),
                         {patient_id})
        self.assertEqual(set(await device_patient_scope(self.db, actor(DOCTOR, "doctor"))),
                         {patient_id})

        # 患者自取链路在停用后正确拒绝：resolve_self 要求 active 临床记录。
        with self.assertRaises(PatientAccessError) as inactive_self:
            await ensure_self_patient_access(self.db, actor(string_id, "patient"))
        self.assertEqual(inactive_self.exception.status_code, 403)
        # admin 豁免与 404 语义保持
        self.assertEqual(await followup_patient_scope(self.db, actor("admin-1", "admin")),
                         None)
        with self.assertRaises(PatientAccessError) as missing:
            await load_patient_doc(self.db, "no-such-patient")
        self.assertEqual(missing.exception.status_code, 404)
        self.assertEqual(missing.exception.error_code, "PATIENT_NOT_FOUND")

    # ---- 场景 5：noop 漂移联动（篡改→LEGACY_BASELINE_DRIFTED→恢复）----

    async def test_noop_rerun_drift_fails_closed_and_recovers(self):
        await self.seed_users(self.seed_documents())
        self.assertEqual((await self.migrate())["migrated_count"], 2)
        state = await self.db[STATE].find_one({"_id": STATE_ID})

        clean = await self.migrate()
        self.assertTrue(clean["verified_noop"])
        self.assertEqual(clean["latecomer_ids"], [])

        # 篡改 legacy 患者文档 → rerun fail-closed，摘要含双方指纹
        await self.db.users.update_one({"_id": self.patient_str},
                                       {"$set": {"name": "tampered"}})
        with self.assertRaises(PatientDomainError) as drifted:
            await self.migrate()
        self.assertEqual(drifted.exception.code, "LEGACY_BASELINE_DRIFTED")
        message = str(drifted.exception)
        self.assertIn(state["legacy_sha256"], message)
        current = await self.db.users.find({"role": "patient"}).sort("_id", 1).to_list(None)
        self.assertIn(fingerprint(current), message)
        # canonical 侧未被改动（fail-closed，不静默补写）
        self.assertEqual((await self.db[PATIENTS].find_one(
            {"patient_id": self.patient_str}))["name"], "Drill Two")
        self.assertEqual(await self.db[STATE].find_one({"_id": STATE_ID}), state)

        # 恢复原样 → 干净 noop
        await self.db.users.update_one({"_id": self.patient_str},
                                       {"$set": {"name": "Drill Two"}})
        restored = await self.migrate()
        self.assertTrue(restored["verified_noop"])
        self.assertEqual(restored["latecomer_ids"], [])

        # 晚到 legacy 患者只上报不补迁
        await self.db.users.insert_one({"_id": "latecomer-e2e", "role": "patient",
                                        "name": "late"})
        rerun = await self.migrate()
        self.assertTrue(rerun["verified_noop"])
        self.assertEqual(rerun["latecomer_ids"], ["latecomer-e2e"])
        self.assertEqual(await self.db[PATIENTS].count_documents({}), 2)

    # ---- 场景 6：回拨演练口径（migrating → fail-closed；删状态文档 → legacy 恢复）----

    async def test_rollback_drill_state_semantics(self):
        await self.seed_users(self.seed_documents())
        await self.migrate()
        patient_id = str(self.patient_oid)
        doctor_actor = actor(DOCTOR, "doctor")
        patient_actor = actor(patient_id, "patient")

        async def assert_fail_closed(label):
            # 内核四入口全部 503，绝不静默回退 legacy
            with self.subTest(entry=label):
                for operation in (lambda: load_patient_doc(self.db, patient_id),
                                  lambda: ensure_patient_access(self.db, patient_id,
                                                                DOCTOR, "doctor"),
                                  lambda: ensure_self_patient_access(self.db, patient_actor),
                                  lambda: assigned_scope_query(self.db, DOCTOR, "doctor")):
                    with self.assertRaises(PatientAccessError) as rejected:
                        await operation()
                    self.assertEqual(rejected.exception.status_code, 503)
                    self.assertEqual(rejected.exception.error_code,
                                     "PATIENT_DOMAIN_STATE_UNAVAILABLE")
                # 业务读取链同样拒绝
                for reader in (lambda: followup_patient_scope(self.db, doctor_actor),
                               lambda: device_patient_scope(self.db, doctor_actor),
                               lambda: resolve_device_patient(self.db, doctor_actor,
                                                              patient_id)):
                    with self.assertRaises(PatientAccessError) as rejected:
                        await reader()
                    self.assertEqual(rejected.exception.status_code, 503)
                # canonical 数据本身未被改动（fail-closed 不产生写入）
                self.assertEqual(await self.db[PATIENTS].count_documents({}), 2)
                self.assertEqual(await self.db[ACCOUNT_LINKS].count_documents({}), 2)

        # 口径 A：状态文档被改成 migrating（半迁移态）→ 四入口全 503
        await self.db[STATE].update_one({"_id": STATE_ID}, {"$set": {"mode": "migrating"}})
        await assert_fail_closed("migrating")

        # 恢复 canonical → 全链路恢复
        await self.db[STATE].update_one({"_id": STATE_ID}, {"$set": {"mode": "canonical"}})
        self.assertEqual((await load_patient_doc(self.db, patient_id))["patient_id"],
                         patient_id)

        # 口径 B：状态文档被删除 → 按现行实现回到 legacy 域（users 重新充当
        # 患者文档，患者自取不再需要 verified 链接）。这不是 fail-closed：
        # 意外删除状态文档会静默降级。回拨 SOP（docs/patient-domain-cutover-plan.md
        # 回拨口径章节，缺口 3 收口）明确：回拨必须以显式域开关状态变更执行，
        # 禁止以删文档当开关；本用例固化「删文档=静默回 legacy」的现行语义，
        # 作为该风险的存在性证据。
        await self.db[STATE].delete_one({"_id": STATE_ID})
        self.assertEqual(await patient_domain_mode(self.db), "legacy")
        legacy_doc = await load_patient_doc(self.db, patient_id)
        self.assertEqual(legacy_doc["_id"], self.patient_oid)  # users 文档重新可读
        self.assertEqual(await ensure_self_patient_access(self.db, patient_actor),
                         patient_id)
        # legacy 医护范围重新按 users 关系解析（canonical 链接不再被消费）
        self.assertEqual(await followup_patient_scope(self.db, doctor_actor),
                         [patient_id, self.patient_str])
        # 重建 canonical 状态文档后回到 canonical 分派（演练可逆）
        await self.db[STATE].insert_one({
            "_id": STATE_ID, "mode": "canonical", "schema_version": 1,
            "legacy_sha256": "replay-drill", "migrated_count": 2})
        self.assertEqual((await load_patient_doc(self.db, patient_id))["patient_id"],
                         patient_id)
        self.assertNotIn("role", await load_patient_doc(self.db, patient_id))


if __name__ == "__main__":
    unittest.main()
