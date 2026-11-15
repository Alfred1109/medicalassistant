"""T64：显式账号绑定工作流（explicit_binding origin）副本集门控测试。

覆盖 patients/repository 新增的 bind_account / disable_account_link 与
resolve_self 的显式 origin 分支：

- 无账号临床患者（create_from_source）→ 建账号 → 显式绑定 → resolve_self
  打通 → 患者内核自取通路可用；停用链接/停用账号后通路如实关闭；
- 互斥语义：任意 origin 已有链接（含 legacy 已停用）一律拒绝，不隐式替换；
- 人工核实凭证（reviewer/evidence）与审计字段必填，篡改/缺失 fail-closed；
- 显式链接不要求 legacy_user_id / ID 对齐（same-document 专属）；
- 显式绑定不破坏迁移 noop 重跑基线（legacy 基线覆盖推断只看
  legacy_same_document 链接）。

门控：REHAB_TEST_CLINICAL_PATIENT_URI（孤立本地副本集；无 URI 全跳过）。
每个用例独立临时库并在 teardown drop；合成数据，不触碰真实业务库。
既有 legacy_same_document 用例（test_clinical_patients.py）不放松、全量保留。
"""
import asyncio
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, skipUnless
from uuid import uuid4

NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.patient_access import PatientAccessError, ensure_self_patient_access
from app.patients.migration import inspect_migration, migrate_legacy_patients
from app.patients.repository import (ACCOUNT_LINKS, PATIENTS,
                                     ClinicalPatientRepository, PatientDomainError)

URI = os.environ.get("REHAB_TEST_CLINICAL_PATIENT_URI")

SOURCE = {"origin": "https://source.example", "system": "form-platform-11344",
          "environment": "production", "patient_id": 64}


def actor(account_id, role):
    """最小认证主体替身：内核只消费 id/role 两个属性。"""
    return type("BindingActor", (), {"id": account_id, "role": role})()


