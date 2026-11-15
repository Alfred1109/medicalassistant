"""波次 2 验收：canonical 模式下康复发布与患者反馈全链路（cutover plan §波次 2）。

门控：REHAB_TEST_CANONICAL_PUBLICATION_URI
（mongodb://127.0.0.1:<port>/...?replicaSet=<name>&directConnection=true）。
迁移/发布/反馈依赖快照事务，standalone 无法执行；无 URI 全部跳过。
每个用例使用独立临时库（uuid 后缀）并在 teardown drop，只触碰 URI 指向实例上
自己创建的库。合成数据，不触碰任何真实业务库。

造数手法复用 test_canonical_accountless_loop.py：legacy 最小数据 →
migrate_legacy_patients → canonical → create_from_source 无账号患者 →
verified 链接补关联（legacy_same_document 载体替位；面向全新源患者的显式
绑定工作流未实现，登记为波次项）。

覆盖：
1. 迁移患者（有账号同文档 verified 链接）：草稿→发布→本人读取/列表→
   反馈提交/医护历史→撤回归档全链路走通；recorded_by 经链接解析落账号 ID；
   栅栏双载体（account_fences 账号计数 + clinical_patients._fence_access
   患者计数）落位，且发布事务失败时与版本指针一同回滚。
2. 无账号患者：医护发布走通；无链接账号（迁移患者账号）代反馈被拒
   403 REHAB_PATIENT_FORBIDDEN；医护历史查询因身份锚点不可解析 fail-closed
   503 REHAB_PATIENT_ACCOUNT_UNAVAILABLE；补关联后反馈走通。
3. 并发撤权：发布授权读取与栅栏递增之间归属被并发改写 → 事务写冲突中止
   重试后拒绝（不假报成功）；无链接账号本人列表被拒。
"""
import asyncio
import os
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.exceptions import AppBaseException
from app.patients.migration import inspect_migration, migrate_legacy_patients
from app.patients.repository import ACCOUNT_LINKS, PATIENTS, ClinicalPatientRepository
from app.schemas.rehab_feedback import PatientFeedbackCreate, PatientExecutionStatus
from app.schemas.rehab_publication import (PublishDraft, SavePublicationDraft,
                                           WithdrawPublication)
from app.schemas.rehabilitation import RehabPlanCreate
from app.services.rehab_feedback_service import RehabFeedbackService
from app.services.rehab_publication_service import RehabPublicationService
from app.services.rehabilitation_service import RehabilitationService

URI = os.environ.get("REHAB_TEST_CANONICAL_PUBLICATION_URI")

# 医护账号用 ObjectId 形态；迁移患者账号 ID 与临床实体同 ID（legacy_same_document）。
DOCTOR = str(ObjectId())
MANAGER = str(ObjectId())
SOURCE = {"origin": "https://source.example", "system": "form-platform-11344",
          "environment": "production", "patient_id": 11}


def actor(account_id, role):
    """最小认证主体替身：内核只消费 id/role 两个属性。"""
    return type("PublicationLoopActor", (), {"id": account_id, "role": role})()


