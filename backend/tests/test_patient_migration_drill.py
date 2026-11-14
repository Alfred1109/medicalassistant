"""T9 演练：legacy→canonical 临床患者迁移在隔离 Mongo 副本集上的可重复验证用例。

门控：REHAB_TEST_PATIENT_MIGRATION_URI（mongodb://127.0.0.1:<port>/...?replicaSet=<name>，
迁移依赖快照事务，standalone 无法执行 migrate_legacy_patients）。无 URI 时全部跳过。
每个用例使用独立临时库（uuid 后缀）并在 teardown drop，只触碰 URI 指向实例上自己创建的库。
断言全部依据 migration.py / repository.py 的真实语义，不改实现；
发现的数据质量闸门与语义缺口记录在用例与报告中。
"""
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.patient_identity import identity_key, load_identity_groups
from app.patients.migration import (_legacy_links, _projections, fingerprint,
                                    inspect_migration, migrate_legacy_patients,
                                    project_legacy_patient)
from app.patients.repository import (ACCOUNT_LINKS, ClinicalPatientRepository,
                                     PatientDomainError, PATIENTS, STATE, STATE_ID)

URI = os.environ.get("REHAB_TEST_PATIENT_MIGRATION_URI")


@unittest.skipUnless(URI, "set REHAB_TEST_PATIENT_MIGRATION_URI to an isolated local replica set")
class PatientMigrationDrillTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if not URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")):
            self.fail("only an explicit loopback test URI is accepted")
        self.client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.client["rehab_patient_migration_drill_" + uuid4().hex]
        self.repo = ClinicalPatientRepository(self.db)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    async def asyncTearDown(self):
        await self.client.drop_database(self.db.name)
        self.client.close()
        self.temp.cleanup()

    @staticmethod
    def stopped():
        return {"application_stopped": True, "guard_reference": "migration-drill-fixture"}

    async def migrate(self, **overrides):
        options = dict(expected_manifest=await inspect_migration(self.db),
                       backup_directory=self.root / uuid4().hex,
                       reviewer="drill-reviewer",
                       evidence_reference="drill-evidence-reference",
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

    # ---- 场景 1：正常迁移（ObjectId 与字符串 _id 两种形态）----

    async def test_normal_migration_preserves_ids_links_and_checksums(self):
        oid = ObjectId()
        string_id = "legacy-string-account-1"
        await self.seed_users([
            {"_id": oid, "role": "patient", "name": "objectid-form", "is_active": True,
             "email": "hidden@example.com", "password_hash": "do-not-project",
             "practitioners": ["doctor-1"], "medical_info": {"diagnosis": "drill"},
             "demographic_info": {"gender": "female"}},
            {"_id": string_id, "role": "patient", "name": "string-form",
             "health_managers": ["manager-1"]},
            {"_id": "doctor-1", "role": "doctor", "is_active": True},
            {"_id": "manager-1", "role": "health_manager", "is_active": True},
            {"_id": "admin-1", "role": "admin", "is_active": True},
            {"_id": "roleless-1", "is_active": True},
        ])
        before_users = await self.users_snapshot()
        manifest = await inspect_migration(self.db)
        self.assertEqual(manifest["legacy_count"], 2)
        self.assertEqual(manifest["mode"], "not_migrated")

        result = await self.migrate()
        self.assertFalse(result["verified_noop"])
        self.assertEqual(result["migrated_count"], 2)
        self.assertEqual(result["account_links_created"], 2)
        self.assertFalse(result["users_modified"])
        self.assertEqual(await self.users_snapshot(), before_users)

        clinical = await self.db[PATIENTS].find({}).sort("_id", 1).to_list(None)
        self.assertEqual(sorted(str(item["_id"]) for item in clinical),
                         sorted([str(oid), string_id]))
        by_id = {str(item["_id"]): item for item in clinical}
        for identifier in (str(oid), string_id):
            document = by_id[identifier]
            self.assertEqual(document["_id"] if isinstance(document["_id"], str) else str(document["_id"]),
                             identifier)
            self.assertEqual(document["patient_id"], identifier)
            self.assertEqual(document["legacy_user_id"], identifier)
            self.assertEqual(document["schema_version"], 1)
            # 凭据与角色字段不投影
            self.assertFalse({"role", "email", "password_hash"} & set(document))
        self.assertEqual(by_id[str(oid)]["status"], "active")
        self.assertEqual(by_id[string_id]["status"], "active")  # is_active 缺失按 active 迁移
        self.assertEqual(by_id[str(oid)]["practitioners"], ["doctor-1"])
        self.assertEqual(by_id[string_id]["health_managers"], ["manager-1"])

        links = await self.db[ACCOUNT_LINKS].find({}).sort("_id", 1).to_list(None)
        self.assertEqual(len(links), 2)
        by_account = {item["account_id"]: item for item in links}
        self.assertEqual(set(by_account), {str(oid), string_id})
        for link in links:
            self.assertEqual(link["_id"], "legacy:" + link["account_id"])
            self.assertEqual(link["source"], "legacy_same_document")
            self.assertEqual(link["patient_id"], link["account_id"])
            self.assertEqual(link["account_id"], str(link["account_document_id"]))
            self.assertEqual(link["schema_version"], 1)
            audit = link["audit"]
            self.assertEqual(audit["reviewer"], "drill-reviewer")
            self.assertEqual(audit["evidence_reference"], "drill-evidence-reference")
            self.assertEqual(audit["operation"], "legacy_same_document_migration")
            self.assertTrue(audit["at"])
        self.assertEqual(by_account[str(oid)]["status"], "verified")
        self.assertEqual(by_account[string_id]["status"], "verified")

        state = await self.db[STATE].find_one({"_id": STATE_ID})
        self.assertEqual(state["mode"], "canonical")
        self.assertEqual(state["migrated_count"], 2)
        self.assertEqual(state["account_links_created"], 2)

        # 校验和一致性：迁移后的实际投影/链接/legacy 快照与迁移前 manifest 对齐。
        # 注意 manifest["legacy_links_sha256"] 是无 audit 封套的内在关系指纹
        # （inspect 阶段尚无 reviewer/at），且与写入后链接排序不同（users 按 BSON
        # _id 排序，链接按字符串 _id 排序），故去封套后做同序比较。
        actual_patients = await self.db[PATIENTS].find({}).sort("_id", 1).to_list(None)
        self.assertEqual(fingerprint(actual_patients), manifest["projection_sha256"])
        # manifest["legacy_sha256"] 只覆盖 role:"patient" 源文档（医护账号不在基线内）
        legacy_patients = await self.db.users.find({"role": "patient"}).sort("_id", 1).to_list(None)
        self.assertEqual(fingerprint(legacy_patients), manifest["legacy_sha256"])

        def stripped(items):
            return sorted([{key: value for key, value in item.items() if key != "audit"}
                           for item in items], key=lambda item: item["_id"])

        self.assertEqual(fingerprint(stripped(links)),
                         fingerprint(stripped(_legacy_links(await self.db.users.find(
                             {"role": "patient"}).sort("_id", 1).to_list(None)))))
        # audit 封套来自同一迁移批次：reviewer/evidence 一致且时间戳统一
        audits = {item["account_id"]: item["audit"] for item in links}
        self.assertEqual(len({audit["at"] for audit in audits.values()}), 1)
        self.assertTrue(all(audit["reviewer"] == "drill-reviewer"
                            and audit["evidence_reference"] == "drill-evidence-reference"
                            for audit in audits.values()))

        # resolve_self：verified 账号可解析，ObjectId 与字符串入参形态等价
        self.assertEqual((await self.repo.resolve_self(str(oid)))["_id"], oid)
        self.assertEqual((await self.repo.resolve_self(oid))["_id"], oid)
        self.assertEqual((await self.repo.resolve_self(string_id))["patient_id"], string_id)
        # 未建立链接的账号不可解析
        for account in ("doctor-1", "manager-1", "admin-1", "roleless-1"):
            self.assertIsNone(await self.repo.resolve_self(account))

    # ---- 场景 2：非患者/医护不迁入；is_active=False → inactive/disabled ----

    async def test_non_patient_roles_excluded_and_inactive_maps_to_disabled_link(self):
        await self.seed_users([
            {"_id": "active-p", "role": "patient", "name": "active"},
            {"_id": "inactive-p", "role": "patient", "name": "inactive", "is_active": False},
            {"_id": "doctor-1", "role": "doctor", "is_active": True},
            {"_id": "manager-1", "role": "health_manager", "is_active": True},
            {"_id": "admin-1", "role": "admin", "is_active": True},
            {"_id": "roleless-1", "is_active": True},
        ])
        result = await self.migrate()
        self.assertEqual(result["migrated_count"], 2)
        patient_ids = {item["patient_id"] for item in await self.db[PATIENTS].find({}).to_list(None)}
        self.assertEqual(patient_ids, {"active-p", "inactive-p"})
        self.assertEqual((await self.db[PATIENTS].find_one({"_id": "active-p"}))["status"], "active")
        self.assertEqual((await self.db[PATIENTS].find_one({"_id": "inactive-p"}))["status"], "inactive")

        links = {item["account_id"]: item for item in await self.db[ACCOUNT_LINKS].find({}).to_list(None)}
        self.assertEqual(set(links), {"active-p", "inactive-p"})
        self.assertEqual(links["active-p"]["status"], "verified")
        self.assertEqual(links["inactive-p"]["status"], "disabled")
        self.assertEqual(await self.db[ACCOUNT_LINKS].count_documents({"account_id": "active-p"}), 1)

        # clinical 记录存在但 status=inactive：可读但不可自解析
        self.assertEqual((await self.repo.get("inactive-p"))["status"], "inactive")
        self.assertIsNone(await self.repo.resolve_self("inactive-p"))
        self.assertIsNotNone(await self.repo.resolve_self("active-p"))

    # ---- 场景 3：歧义数据 fail-closed，无半迁移状态 ----

    async def test_ambiguous_identity_key_fails_closed_before_any_write(self):
        oid = ObjectId()
        self.assertEqual(identity_key(oid), identity_key(str(oid)))
        await self.seed_users([
            {"_id": oid, "role": "patient", "name": "objectid-form"},
            {"_id": str(oid), "role": "patient", "name": "string-form"},
            {"_id": "doctor-1", "role": "doctor"},
        ])
        groups = await load_identity_groups(self.db, [str(oid)])
        self.assertEqual(len(groups[identity_key(str(oid))]), 2)

        before_users = await self.users_snapshot()
        with self.assertRaises(PatientDomainError) as inspect_failed:
            await inspect_migration(self.db)
        self.assertEqual(inspect_failed.exception.code, "AMBIGUOUS_LEGACY_PATIENT_ID")

        # migrate 内部同样在 inspect 阶段拒绝（早于索引创建与事务写入）
        with self.assertRaises(PatientDomainError) as migrate_failed:
            await self.migrate()
        self.assertEqual(migrate_failed.exception.code, "AMBIGUOUS_LEGACY_PATIENT_ID")

        # fail-closed：无半迁移状态（除 users 外无任何集合/索引/状态文档）
        self.assertEqual(await self.domain_counts(), {"patients": 0, "links": 0, "state": 0})
        self.assertEqual(await self.db.list_collection_names(), ["users"])
        self.assertEqual(await self.users_snapshot(), before_users)

        # 失败可区分、可恢复：移除歧义形态后同一库可干净完成迁移
        await self.db.users.delete_one({"_id": str(oid)})
        result = await self.migrate()
        self.assertEqual(result["migrated_count"], 1)
        self.assertEqual((await self.repo.resolve_self(str(oid)))["_id"], oid)

    # ---- 场景 4：幂等重跑 ----

    async def test_idempotent_rerun_is_noop_without_duplicate_links(self):
        await self.seed_users([{"_id": "patient-1", "role": "patient", "name": "drill"}])
        first = await self.migrate()
        self.assertEqual(first["migrated_count"], 1)
        state_before = await self.db[STATE].find_one({"_id": STATE_ID})
        link_before = await self.db[ACCOUNT_LINKS].find_one({})

        second = await self.migrate()
        self.assertTrue(second["verified_noop"])
        self.assertEqual(second["mode"], "canonical")
        self.assertFalse(second["users_modified"])
        self.assertNotIn("migrated_count", second)
        self.assertEqual(await self.db[PATIENTS].count_documents({}), 1)
        self.assertEqual(await self.db[ACCOUNT_LINKS].count_documents({}), 1)
        self.assertEqual(await self.db[ACCOUNT_LINKS].find_one({}), link_before)
        self.assertEqual(await self.db[STATE].find_one({"_id": STATE_ID}), state_before)

        # cutover 后新增的 legacy 患者不会被 noop 重跑补迁（T17：随结果上报 latecomer_ids）
        await self.db.users.insert_one({"_id": "latecomer-p", "role": "patient", "name": "late"})
        third = await self.migrate()
        self.assertTrue(third["verified_noop"])
        self.assertEqual(third["latecomer_ids"], ["latecomer-p"])
        self.assertEqual(await self.db[PATIENTS].count_documents({}), 1)
        self.assertEqual(await self.db[ACCOUNT_LINKS].count_documents({}), 1)
        self.assertIsNone(await self.db[PATIENTS].find_one({"_id": "latecomer-p"}))

    # ---- 场景 5：注入失败 → 事务回滚，无半迁移，可重试 ----

    async def test_injected_failure_rolls_back_without_half_migration(self):
        await self.seed_users([
            {"_id": "patient-1", "role": "patient", "name": "drill"},
            {"_id": "patient-2", "role": "patient", "name": "drill-2"},
        ])
        before_users = await self.users_snapshot()
        for phase in ("after_insert", "before_commit"):
            with self.subTest(phase=phase):
                with self.assertRaises(RuntimeError):
                    await self.migrate(fail_at=phase)
                # 部分成功可区分：事务内写入整体回滚，状态文档不存在
                self.assertEqual(await self.domain_counts(),
                                 {"patients": 0, "links": 0, "state": 0})
                self.assertEqual(await self.users_snapshot(), before_users)
        # 同一库重试可干净完成
        result = await self.migrate()
        self.assertEqual(result["migrated_count"], 2)
        self.assertEqual(await self.db[ACCOUNT_LINKS].count_documents({}), 2)
        self.assertEqual((await self.repo.resolve_self("patient-1"))["patient_id"], "patient-1")
        self.assertEqual((await self.repo.resolve_self("patient-2"))["patient_id"], "patient-2")

    # ---- 场景 6：缺失字段患者如实投影 ----

    async def test_missing_fields_project_with_explicit_defaults(self):
        await self.seed_users([
            {"_id": "bare-p", "role": "patient"},
            {"_id": "name-only-p", "role": "patient", "name": "只有姓名"},
            {"_id": "null-fields-p", "role": "patient", "name": None,
             "medical_info": None, "demographic_info": None, "emergency_contact": None},
        ])
        result = await self.migrate()
        self.assertEqual(result["migrated_count"], 3)

        bare = await self.db[PATIENTS].find_one({"_id": "bare-p"})
        # 缺失字段不凭空发明：name/created_at 缺省，关系/资料字段补显式空值
        self.assertNotIn("name", bare)
        self.assertNotIn("created_at", bare)
        self.assertNotIn("updated_at", bare)
        for key in ("medical_info", "demographic_info", "emergency_contact"):
            self.assertEqual(bare[key], {})
        for key in ("practitioners", "health_managers", "rehabilitation_plans", "devices"):
            self.assertEqual(bare[key], [])
        self.assertEqual(bare["status"], "active")  # is_active 缺失按 active 迁移
        name_only = await self.db[PATIENTS].find_one({"_id": "name-only-p"})
        self.assertEqual(name_only["name"], "只有姓名")
        null_fields = await self.db[PATIENTS].find_one({"_id": "null-fields-p"})
        self.assertIsNone(null_fields["name"])
        self.assertEqual(null_fields["medical_info"], {})

        self.assertIsNone((await self.repo.get_response("bare-p")).name)
        self.assertEqual((await self.repo.get_response("name-only-p")).name, "只有姓名")
        self.assertIsNone((await self.repo.get_response("null-fields-p")).name)
        # 缺字段患者同样获得审计链接并可解析自身
        self.assertIsNotNone(await self.repo.resolve_self("bare-p"))
        self.assertEqual(await self.db[ACCOUNT_LINKS].count_documents({}), 3)

    # ---- 场景 7：迁移前 resolve_self fail-closed ----

    async def test_resolve_self_before_migration_fails_closed(self):
        await self.seed_users([{"_id": "patient-1", "role": "patient"}])
        with self.assertRaises(PatientDomainError) as rejected:
            await self.repo.resolve_self("patient-1")
        self.assertEqual(rejected.exception.code, "PATIENT_DOMAIN_NOT_MIGRATED")

    # ---- 场景 8：noop 重跑基线漂移 fail-closed（T17 缺口 1）----

    async def test_noop_rerun_fails_closed_on_legacy_baseline_drift(self):
        await self.seed_users([{"_id": "patient-1", "role": "patient", "name": "drill"}])
        self.assertEqual((await self.migrate())["migrated_count"], 1)
        state = await self.db[STATE].find_one({"_id": STATE_ID})

        # 未篡改：verified_noop 且 latecomer_ids 为空
        clean = await self.migrate()
        self.assertTrue(clean["verified_noop"])
        self.assertEqual(clean["latecomer_ids"], [])

        # 迁移后篡改 legacy 患者文档（如 role 侧字段漂移）→ rerun fail-closed
        await self.db.users.update_one({"_id": "patient-1"}, {"$set": {"name": "tampered"}})
        with self.assertRaises(PatientDomainError) as drifted:
            await self.migrate()
        self.assertEqual(drifted.exception.code, "LEGACY_BASELINE_DRIFTED")
        message = str(drifted.exception)
        # 错误信息携带双方指纹摘要：state 记录的基线指纹与当前 legacy 文档指纹
        self.assertIn(state["legacy_sha256"], message)
        self.assertIn(fingerprint(await self.db.users.find(
            {"role": "patient"}).sort("_id", 1).to_list(None)), message)
        # fail-closed：canonical 侧未被改动，legacy 文档保持篡改现状待人工核查
        self.assertEqual(await self.db[PATIENTS].count_documents({}), 1)
        self.assertEqual((await self.db[PATIENTS].find_one({"_id": "patient-1"}))["name"],
                         "drill")
        self.assertEqual((await self.db[STATE].find_one({"_id": STATE_ID})), state)

        # 删除基线患者同样算漂移（集合收缩偏离基线）
        await self.db.users.update_one({"_id": "patient-1"}, {"$set": {"name": "drill"}})
        await self.db.users.delete_one({"_id": "patient-1"})
        with self.assertRaises(PatientDomainError) as deleted:
            await self.migrate()
        self.assertEqual(deleted.exception.code, "LEGACY_BASELINE_DRIFTED")

        # 恢复原样后同一库重跑回到干净 noop
        await self.seed_users([{"_id": "patient-1", "role": "patient", "name": "drill"}])
        restored = await self.migrate()
        self.assertTrue(restored["verified_noop"])
        self.assertEqual(restored["latecomer_ids"], [])

    # ---- 场景 9：晚到患者只上报不补迁（T17 缺口 2，保守策略）----

    async def test_noop_rerun_reports_latecomers_without_auto_migration(self):
        await self.seed_users([{"_id": "patient-1", "role": "patient", "name": "drill"}])
        self.assertEqual((await self.migrate())["migrated_count"], 1)

        # 迁移后插入新 legacy 患者文档：rerun 仍 verified_noop，latecomer_ids 上报
        await self.db.users.insert_one({"_id": "latecomer-p", "role": "patient", "name": "late"})
        rerun = await self.migrate()
        self.assertTrue(rerun["verified_noop"])
        self.assertEqual(rerun["latecomer_ids"], ["latecomer-p"])
        # 不自动补迁：clinical/链接集合均无该患者
        self.assertEqual(await self.db[PATIENTS].count_documents({}), 1)
        self.assertEqual(await self.db[ACCOUNT_LINKS].count_documents({}), 1)
        self.assertIsNone(await self.db[PATIENTS].find_one({"_id": "latecomer-p"}))
        self.assertEqual(await self.db[ACCOUNT_LINKS].count_documents(
            {"account_id": "latecomer-p"}), 0)
        self.assertIsNone(await self.repo.resolve_self("latecomer-p"))

        # 晚到患者不影响基线校验：基线集合指纹仍与 state 一致（未触发漂移错误）
        self.assertEqual((await self.db[STATE].find_one({"_id": STATE_ID}))["mode"],
                         "canonical")

        # 基线漂移与晚到并存：仍 fail-closed，错误信息同时携带双方指纹与晚到 _id
        await self.db.users.update_one({"_id": "patient-1"}, {"$set": {"name": "tampered"}})
        with self.assertRaises(PatientDomainError) as drifted:
            await self.migrate()
        self.assertEqual(drifted.exception.code, "LEGACY_BASELINE_DRIFTED")
        message = str(drifted.exception)
        self.assertIn((await self.db[STATE].find_one({"_id": STATE_ID}))["legacy_sha256"],
                      message)
        self.assertIn("latecomer-p", message)
        # 当前指纹只覆盖基线集合（排除晚到者），仍可被人工核对
        baseline = await self.db.users.find({"role": "patient", "_id": {"$ne": "latecomer-p"}}).sort("_id", 1).to_list(None)
        self.assertIn(fingerprint(baseline), message)

    # ---- 场景 10：晚到者字段非法时 rerun 仍如实上报（T56/B4 回归）----

    def rerun_options(self):
        """rerun 用例不经 self.migrate() 夹具（该夹具先跑 inspect_migration，
        在非法晚到者上会提前抛 INVALID_LEGACY_PATIENT_*，掩盖被测路径）。
        rerun 路径不消费 expected_manifest，传空占位即可。"""
        return dict(expected_manifest={}, backup_directory=self.root / uuid4().hex,
                    reviewer="drill-reviewer", evidence_reference="drill-evidence-reference",
                    maintenance_guard=self.stopped)

    async def test_noop_rerun_reports_latecomer_even_when_latecomer_fields_invalid(self):
        # T56/B4 修复前：rerun 先跑 inspect_migration，其投影硬闸会先在非法
        # 晚到者上抛 INVALID_LEGACY_PATIENT_*，掩盖 canonical 域重跑的真实
        # 状态与晚到者上报。修复后 rerun 判定（状态单例 + 基线指纹）先于
        # 投影校验：rerun 路径不做投影校验，晚到者只收集 _id 上报。
        await self.seed_users([{"_id": "patient-1", "role": "patient", "name": "drill"}])
        self.assertEqual((await self.migrate())["migrated_count"], 1)

        # 晚到者带非法字段（createdAt 字符串形态，投影硬闸必拒的形态）
        await self.db.users.insert_one({"_id": "latecomer-p", "role": "patient",
                                        "createdAt": "2026-01-01T00:00:00Z"})
        rerun = await migrate_legacy_patients(self.db, **self.rerun_options())
        self.assertTrue(rerun["verified_noop"])
        self.assertEqual(rerun["latecomer_ids"], ["latecomer-p"])
        # fail-closed 不变：晚到者不被自动补迁
        self.assertEqual(await self.db[PATIENTS].count_documents({}), 1)
        self.assertEqual(await self.db[ACCOUNT_LINKS].count_documents({}), 1)
        self.assertIsNone(await self.db[PATIENTS].find_one({"_id": "latecomer-p"}))

    async def test_invalid_fields_still_block_first_migration_projection_gate(self):
        # 投影硬闸本身不放松：同一非法字段形态在未迁移路径上仍由迁移工具
        # 拒绝（不经夹具的预 inspect，验证 migrate_legacy_patients 自身），
        # 且错误码不变（该闸门只对 rerun 路径让位，不放松任何校验）
        await self.seed_users([{"_id": "bad-p", "role": "patient",
                                "createdAt": "2026-01-01T00:00:00Z"}])
        with self.assertRaises(PatientDomainError) as rejected:
            await migrate_legacy_patients(self.db, **self.rerun_options())
        self.assertEqual(rejected.exception.code, "INVALID_LEGACY_PATIENT_TIME")
        self.assertEqual(await self.domain_counts(), {"patients": 0, "links": 0, "state": 0})

    async def test_rerun_still_fails_closed_on_non_canonical_state_variants(self):
        # T56/B4 重构后的语义保持：显式 legacy 状态下 rerun 仍以
        # PATIENT_DOMAIN_STATE_CONFLICT 拒绝（与 README 的 rollback 载体约定一致）
        await self.seed_users([{"_id": "patient-1", "role": "patient", "name": "drill"}])
        self.assertEqual((await self.migrate())["migrated_count"], 1)
        await self.db[STATE].update_one({"_id": STATE_ID},
                                        {"$set": {"mode": "legacy"}})
        with self.assertRaises(PatientDomainError) as rejected:
            await migrate_legacy_patients(self.db, **self.rerun_options())
        self.assertEqual(rejected.exception.code, "PATIENT_DOMAIN_STATE_CONFLICT")


@unittest.skipUnless(os.environ.get("REHAB_TEST_PATIENT_MIGRATION_STANDALONE_URI"),
                     "set REHAB_TEST_PATIENT_MIGRATION_STANDALONE_URI to an isolated local standalone")
class PatientMigrationStandaloneRejectionTests(unittest.IsolatedAsyncioTestCase):
    """standalone（无副本集）上迁移必须在写之前拒绝（快照事务前提）。"""

    async def test_migration_requires_replica_set(self):
        from motor.motor_asyncio import AsyncIOMotorClient as _Client
        uri = os.environ["REHAB_TEST_PATIENT_MIGRATION_STANDALONE_URI"]
        if not uri.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")):
            self.fail("only an explicit loopback test URI is accepted")
        client = _Client(uri, serverSelectionTimeoutMS=3000)
        db = client["rehab_patient_migration_standalone_" + uuid4().hex]
        temp = tempfile.TemporaryDirectory()
        try:
            await db.users.insert_one({"_id": "patient-1", "role": "patient"})
            hello = await client.admin.command("hello")
            self.assertIsNone(hello.get("setName"))
            with self.assertRaises(PatientDomainError) as rejected:
                await migrate_legacy_patients(db,
                    expected_manifest=await inspect_migration(db),
                    backup_directory=Path(temp.name) / uuid4().hex,
                    reviewer="drill-reviewer", evidence_reference="drill-evidence-reference",
                    maintenance_guard=lambda: {"application_stopped": True,
                                               "guard_reference": "drill"})
            self.assertEqual(rejected.exception.code, "PATIENT_MIGRATION_REQUIRES_REPLICA_SET")
            self.assertEqual(await db.clinical_patients.count_documents({}), 0)
            self.assertEqual(await db.patient_account_links.count_documents({}), 0)
        finally:
            await client.drop_database(db.name)
            client.close()
            temp.cleanup()


class LegacyProjectionDataGates(unittest.TestCase):
    """合成 legacy 文档的数据质量闸门（纯函数，无 Mongo 依赖，始终运行）。

    这些是真实历史数据最可能触碰的投影硬闸，迁移前需先做数据清洗（第二波段输入）。
    """

    def test_null_is_active_blocks_migration(self):
        with self.assertRaises(PatientDomainError) as raised:
            project_legacy_patient({"_id": ObjectId(), "role": "patient", "is_active": None})
        self.assertEqual(raised.exception.code, "INVALID_LEGACY_PATIENT_STATUS")

    def test_string_timestamp_blocks_migration(self):
        with self.assertRaises(PatientDomainError) as raised:
            project_legacy_patient({"_id": ObjectId(), "role": "patient",
                                    "createdAt": "2026-01-01T00:00:00Z"})
        self.assertEqual(raised.exception.code, "INVALID_LEGACY_PATIENT_TIME")

    def test_null_relation_list_blocks_migration(self):
        with self.assertRaises(PatientDomainError) as raised:
            project_legacy_patient({"_id": ObjectId(), "role": "patient", "practitioners": None})
        self.assertEqual(raised.exception.code, "INVALID_LEGACY_PATIENT_RELATION")

    def test_non_string_name_rejected_at_projection_validation(self):
        with self.assertRaises(PatientDomainError) as raised:
            _projections([{"_id": ObjectId(), "role": "patient", "name": 123}])
        self.assertEqual(raised.exception.code, "INVALID_LEGACY_PATIENT_PROJECTION")

    def test_account_only_fields_are_dropped_not_projected(self):
        legacy = {"_id": ObjectId(), "role": "patient", "email": "x@example.com",
                  "password_hash": "h", "refresh_tokens": ["t"], "source": {"unknown": 1}}
        projected = project_legacy_patient(legacy)
        self.assertFalse({"role", "email", "password_hash", "refresh_tokens", "source"} & set(projected))