@skipUnless(URI, "set REHAB_TEST_CLINICAL_PATIENT_URI to an isolated local replica set")
class PatientAccountBindingTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if not URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")):
            self.fail("only an explicit local test URI is accepted")
        self.client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.client["rehab_patient_binding_test_" + uuid4().hex]
        self.legacy_patient_id = ObjectId()
        self.doctor_id = ObjectId()
        await self.db.users.insert_many([
            {"_id": self.legacy_patient_id, "role": "patient", "name": "存量患者",
             "email": "legacy-binding@example.com", "password_hash": "do-not-project",
             "is_active": True, "practitioners": [], "health_managers": []},
            {"_id": self.doctor_id, "role": "doctor", "is_active": True}])
        self.repo = ClinicalPatientRepository(self.db)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        await self.migrate()

    async def asyncTearDown(self):
        await self.client.drop_database(self.db.name)
        self.client.close()
        self.temp.cleanup()

    @staticmethod
    def stopped():
        return {"application_stopped": True, "guard_reference": "binding-fixture"}

    async def migrate(self, **overrides):
        options = dict(expected_manifest=await inspect_migration(self.db),
                       backup_directory=self.root / uuid4().hex, reviewer="binding-reviewer",
                       evidence_reference="binding-evidence", maintenance_guard=self.stopped)
        options.update(overrides)
        return await migrate_legacy_patients(self.db, **options)

    async def create_accountless_patient(self):
        document = await self.repo.create_from_source(
            SOURCE, reviewer="binding-reviewer", evidence_reference="binding-evidence-1",
            name="显式绑定患者")
        self.assertIsNone(document.get("legacy_user_id"))
        return document

    async def create_patient_account(self, patient_name="绑定账号"):
        account_id = str(ObjectId())
        await self.db.users.insert_one({
            "_id": ObjectId(account_id), "role": "patient", "name": patient_name,
            "email": f"{account_id}@binding.invalid", "password_hash": "!",
            "is_active": True, "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)})
        return account_id

    async def bind(self, patient_id, account_id, **overrides):
        options = dict(account_id=account_id, reviewer="管理员甲",
                       evidence_reference="核实凭证-64")
        options.update(overrides)
        return await self.repo.bind_account(patient_id, **options)

    # ── 主链：建档 → 建账号 → 显式绑定 → resolve_self / 内核自取 ──────────

    async def test_explicit_binding_opens_self_access_and_disable_closes_it(self):
        patient = await self.create_accountless_patient()
        patient_id = patient["patient_id"]
        account_id = await self.create_patient_account()
        # 绑定前：resolve_self / 内核自取一律 fail-closed
        self.assertIsNone(await self.repo.resolve_self(account_id))
        with self.assertRaises(PatientAccessError):
            await ensure_self_patient_access(self.db, actor(account_id, "patient"))

        link = await self.bind(patient_id, account_id)
        self.assertEqual(link["source"], "explicit_binding")
        self.assertEqual(link["status"], "verified")
        self.assertEqual(link["patient_id"], patient_id)
        self.assertEqual(link["account_id"], account_id)
        self.assertEqual(link["account_document_id"], ObjectId(account_id))
        self.assertEqual(link["schema_version"], 1)
        self.assertEqual(link["audit"][0]["operation"], "explicit_binding")
        self.assertEqual(link["audit"][0]["reviewer"], "管理员甲")
        self.assertEqual(link["audit"][0]["evidence_reference"], "核实凭证-64")
        self.assertIsInstance(link["audit"][0]["at"], datetime)

        # 显式 origin 不要求 legacy_user_id / ID 对齐（same-document 专属）
        self.assertIsNone((await self.repo.get(patient_id)).get("legacy_user_id"))
        self.assertNotEqual(patient_id, account_id)
        resolved = await self.repo.resolve_self(account_id)
        self.assertEqual(resolved["patient_id"], patient_id)
        self.assertEqual(await ensure_self_patient_access(
            self.db, actor(account_id, "patient")), patient_id)

        # 停用账号（不触碰链接）：反向核验让链接失效，不自动复活
        await self.db.users.update_one({"_id": ObjectId(account_id)},
                                       {"$set": {"is_active": False}})
        self.assertIsNone(await self.repo.resolve_self(account_id))
        await self.db.users.update_one({"_id": ObjectId(account_id)},
                                       {"$set": {"is_active": True}})
        self.assertEqual((await self.repo.resolve_self(account_id))["patient_id"], patient_id)

        # 停用链接：verified→disabled 状态机，审计追加，文档不删除
        disabled = await self.repo.disable_account_link(
            patient_id, reviewer="管理员乙", evidence_reference="解绑凭证-1")
        self.assertEqual(disabled["status"], "disabled")
        self.assertIsInstance(disabled["disabled_at"], datetime)
        operations = [entry["operation"] for entry in disabled["audit"]]
        self.assertEqual(operations, ["explicit_binding", "explicit_binding_disable"])
        self.assertEqual(disabled["audit"][-1]["reviewer"], "管理员乙")
        self.assertIsNone(await self.repo.resolve_self(account_id))
        with self.assertRaises(PatientAccessError):
            await ensure_self_patient_access(self.db, actor(account_id, "patient"))

    async def test_resolve_self_rejects_tampered_explicit_links(self):
        patient = await self.create_accountless_patient()
        account_id = await self.create_patient_account()
        await self.bind(patient["patient_id"], account_id)
        self.assertIsNotNone(await self.repo.resolve_self(account_id))
        for update in ({"audit.0.evidence_reference": ""},
                       {"audit.0.reviewer": ""},
                       {"audit.0.operation": "legacy_same_document_migration"},
                       {"audit": []},
                       {"audit": {"reviewer": "管理员甲", "evidence_reference": "核实凭证-64",
                                  "operation": "explicit_binding", "at": NOW}},
                       {"schema_version": 2},
                       {"status": "disabled"},
                       {"account_document_id": str(ObjectId())}):
            with self.subTest(update=update):
                await self.db[ACCOUNT_LINKS].update_one(
                    {"patient_id": patient["patient_id"]}, {"$set": update})
                self.assertIsNone(await self.repo.resolve_self(account_id))
                # 还原：唯一槽位被占用，直接改回字段后恢复可解析
                await self.db[ACCOUNT_LINKS].update_one(
                    {"patient_id": patient["patient_id"]},
                    {"$set": {"audit": [{"reviewer": "管理员甲",
                                         "evidence_reference": "核实凭证-64",
                                         "operation": "explicit_binding", "at": NOW}],
                              "schema_version": 1,
                              "status": "verified",
                              "account_document_id": ObjectId(account_id)}})
                self.assertIsNotNone(await self.repo.resolve_self(account_id))

    async def test_explicit_link_keeps_migration_noop_verified(self):
        patient = await self.create_accountless_patient()
        account_id = await self.create_patient_account()
        await self.bind(patient["patient_id"], account_id)
        result = await self.migrate()
        self.assertTrue(result["verified_noop"])
        # 基线覆盖只认 legacy_same_document 链接；绑定工作流新建的
        # role:"patient" 账号如实作为晚到者上报（绝不自动迁移）。
        self.assertEqual(result["latecomer_ids"], [account_id])
        self.assertEqual(await self.db[ACCOUNT_LINKS].count_documents(
            {"source": "explicit_binding"}), 1)
        self.assertEqual(await self.db[ACCOUNT_LINKS].count_documents(
            {"source": "legacy_same_document"}), 1)

    # ── 互斥：任意 origin 已有链接一律拒绝，不隐式替换 ────────────────────

    async def test_binding_conflicts_reject_any_existing_link(self):
        patient = await self.create_accountless_patient()
        patient_id = patient["patient_id"]
        account_id = await self.create_patient_account()
        other_account_id = await self.create_patient_account("另一个账号")
        await self.bind(patient_id, account_id)
        # 同患者换账号
        with self.assertRaises(PatientDomainError) as rejected:
            await self.bind(patient_id, other_account_id)
        self.assertEqual(rejected.exception.code, "PATIENT_ACCOUNT_LINK_CONFLICT")
        # 同账号绑到别的患者（再建一个无账号患者）
        second = await self.repo.create_from_source(
            {**SOURCE, "patient_id": 65}, reviewer="r", evidence_reference="e")
        with self.assertRaises(PatientDomainError) as rejected:
            await self.bind(second["patient_id"], account_id)
        self.assertEqual(rejected.exception.code, "PATIENT_ACCOUNT_LINK_CONFLICT")
        # 重复同一绑定
        with self.assertRaises(PatientDomainError) as rejected:
            await self.bind(patient_id, account_id)
        self.assertEqual(rejected.exception.code, "PATIENT_ACCOUNT_LINK_CONFLICT")
        self.assertEqual(await self.db[ACCOUNT_LINKS].count_documents({}), 2)

    async def test_legacy_linked_patient_and_account_are_rejected(self):
        # 存量迁移患者：已有 legacy_same_document 链接（verified）
        account_id = await self.create_patient_account()
        with self.assertRaises(PatientDomainError) as rejected:
            await self.bind(str(self.legacy_patient_id), account_id)
        self.assertEqual(rejected.exception.code, "PATIENT_ACCOUNT_LINK_CONFLICT")
        # legacy 账号（已被 legacy 链接占用）也不能再绑到别的新患者
        patient = await self.create_accountless_patient()
        with self.assertRaises(PatientDomainError) as rejected:
            await self.bind(patient["patient_id"], str(self.legacy_patient_id))
        self.assertEqual(rejected.exception.code, "PATIENT_ACCOUNT_LINK_CONFLICT")
        # legacy 链接停用后同样占用唯一槽位：终态文档，不隐式替换/复活
        await self.db[ACCOUNT_LINKS].update_one(
            {"account_id": str(self.legacy_patient_id)}, {"$set": {"status": "disabled"}})
        account_id = await self.create_patient_account()
        with self.assertRaises(PatientDomainError) as rejected:
            await self.bind(str(self.legacy_patient_id), account_id)
        self.assertEqual(rejected.exception.code, "PATIENT_ACCOUNT_LINK_CONFLICT")
        with self.assertRaises(PatientDomainError) as rejected:
            await self.bind(patient["patient_id"], str(self.legacy_patient_id))
        self.assertEqual(rejected.exception.code, "PATIENT_ACCOUNT_LINK_CONFLICT")

    async def test_disabled_explicit_link_is_terminal(self):
        patient = await self.create_accountless_patient()
        patient_id = patient["patient_id"]
        account_id = await self.create_patient_account()
        await self.bind(patient_id, account_id)
        await self.repo.disable_account_link(patient_id, reviewer="管理员乙",
                                             evidence_reference="解绑凭证-1")
        # 已停用的显式链接占据唯一槽位：同患者/同账号重绑一律拒绝（不自动复活）
        other_account_id = await self.create_patient_account()
        with self.assertRaises(PatientDomainError) as rejected:
            await self.bind(patient_id, other_account_id)
        self.assertEqual(rejected.exception.code, "PATIENT_ACCOUNT_LINK_CONFLICT")
        second = await self.repo.create_from_source(
            {**SOURCE, "patient_id": 66}, reviewer="r", evidence_reference="e")
        with self.assertRaises(PatientDomainError) as rejected:
            await self.bind(second["patient_id"], account_id)
        self.assertEqual(rejected.exception.code, "PATIENT_ACCOUNT_LINK_CONFLICT")
        self.assertEqual(await self.db[ACCOUNT_LINKS].count_documents({}), 2)

    async def test_concurrent_bindings_commit_exactly_one(self):
        patient = await self.create_accountless_patient()
        patient_id = patient["patient_id"]
        account_ids = [await self.create_patient_account() for _ in range(4)]
        results = await asyncio.gather(*[self.bind(patient_id, account_id)
                                         for account_id in account_ids],
                                      return_exceptions=True)
        self.assertEqual(sum(isinstance(item, dict) for item in results), 1)
        self.assertEqual(await self.db[ACCOUNT_LINKS].count_documents(
            {"source": "explicit_binding"}), 1)
        self.assertEqual(await self.db[ACCOUNT_LINKS].count_documents(
            {"patient_id": patient_id}), 1)

    # ── 校验：凭证/账号/患者 fail-closed ─────────────────────────────────

    async def test_binding_requires_review_and_evidence(self):
        patient = await self.create_accountless_patient()
        account_id = await self.create_patient_account()
        for reviewer, evidence in (("", "凭证"), ("管理员", ""), ("  ", "凭证"),
                                   (None, "凭证"), ("管理员", None)):
            with self.subTest(reviewer=reviewer), self.assertRaises(PatientDomainError) as rejected:
                await self.bind(patient["patient_id"], account_id,
                                reviewer=reviewer, evidence_reference=evidence)
            self.assertEqual(rejected.exception.code, "PATIENT_REVIEW_REQUIRED")
        with self.assertRaises(PatientDomainError) as rejected:
            await self.bind(patient["patient_id"], account_id,
                            reviewer="甲" * 201, evidence_reference="凭证")
        self.assertEqual(rejected.exception.code, "INVALID_PATIENT_REVIEW_REFERENCE")

    async def test_binding_validates_account(self):
        patient = await self.create_accountless_patient()
        patient_id = patient["patient_id"]
        for account_id, expected in (("not-an-objectid", "INVALID_PATIENT_ACCOUNT"),
                                     (str(ObjectId()), "INVALID_PATIENT_ACCOUNT")):
            with self.subTest(account_id=account_id), self.assertRaises(PatientDomainError) as rejected:
                await self.bind(patient_id, account_id)
            self.assertEqual(rejected.exception.code, expected)
        # 非患者角色 / 停用账号
        doctor_id = str(ObjectId())
        await self.db.users.insert_one({"_id": ObjectId(doctor_id), "role": "doctor",
                                        "is_active": True})
        with self.assertRaises(PatientDomainError) as rejected:
            await self.bind(patient_id, doctor_id)
        self.assertEqual(rejected.exception.code, "INVALID_PATIENT_ACCOUNT")
        inactive_id = await self.create_patient_account()
        await self.db.users.update_one({"_id": ObjectId(inactive_id)},
                                       {"$set": {"is_active": False}})
        with self.assertRaises(PatientDomainError) as rejected:
            await self.bind(patient_id, inactive_id)
        self.assertEqual(rejected.exception.code, "INVALID_PATIENT_ACCOUNT")
        self.assertEqual(await self.db[ACCOUNT_LINKS].count_documents({}), 1)

    async def test_binding_validates_clinical_patient(self):
        account_id = await self.create_patient_account()
        with self.assertRaises(PatientDomainError) as rejected:
            await self.bind("missing-patient", account_id)
        self.assertEqual(rejected.exception.code, "PATIENT_NOT_FOUND")
        patient = await self.create_accountless_patient()
        await self.db[PATIENTS].update_one({"patient_id": patient["patient_id"]},
                                           {"$set": {"status": "inactive"}})
        with self.assertRaises(PatientDomainError) as rejected:
            await self.bind(patient["patient_id"], account_id)
        self.assertEqual(rejected.exception.code, "PATIENT_NOT_FOUND")
        self.assertEqual(await self.db[ACCOUNT_LINKS].count_documents({}), 1)

    # ── 停用路径校验 ─────────────────────────────────────────────────────

    async def test_disable_validations(self):
        # 未绑定的患者：404 语义
        with self.assertRaises(PatientDomainError) as rejected:
            await self.repo.disable_account_link("missing-patient", reviewer="管理员",
                                                 evidence_reference="凭证")
        self.assertEqual(rejected.exception.code, "PATIENT_ACCOUNT_LINK_NOT_FOUND")
        # legacy 链接不在本工作流内
        with self.assertRaises(PatientDomainError) as rejected:
            await self.repo.disable_account_link(str(self.legacy_patient_id),
                                                 reviewer="管理员", evidence_reference="凭证")
        self.assertEqual(rejected.exception.code, "PATIENT_ACCOUNT_LINK_CONFLICT")
        # 缺凭证
        patient = await self.create_accountless_patient()
        account_id = await self.create_patient_account()
        await self.bind(patient["patient_id"], account_id)
        with self.assertRaises(PatientDomainError) as rejected:
            await self.repo.disable_account_link(patient["patient_id"],
                                                 reviewer="", evidence_reference="凭证")
        self.assertEqual(rejected.exception.code, "PATIENT_REVIEW_REQUIRED")
        # 重复停用
        await self.repo.disable_account_link(patient["patient_id"], reviewer="管理员",
                                             evidence_reference="解绑-1")
        with self.assertRaises(PatientDomainError) as rejected:
            await self.repo.disable_account_link(patient["patient_id"], reviewer="管理员",
                                                 evidence_reference="解绑-2")
        self.assertEqual(rejected.exception.code, "PATIENT_ACCOUNT_LINK_CONFLICT")


if __name__ == "__main__":
    import unittest
    unittest.main()