@unittest.skipUnless(URI, "set REHAB_TEST_CANONICAL_PUBLICATION_URI to an isolated local replica set")
class CanonicalPublicationLoopTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if not URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")):
            self.fail("only an explicit loopback test URI is accepted")
        self.client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.client["rehab_canonical_publication_" + uuid4().hex]
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.svc = RehabPublicationService(self.db)
        self.feedback = RehabFeedbackService(self.db)
        self.legacy_patient_id = ObjectId()

    async def asyncTearDown(self):
        await self.client.drop_database(self.db.name)
        self.client.close()
        self.temp.cleanup()

    @staticmethod
    def stopped():
        return {"application_stopped": True, "guard_reference": "canonical-publication-fixture"}

    async def migrate(self, **overrides):
        options = dict(expected_manifest=await inspect_migration(self.db),
                       backup_directory=self.root / uuid4().hex,
                       reviewer="publication-loop-reviewer",
                       evidence_reference="publication-loop-evidence",
                       maintenance_guard=self.stopped)
        options.update(overrides)
        return await migrate_legacy_patients(self.db, **options)

    def seed_documents(self):
        """合成 legacy 数据：1 个存量患者（有账号同文档）+ 医护账号。

        legacy_patient_id 在 asyncSetUp 生成，供用例开头构造 actor 使用。
        """
        return [
            {"_id": self.legacy_patient_id, "role": "patient", "name": "存量患者",
             "is_active": True, "email": "publication-loop@example.com",
             "password_hash": "do-not-project",
             "practitioners": [DOCTOR], "health_managers": [MANAGER],
             "medical_info": {"diagnosis": "stroke"}},
            {"_id": ObjectId(DOCTOR), "role": "doctor", "name": "演练医生", "is_active": True},
            {"_id": ObjectId(MANAGER), "role": "health_manager", "name": "演练管理师", "is_active": True},
        ]

    async def seed_and_migrate(self):
        from app.core.fences import create_account_fence_indexes
        await self.db.users.insert_many([deepcopy(item) for item in self.seed_documents()])
        result = await self.migrate()
        self.assertEqual(result["migrated_count"], 1)
        self.assertEqual(result["account_links_created"], 1)
        # account_fences 唯一索引由部署侧脚本执行（fences.py 约定：不进应用
        # 启动路径）；测试环境在栅栏启用前显式执行同一动作。
        await create_account_fence_indexes(self.db)

    async def create_accountless_patient(self):
        """create_from_source 创建无账号临床患者 + 医护归属替位写入（与演练同手法）。"""
        document = await ClinicalPatientRepository(self.db).create_from_source(
            SOURCE, reviewer="publication-loop-reviewer", evidence_reference="publication-loop-evidence-1",
            name="演练无账号患者")
        await self.db[PATIENTS].update_one({"patient_id": document["patient_id"]},
                                           {"$set": {"practitioners": [DOCTOR],
                                                     "health_managers": [MANAGER]}})
        return document

    def draft_request(self, **updates):
        data = {"request_id": uuid4().hex, "content": {"name": "Canonical plan", "description": "Reviewed content",
            "goal": "A recorded goal", "start_date": "2026-11-15T08:00:00+08:00"},
            "items": [{"intervention_type": "exercise", "name": "Loop exercise", "schedule": {"sets": 2}},
                      {"intervention_type": "medication", "name": "Loop medication",
                       "medication_fields": {"frequency": "explicit schedule"}}]}
        data.update(updates)
        return SavePublicationDraft.model_validate(data)

    def publish_request(self, draft, previous=None, **updates):
        data = {"request_id": uuid4().hex, "draft_id": draft["draft"]["id"],
            "expected_draft_revision": draft["draft"]["revision"], "expected_publication_id": previous,
            "confirmed": True, "confirmation_note": "Clinician checked all entered content"}
        data.update(updates)
        return PublishDraft.model_validate(data)

    async def create_plan(self, patient_id, name="Canonical plan"):
        plan = await RehabilitationService(self.db).create_rehab_plan(RehabPlanCreate(
            name=name, description="canonical publication loop", patient_id=patient_id,
            start_date=datetime.now(timezone.utc), goal="恢复上肢功能"))
        return plan

    def feedback_payload(self, version_id, item_id, **changes):
        data = {"event_id": str(uuid4()), "version_id": version_id,
                "prescription_item_id": item_id, "execution_status": "partial",
                "feelings": "患者记录的主观执行观察",
                "performed_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()}
        data.update(changes)
        return PatientFeedbackCreate.model_validate(data)

    async def test_migrated_patient_publication_and_feedback_full_loop(self):
        doctor_actor = actor(DOCTOR, "doctor")
        patient_actor = actor(str(self.legacy_patient_id), "patient")
        await self.seed_and_migrate()
        plan = await self.create_plan(str(self.legacy_patient_id))
        draft = await self.svc.save_draft(plan["_id"], doctor_actor, self.draft_request())
        published = await self.svc.publish(plan["_id"], doctor_actor, self.publish_request(draft))
        self.assertEqual(published["version_id"], draft["draft"]["id"])

        # 栅栏双载体落位：医护发布的账号侧 account_fences 计数（从 1 起算）
        # 与患者侧 clinical_patients._fence_access 计数。患者账号侧计数器在
        # 患者本人的栅栏化操作（反馈提交）后才出现。
        doctor_fence = await self.db.account_fences.find_one({"account_id": DOCTOR, "fence_name": "access"})
        self.assertGreaterEqual(doctor_fence["count"], 1)
        clinical = await self.db[PATIENTS].find_one({"patient_id": str(self.legacy_patient_id)})
        self.assertGreaterEqual(clinical.get("_fence_access", 0), 1)
        # users 载体在 canonical 下停止递增（迁移窗口约束）
        legacy_doc = await self.db.users.find_one({"_id": self.legacy_patient_id})
        self.assertNotIn("_access_fence", legacy_doc)

        # 本人读取与列表经 resolve_self（verified 链接）
        self.assertEqual((await self.svc.patient_detail(plan["_id"], patient_actor))["version_id"],
                         published["version_id"])
        listing = await self.svc.patient_list(patient_actor)
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["items"][0]["version_id"], published["version_id"])

        # 反馈：recorded_by 经链接解析落账号 ID（legacy_same_document 载体下
        # 与临床实体同 ID，跨波段历史连续）
        submitted = await self.feedback.submit(plan["_id"],
            self.feedback_payload(published["version_id"], published["items"][0]["item_id"]),
            patient_actor)
        self.assertTrue(submitted.created)
        stored = await self.db.rehab_execution_events.find_one({})
        self.assertEqual(stored["recorded_by"], str(self.legacy_patient_id))
        self.assertEqual(stored["patient_id"], str(self.legacy_patient_id))
        self.assertEqual((await self.feedback.list(plan["_id"], doctor_actor)).total, 1)
        # 患者本人栅栏化操作后：患者账号侧计数器亦落位
        patient_fence = await self.db.account_fences.find_one(
            {"account_id": str(self.legacy_patient_id), "fence_name": "access"})
        self.assertGreaterEqual(patient_fence["count"], 1)

        # 发布事务失败：版本指针与双载体栅栏计数一同回滚。
        # 快照取在失败发布之前（draft2 的保存本身也是一次栅栏化授权，先落位）。
        draft2 = await self.svc.save_draft(plan["_id"], doctor_actor, self.draft_request())
        before_account = await self.db.account_fences.find({"account_id": {"$in": [DOCTOR, str(self.legacy_patient_id)]}}).to_list(2)
        before_patient_fence = (await self.db[PATIENTS].find_one(
            {"patient_id": str(self.legacy_patient_id)})).get("_fence_access")
        with patch.object(self.svc, "_record_operation", side_effect=RuntimeError("injected failure")):
            with self.assertRaises(RuntimeError):
                await self.svc.publish(plan["_id"], doctor_actor, self.publish_request(draft2, published["version_id"]))
        plan_doc = await self.db.rehab_plans.find_one({"_id": ObjectId(plan["_id"])})
        self.assertEqual(plan_doc["published_version_id"], published["version_id"])
        self.assertEqual((await self.db.rehab_plan_versions.find_one(
            {"_id": ObjectId(draft2["draft"]["id"])}))["status"], "draft")
        after_account = await self.db.account_fences.find({"account_id": {"$in": [DOCTOR, str(self.legacy_patient_id)]}}).to_list(2)
        self.assertEqual({(row["account_id"], row["count"]) for row in before_account},
                         {(row["account_id"], row["count"]) for row in after_account})
        clinical = await self.db[PATIENTS].find_one({"patient_id": str(self.legacy_patient_id)})
        self.assertEqual(clinical.get("_fence_access", 0), before_patient_fence)

        # 撤回归档：本人列表归零，反馈历史保留
        await self.svc.withdraw(plan["_id"], doctor_actor, WithdrawPublication(
            request_id=uuid4().hex, expected_publication_id=published["version_id"],
            action="archive", reason="Clinician archived this plan"))
        self.assertEqual((await self.svc.patient_list(patient_actor))["total"], 0)
        self.assertEqual((await self.feedback.list(plan["_id"], doctor_actor)).total, 1)

    async def test_accountless_patient_feedback_requires_verified_link(self):
        doctor_actor = actor(DOCTOR, "doctor")
        linked_actor = actor(str(self.legacy_patient_id), "patient")
        await self.seed_and_migrate()
        patient = await self.create_accountless_patient()
        patient_id = patient["patient_id"]
        plan = await self.create_plan(patient_id)
        draft = await self.svc.save_draft(plan["_id"], doctor_actor, self.draft_request())
        published = await self.svc.publish(plan["_id"], doctor_actor, self.publish_request(draft))
        clinical = await self.db[PATIENTS].find_one({"patient_id": patient_id})
        self.assertGreaterEqual(clinical.get("_fence_access", 0), 1)

        # 无链接账号（迁移患者账号）对无账号患者方案提交反馈：本人解析经
        # resolve_self 未通过 → 403，绝不按同 ID 假设放行
        with self.assertRaises(AppBaseException) as denied:
            await self.feedback.submit(plan["_id"],
                self.feedback_payload(published["version_id"], published["items"][0]["item_id"]),
                linked_actor)
        self.assertEqual(denied.exception.status_code, 403)
        self.assertEqual(denied.exception.error_code, "REHAB_PATIENT_FORBIDDEN")
        # 医护历史查询：身份锚点（verified 链接）不可解析 → fail-closed 503
        with self.assertRaises(AppBaseException) as anchor:
            await self.feedback.list(plan["_id"], doctor_actor)
        self.assertEqual(anchor.exception.status_code, 503)
        self.assertEqual(anchor.exception.error_code, "REHAB_PATIENT_ACCOUNT_UNAVAILABLE")
        self.assertEqual(await self.db.rehab_execution_events.count_documents({}), 0)

        # 无链接账号本人列表同样被拒（resolve_self 未通过，不猜 ID）。
        # 注意 linked_actor 自带 verified 链接（迁移载体），其本人空列表合法；
        # 被拒的是从未建立链接的账号。
        stray_id = ObjectId()
        await self.db.users.insert_one({
            "_id": stray_id, "role": "patient", "name": "无链接账号", "is_active": True,
            "email": f"stray-{stray_id}@publication.invalid", "password_hash": "!",
            "permissions": [], "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)})
        with self.assertRaises(AppBaseException) as forbidden:
            await self.svc.patient_list(actor(str(stray_id), "patient"))
        self.assertEqual(forbidden.exception.status_code, 403)
        self.assertEqual(forbidden.exception.error_code, "REHAB_PATIENT_FORBIDDEN")

        # 账号补关联（legacy_same_document 载体替位）：反馈与本人列表打开
        await self.db.users.insert_one({
            "_id": ObjectId(patient_id), "role": "patient", "name": "演练无账号患者",
            "email": f"adopted-{patient_id}@publication.invalid", "password_hash": "!",
            "permissions": [], "is_active": True,
            "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})
        await self.db[PATIENTS].update_one({"patient_id": patient_id},
                                           {"$set": {"legacy_user_id": patient_id}})
        await self.db[ACCOUNT_LINKS].insert_one({
            "_id": f"legacy:{patient_id}", "account_id": patient_id,
            "account_document_id": ObjectId(patient_id), "patient_id": patient_id,
            "status": "verified", "source": "legacy_same_document", "schema_version": 1,
            "audit": {"reviewer": "publication-loop-reviewer",
                      "evidence_reference": "adopt-evidence-1",
                      "operation": "legacy_same_document_migration",
                      "at": datetime.now(timezone.utc)}})
        patient_actor = actor(patient_id, "patient")
        submitted = await self.feedback.submit(plan["_id"],
            self.feedback_payload(published["version_id"], published["items"][0]["item_id"]),
            patient_actor)
        self.assertTrue(submitted.created)
        stored = await self.db.rehab_execution_events.find_one({})
        self.assertEqual(stored["recorded_by"], patient_id)
        self.assertEqual((await self.feedback.list(plan["_id"], doctor_actor)).total, 1)
        self.assertEqual((await self.svc.patient_list(patient_actor))["total"], 1)

    async def test_concurrent_assignment_revocation_rechecks_authority(self):
        doctor_actor = actor(DOCTOR, "doctor")
        await self.seed_and_migrate()
        plan = await self.create_plan(str(self.legacy_patient_id))
        draft = await self.svc.save_draft(plan["_id"], doctor_actor, self.draft_request())
        original = self.svc._authorize
        observed = asyncio.Event()
        resume = asyncio.Event()
        paused = False

        async def pause(plan, actor, session, **kwargs):
            nonlocal paused
            if not paused:
                paused = True
                await original(plan, actor, session, write=False, fence=False)
                observed.set()
                await resume.wait()
            return await original(plan, actor, session, **kwargs)

        with patch.object(self.svc, "_authorize", new=pause):
            task = asyncio.create_task(self.svc.publish(plan["_id"], doctor_actor, self.publish_request(draft)))
            await asyncio.wait_for(observed.wait(), 3)
            # 归属并发撤写：与栅栏 $inc 写同一患者文档 → 事务写冲突中止重试，
            # 重试后重新读取授权快照即拒绝
            await self.db[PATIENTS].update_one({"patient_id": str(self.legacy_patient_id)},
                                               {"$set": {"practitioners": []}})
            resume.set()
            with self.assertRaises(AppBaseException) as caught:
                await task
        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(await self.db.rehab_plan_versions.count_documents({"status": "published"}), 0)

    async def test_concurrent_account_disable_blocks_subsequent_writes(self):
        """canonical 账号侧撤权语义（波次 2 如实记录）。

        栅栏载体拆分后账号态载体是独立 account_fences 集合（cutover plan
        §3.2「账号撤权写入与栅栏递增互不干扰」）：users.is_active 的并发停用
        不与本次发布事务的写集冲突，授权读取（快照）时仍有效的发布照常提交；
        但停用对该账号的后续任何写入立即生效（下一事务的账号读取即拒绝）。
        与 legacy「users 同文档写冲突触发重试复核」的差异登记为波次项：
        撤权路径参与 account_fences 计数（或 CAS check）后方可对账上关闭
        该窗口。实体侧并发归属撤写仍由 PatientFenceStore 与 clinical_patients
        的写冲突保证（见并发归属撤权用例）。
        """
        doctor_actor = actor(DOCTOR, "doctor")
        await self.seed_and_migrate()
        plan = await self.create_plan(str(self.legacy_patient_id))
        draft = await self.svc.save_draft(plan["_id"], doctor_actor, self.draft_request())
        original = self.svc._authorize
        observed = asyncio.Event()
        resume = asyncio.Event()
        paused = False

        async def pause(plan, actor, session, **kwargs):
            nonlocal paused
            if not paused:
                paused = True
                await original(plan, actor, session, write=False, fence=False)
                observed.set()
                await resume.wait()
            return await original(plan, actor, session, **kwargs)

        with patch.object(self.svc, "_authorize", new=pause):
            task = asyncio.create_task(self.svc.publish(plan["_id"], doctor_actor, self.publish_request(draft)))
            await asyncio.wait_for(observed.wait(), 3)
            await self.db.users.update_one({"_id": ObjectId(DOCTOR)}, {"$set": {"is_active": False}})
            resume.set()
            # 授权读取时仍有效的发布照常提交（不假报失败）
            published = await asyncio.wait_for(task, 10)
            self.assertEqual(published["version_id"], draft["draft"]["id"])
        # 停用后的下一次写入立即被拒
        with self.assertRaises(AppBaseException) as caught:
            await self.svc.save_draft(plan["_id"], doctor_actor, self.draft_request())
        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(caught.exception.error_code, "REHAB_ACCOUNT_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
