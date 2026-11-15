"""T55 演练：canonical 模式下「无账号患者」全链路验收（cutover plan 目标形态验证）。

架构目标：clinical_patients 是临床实体（可无账号），账号经人工核实 + 审计凭证的
patient_account_links 显式关联（可选）。本演练证明一个没有登录账号的临床患者
能从建档走完整条临床链路，并如实记录每一步的走通/受阻状态。

门控：REHAB_TEST_CANONICAL_LOOP_URI
（mongodb://127.0.0.1:<port>/...?replicaSet=<name>&directConnection=true）。
迁移/导入/业务事务依赖快照事务，standalone 无法执行；无 URI 全部跳过。
每个用例使用独立临时库（uuid 后缀）并在 teardown drop，只触碰 URI 指向实例上
自己创建的库。合成数据，不触碰任何真实业务库。

主链用例逐步记录（file:line 指向被断言的真实语义）：
1. 建库到 canonical：legacy 最小数据 → migrate_legacy_patients → canonical 模式。
2. 无账号建档：create_from_source 创建无 links 临床患者；患者存在于
   clinical_patients、users/links 零写入、resolve_self 拒绝、医护 assigned
   范围与对象授权可见。医护归属写入以直接更新替位（canonical 归属写入工作流
   尚未落地，登记为波次项；authorization 语义以内核断言为准）。
3. 随访/健康档案：内核授权（ensure_followup_patient_access /
   ensure_health_record_patient_access）+ 服务写入全走通；工作台姓名搜索的
   canonical 域分派为 T55 当场修复（原实现把 legacy 适配器查询交给 users
   执行，无账号患者被静默过滤成空，见 followup_service.list_workbench）。
   提醒扫描/派发在波次 3（T65）后 canonical 走通：收件人解析经
   patient_account_links，无账号患者的患者槽位跳过（PATIENT_ACCOUNT_UNAVAILABLE）、
   医护槽位照常投递，栅栏落双载体（account_fences +
   clinical_patients._fence_reminder）。
4. 康复方案：方案创建/列表走通（list_rehab_plans 经 assigned_scope_ids 域感知）；
   波次 2 门闩移除后发布走通（canonical 双载体栅栏落在 account_fences +
   clinical_patients._fence_rehab_publish，T67 缺陷 1 后栅栏名域化）；
   无账号患者本人不能读取/反馈（无 verified 链接，账号不可达=预期形态）。
5. 设备：波次 5 后绑定与手工读数走通（canonical 双载体栅栏落在
   account_fences("device") + clinical_patients._fence_device，users 文档
   不再承担栅栏计数；T55 演练的「写阻」缺口闭合）；对象授权读路径
   （resolve_device_patient/device_patient_scope）与设备读数读路径同步验证。
6. 质控：T63 波次 2/3 门闩移除后 canonical 全流程走通（问题全生命周期、
   list/assignees、栅栏双载体 account_fences +
   clinical_patients._fence_quality_access、过程监测 scope/overview）；
   波次 3/4 换源落地后引用核验直查 clinical_patients（T66）：无账号患者的
   随访引用如实按 valid 计数、issue_eligible=True（不再经 users 误判
   not_found）。
7. 统计：analytics 患者聚合源仍是 users（analytics_service.py
   PATIENTS_COLLECTION_NAME），无账号患者不被统计（波次 4 缺口，如实断言）。
8. 账号补关联（T64 显式绑定工作流）：管理员人工核实（reviewer + evidence）
   后经 repo.bind_account 建立独立 explicit_binding origin 的 verified 链接
   （账号 ID 与临床患者 ID 不同，无需 legacy_user_id/ID 对齐），resolve_self
   打通，患者范围解析自取（followup/device scope）、随访/健康档案/设备的
   对象级自取（T67 缺陷 2 后内核患者角色实体解析经 repo.resolve_self 域分派，
   带目标参数的自取不再被同文档前置假设拒绝）、医患通信与康复发布读取/
   反馈通路全部打开——「账号可选」的正向证明；末尾以管理员停用链接
   （verified→disabled 状态机）验证通路如实关闭、停用链接为终态文档。
"""
import os
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.device_access import device_patient_scope, resolve_device_patient
from app.core.exceptions import AppBaseException
from app.core.followup_access import ensure_followup_patient_access, followup_patient_scope
from app.core.health_record_access import ensure_health_record_patient_access
from app.core.patient_access import (PatientAccessError, assigned_scope_ids,
                                     ensure_patient_access, ensure_self_patient_access)
from app.patients.migration import inspect_migration, migrate_legacy_patients
from app.patients.repository import (ACCOUNT_LINKS, PATIENTS, STATE, STATE_ID,
                                     ClinicalPatientRepository)
from app.services.analytics_service import AnalyticsService
from app.services.communication_service import CommunicationService
from app.services.device_service import DeviceService
from app.services.followup_reminder_service import FollowupReminderService
from app.services.followup_service import FollowupService
from app.services.health_record_service import HealthRecordService
from app.services.quality_issue_service import QualityIssueService
from app.services.quality_monitoring_service import QualityMonitoringService
from app.services.rehab_feedback_service import RehabFeedbackService
from app.services.rehab_publication_service import RehabPublicationService
from app.services.rehabilitation_service import RehabilitationService
from app.schemas.followup import FollowUpRecordCreate
from app.schemas.health_record import HealthRecordCreate
from app.schemas.quality_issue import (AssignQualityIssue, ConfirmQualityIssue, QualityIssueCreate,
    ResolveQualityIssue, ReviewQualityIssue)
from app.schemas.rehab_feedback import PatientFeedbackCreate, PatientExecutionStatus
from app.schemas.rehab_publication import PublishDraft, SavePublicationDraft
from app.schemas.rehabilitation import RehabPlanCreate

URI = os.environ.get("REHAB_TEST_CANONICAL_LOOP_URI")

# 医护账号用 ObjectId 形态：通信域会话成员 ID 必须是 ObjectId（conversation_policy）。
DOCTOR = str(ObjectId())
MANAGER = str(ObjectId())
UNASSIGNED_DOCTOR = str(ObjectId())
SOURCE = {"origin": "https://source.example", "system": "form-platform-11344",
          "environment": "production", "patient_id": 7}


def actor(account_id, role):
    """最小认证主体替身：内核只消费 id/role 两个属性。"""
    return type("LoopActor", (), {"id": account_id, "role": role})()


@unittest.skipUnless(URI, "set REHAB_TEST_CANONICAL_LOOP_URI to an isolated local replica set")
class CanonicalAccountlessLoopTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if not URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")):
            self.fail("only an explicit loopback test URI is accepted")
        self.client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.client["rehab_canonical_loop_" + uuid4().hex]
        self.repo = ClinicalPatientRepository(self.db)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    async def asyncTearDown(self):
        await self.client.drop_database(self.db.name)
        self.client.close()
        self.temp.cleanup()

    @staticmethod
    def stopped():
        return {"application_stopped": True, "guard_reference": "canonical-loop-fixture"}

    async def migrate(self, **overrides):
        options = dict(expected_manifest=await inspect_migration(self.db),
                       backup_directory=self.root / uuid4().hex,
                       reviewer="loop-reviewer",
                       evidence_reference="loop-evidence",
                       maintenance_guard=self.stopped)
        options.update(overrides)
        return await migrate_legacy_patients(self.db, **options)

    def seed_documents(self):
        """合成 legacy 数据：1 个存量患者（有账号同文档）+ 医护账号。"""
        self.legacy_patient_id = ObjectId()
        return [
            {"_id": self.legacy_patient_id, "role": "patient", "name": "存量患者",
             "is_active": True, "email": "legacy-loop@example.com",
             "password_hash": "do-not-project",
             "practitioners": [DOCTOR], "health_managers": [MANAGER],
             "medical_info": {"diagnosis": "stroke"},
             "demographic_info": {"gender": "female", "age": 54}},
            {"_id": ObjectId(DOCTOR), "role": "doctor", "name": "演练医生", "is_active": True},
            {"_id": ObjectId(MANAGER), "role": "health_manager", "name": "演练管理师", "is_active": True},
            {"_id": ObjectId(UNASSIGNED_DOCTOR), "role": "doctor", "name": "无关医生", "is_active": True},
        ]

    async def seed_and_migrate(self):
        await self.db.users.insert_many([deepcopy(item) for item in self.seed_documents()])
        result = await self.migrate()
        self.assertEqual(result["migrated_count"], 1)
        self.assertEqual(result["account_links_created"], 1)

    async def create_accountless_patient(self):
        """步骤 2：经 create_from_source 创建无账号临床患者 + 医护归属替位写入。"""
        document = await self.repo.create_from_source(
            SOURCE, reviewer="loop-reviewer", evidence_reference="loop-evidence-1",
            name="演练无账号患者")
        # canonical 归属写入工作流尚未落地（波次登记项）：以直接更新替位，
        # 授权语义本身以内核断言为准（与迁移投影写归属字段同一数据形态）。
        await self.db[PATIENTS].update_one({"patient_id": document["patient_id"]},
                                           {"$set": {"practitioners": [DOCTOR],
                                                     "health_managers": [MANAGER]}})
        return document

    async def test_accountless_patient_full_clinical_loop(self):
        # -- 步骤 1：建库到 canonical --
        await self.seed_and_migrate()
        state = await self.db[STATE].find_one({"_id": STATE_ID})
        self.assertEqual(state["mode"], "canonical")

        # -- 步骤 2：无账号患者建档（create_from_source，无 links）--
        patient = await self.create_accountless_patient()
        patient_id = patient["patient_id"]
        stored = await self.repo.get(patient_id)
        self.assertEqual(stored["status"], "active")
        self.assertEqual(stored["name"], "演练无账号患者")
        self.assertIsNone(stored.get("legacy_user_id"))
        self.assertEqual(stored["source"]["patient_id"], 7)
        # 无账号依赖：users 与 links 零新增
        self.assertEqual(await self.db.users.count_documents({"role": "patient"}), 1)
        self.assertEqual(await self.db[ACCOUNT_LINKS].count_documents({}), 1)
        self.assertEqual(await self.db[ACCOUNT_LINKS].count_documents(
            {"patient_id": patient_id}), 0)
        # 本人自取被拒（无链接：账号路径严格 fail-closed，不猜 ID）
        with self.assertRaises(PatientAccessError) as denied:
            await ensure_self_patient_access(self.db, actor(patient_id, "patient"))
        self.assertEqual(denied.exception.status_code, 403)
        self.assertIsNone(await self.repo.resolve_self(patient_id))
        # 医护在授权范围与对象级访问中可见（assigned 范围）
        self.assertIn(patient_id, await assigned_scope_ids(self.db, DOCTOR, "doctor"))
        self.assertIn(patient_id,
                      [item["patient_id"] for item in await self.repo.list_assigned(DOCTOR, "doctor")])
        granted = await ensure_patient_access(self.db, patient_id, DOCTOR, "doctor")
        self.assertEqual(granted["patient_id"], patient_id)
        with self.assertRaises(PatientAccessError) as forbidden:
            await ensure_patient_access(self.db, patient_id, UNASSIGNED_DOCTOR, "doctor")
        self.assertEqual(forbidden.exception.status_code, 403)
        # 医护患者列表（PatientCRUD.find_assigned_patients，T55 域分派修复后）
        from app.db.crud_services import PatientCRUD
        from app.models.user import Patient
        listed = await PatientCRUD(self.db, Patient).find_assigned_patients(DOCTOR, "doctor")
        self.assertEqual({item["id"] for item in listed},
                         {patient_id, str(self.legacy_patient_id)})

        # -- 步骤 3：随访（写授权 + 服务写入 + 工作台范围/姓名搜索）--
        doctor_actor = actor(DOCTOR, "doctor")
        await ensure_followup_patient_access(self.db, patient_id, doctor_actor, write=True)
        followup = await FollowupService(self.db).create_followup_record(FollowUpRecordCreate(
            patient_id=patient_id, follow_up_type="电话随访", provider_id=DOCTOR,
            description="无账号患者随访",
            scheduled_date=datetime.now(timezone.utc) + timedelta(days=1)))
        row = await self.db.followup_records.find_one({"_id": ObjectId(followup.id)})
        self.assertEqual(row["patient_id"], patient_id)
        # 提醒派发（波次 3/T65 后）：canonical 收件人解析经 patient_account_links；
        # 无账号患者（无 verified 链接）的患者槽位跳过不报错，医护槽位照常投递
        service = FollowupReminderService(self.db)
        self.assertEqual((await service.dispatch_one(followup.id))["generated"], 1)
        notices = await self.db.notifications.find({}).to_list(None)
        self.assertEqual([row["recipient_id"] for row in notices], [DOCTOR])
        skipped = await self.db.followup_reminder_deliveries.find_one(
            {"slot": "patient", "reason": "PATIENT_ACCOUNT_UNAVAILABLE"})
        self.assertIsNotNone(skipped)
        self.assertEqual(skipped["status"], "skipped")
        self.assertEqual(skipped["patient_id"], patient_id)  # legacy ID 主键语义不变
        # 栅栏双载体：账号侧 account_fences（仅医护）、患者侧 clinical_patients
        self.assertGreater((await self.db.account_fences.find_one(
            {"account_id": DOCTOR, "fence_name": "reminder"}))["count"], 0)
        self.assertIsNone(await self.db.account_fences.find_one(
            {"account_id": patient_id}))
        clinical = await self.db[PATIENTS].find_one({"patient_id": patient_id})
        self.assertGreater(clinical["_fence_reminder"], 0)
        # 已投递事件幂等：scan 不重投
        self.assertEqual(await service.scan(), 0)
        self.assertEqual(await self.db.notifications.count_documents({}), 1)
        # 工作台：范围 + 姓名搜索（T55 域分派修复后 canonical 姓名搜索不再落 users）
        workbench = await FollowupService(self.db).list_workbench(
            patient_ids=await followup_patient_scope(self.db, doctor_actor))
        self.assertEqual(workbench.total, 1)
        by_name = await FollowupService(self.db).list_workbench(
            patient_ids=await followup_patient_scope(self.db, doctor_actor),
            patient_name="无账号")
        self.assertEqual(by_name.total, 1)
        self.assertEqual(by_name.items[0].id, followup.id)
        # 健康档案：对象授权 + 服务写入走通
        await ensure_health_record_patient_access(self.db, patient_id, doctor_actor)
        record = await HealthRecordService(self.db).create_health_record(HealthRecordCreate(
            patient_id=patient_id, record_type="visit", title="初诊",
            content="无账号患者健康档案", created_by=DOCTOR))
        stored = await self.db.health_records.find_one({"_id": ObjectId(record.id)})
        self.assertEqual(stored["patient_id"], patient_id)

        # -- 步骤 4：康复方案（创建/列表/草稿/发布走通；本人读取与反馈被无链接挡住）--
        plan = await RehabilitationService(self.db).create_rehab_plan(RehabPlanCreate(
            name="无账号患者方案", description="canonical 演练", patient_id=patient_id,
            start_date=datetime.now(timezone.utc), goal="恢复上肢功能"))
        plans = await RehabilitationService(self.db).list_rehab_plans(
            actor_id=DOCTOR, actor_role="doctor")
        self.assertIn(plan["_id"], {item["_id"] for item in plans})
        # 波次 2 门闩移除后：canonical 发布走通。栅栏双载体落位——账号侧
        # account_fences 计数、患者侧 clinical_patients._fence_rehab_publish
        # 计数（T67 缺陷 1 后栅栏名域化，不与质控 "quality_access" 共名）。
        from app.core.fences import create_account_fence_indexes
        await create_account_fence_indexes(self.db)
        publication = RehabPublicationService(self.db)
        draft = await publication.save_draft(plan["_id"], doctor_actor, SavePublicationDraft.model_validate({
            "request_id": "loop-draft-1",
            "content": {"name": "无账号患者方案", "description": "canonical 演练",
                        "goal": "恢复上肢功能", "start_date": "2026-11-15T00:00:00Z"},
            "items": [{"intervention_type": "exercise", "name": "上肢训练",
                       "schedule": {"sets": 2}}]}))
        published = await publication.publish(plan["_id"], doctor_actor, PublishDraft(
            request_id="loop-publish-1", draft_id=draft["draft"]["id"],
            expected_draft_revision=draft["draft"]["revision"],
            expected_publication_id=None, confirmed=True, confirmation_note="演练"))
        self.assertEqual(published["version_id"], draft["draft"]["id"])
        fence_row = await self.db.account_fences.find_one(
            {"account_id": DOCTOR, "fence_name": "rehab_publish"})
        self.assertGreaterEqual(fence_row["count"], 1)
        clinical = await self.db[PATIENTS].find_one({"patient_id": patient_id})
        self.assertGreaterEqual(clinical.get("_fence_rehab_publish", 0), 1)
        # 无账号患者本人：账号不存在（canonical 账号层仍在 users）→ 账号不可用
        with self.assertRaises(AppBaseException) as reader_gate:
            await publication.patient_detail(plan["_id"], actor(patient_id, "patient"))
        self.assertEqual(reader_gate.exception.status_code, 403)
        with self.assertRaises(AppBaseException) as feedback_gate:
            await RehabFeedbackService(self.db).submit(plan["_id"], PatientFeedbackCreate(
                event_id="2b5e1f2a-0000-4000-8000-000000000001",
                version_id=published["version_id"], prescription_item_id=published["items"][0]["item_id"],
                execution_status=PatientExecutionStatus.COMPLETED,
                feelings="演练", performed_at=datetime.now(timezone.utc) - timedelta(hours=1)),
                actor(patient_id, "patient"))
        self.assertEqual(feedback_gate.exception.status_code, 403)

        # -- 步骤 5：设备（波次 5：读路径与写路径全走通，双载体栅栏落位）--
        self.assertEqual(await resolve_device_patient(self.db, doctor_actor, patient_id),
                         patient_id)
        self.assertIn(patient_id, await device_patient_scope(self.db, doctor_actor))
        device_service = DeviceService(self.db)
        # 绑定走通：canonical 双载体栅栏落 account_fences("device") +
        # clinical_patients._fence_device，users 文档零栅栏写入——T55 演练的
        # 「写阻」缺口（无账号患者设备绑定被 users 载体 matched_count=0 挡住）
        # 随栅栏载体拆分闭合。
        bound = await device_service.bind_device(patient_id, {
            "device_type": "血压计", "name": "loop-device"}, actor=doctor_actor)
        self.assertIsNone(bound.get("error"))
        self.assertEqual(bound["patient_id"], patient_id)
        device_id = bound["_id"]
        device = await device_service.get_device(device_id)
        from app.core.device_access import ensure_device_access
        from app.services.device_service import DEVICE_READ_ROLES
        await ensure_device_access(self.db, device, doctor_actor, list(DEVICE_READ_ROLES))
        # 手工读数走通（同一双载体栅栏第二次递增）
        reading = await device_service.record_manual_reading(
            device_id, "systolic", "118", "mmHg", datetime.now(timezone.utc),
            actor=doctor_actor)
        self.assertEqual(reading["metadata"]["source"], "手工登记")
        readings = await device_service.get_device_data(device_id)
        self.assertEqual(len(readings), 1)
        device_account_fence = await self.db.account_fences.find_one(
            {"account_id": DOCTOR, "fence_name": "device"})
        self.assertGreaterEqual(device_account_fence["count"], 2)  # 绑定 + 手工读数
        self.assertGreaterEqual((await self.repo.get(patient_id)).get("_fence_device", 0), 2)
        self.assertIsNone((await self.db.users.find_one({"_id": ObjectId(DOCTOR)}))
                          .get("_device_access_fence"))

        # -- 步骤 6：质控（T63 波次 2/3 门闩移除：canonical 全流程走通）--
        issue_service = QualityIssueService(self.db)
        # 栅栏双载体：账号跳 account_fences、患者跳
        # clinical_patients._fence_quality_access（T67 缺陷 1 后栅栏名域化，
        # 与康复 "rehab_publish"/设备 "device" 各自独立计数）；users 文档
        # 不再承担并发栅栏计数（canonical 只读约定）。断言按本域名取相对增量。
        fence_before = (await self.db.account_fences.find_one(
            {"account_id": DOCTOR, "fence_name": "quality_access"}) or {}).get("count", 0)
        patient_fence_before = (await self.repo.get(patient_id)).get("_fence_quality_access", 0)
        issue, created = await issue_service.create(QualityIssueCreate(
            request_id="loop-qc-create-1", patient_id=patient_id,
            source_type="followup", source_id=followup.id,
            title="随访逾期", description="质控 canonical 演练", evidence_refs=["loop-evidence-2"]),
            doctor_actor)
        self.assertTrue(created)
        self.assertEqual(issue["status"], "open")
        self.assertEqual((await self.db.account_fences.find_one(
            {"account_id": DOCTOR, "fence_name": "quality_access"}))["count"], fence_before + 1)
        self.assertEqual((await self.repo.get(patient_id))["_fence_quality_access"],
                         patient_fence_before + 1)
        self.assertIsNone((await self.db.users.find_one({"_id": ObjectId(DOCTOR)})).get("_access_fence"))
        # 全生命周期：指派（责任人=本人）→ 确认 → 处置 → 复核关闭
        issue = await issue_service.mutate(issue["id"], "assign", AssignQualityIssue(
            request_id="loop-qc-assign-1", expected_version=0, assignee_id=DOCTOR,
            note="指派复核"), doctor_actor)
        self.assertEqual((issue["status"], issue["version"]), ("open", 1))
        # assign 两跳栅栏：_patient 双载体复核（账号跳 + 患者跳）+ _assignee
        # 账号跳 → 账号 +2、患者栅栏 +1。
        self.assertEqual((await self.db.account_fences.find_one(
            {"account_id": DOCTOR, "fence_name": "quality_access"}))["count"], fence_before + 3)
        self.assertEqual((await self.repo.get(patient_id))["_fence_quality_access"],
                         patient_fence_before + 2)
        issue = await issue_service.mutate(issue["id"], "confirm", ConfirmQualityIssue(
            request_id="loop-qc-confirm-1", expected_version=1, note="确认核实"), doctor_actor)
        self.assertEqual(issue["status"], "in_progress")
        issue = await issue_service.mutate(issue["id"], "resolve", ResolveQualityIssue(
            request_id="loop-qc-resolve-1", expected_version=2, resolution="资料补齐",
            evidence_refs=["loop-evidence-3"]), doctor_actor)
        self.assertEqual(issue["status"], "pending_review")
        issue = await issue_service.mutate(issue["id"], "review", ReviewQualityIssue(
            request_id="loop-qc-review-1", expected_version=3, decision="approve",
            note="复核通过", evidence_refs=["loop-evidence-4"]), doctor_actor)
        self.assertEqual((issue["status"], issue["version"]), ("closed", 4))
        listed = await issue_service.list(doctor_actor, limit=100)
        self.assertEqual(listed["total"], 1)
        self.assertEqual([item["id"] for item in listed["items"]], [issue["id"]])
        # 未分配医生创建被拒（canonical 归属校验同构）
        with self.assertRaises(AppBaseException) as forbidden:
            await issue_service.create(QualityIssueCreate(
                request_id="loop-qc-create-2", patient_id=patient_id,
                source_type="followup", source_id=followup.id,
                title="越权质控", description="未分配医生", evidence_refs=["loop-evidence-5"]),
                actor(UNASSIGNED_DOCTOR, "doctor"))
        self.assertEqual(forbidden.exception.status_code, 403)
        self.assertEqual(forbidden.exception.error_code, "QUALITY_PATIENT_NOT_ASSIGNED")
        # 责任人目录：canonical 归属字段保留原账号 ID 字面量
        directory = await issue_service.assignees(patient_id, doctor_actor)
        self.assertEqual({item["id"] for item in directory["items"]}, {DOCTOR, MANAGER})
        # 过程监测：范围解析走 clinical_patients（含存量迁移患者），选定患者
        # 统计走通；引用核验经波次 3/4 换源直查 clinical_patients（T66），
        # 无账号患者的随访引用如实按 valid 计数、具备开单资格（不再被
        # users 载体误判 not_found）。
        monitoring = QualityMonitoringService(self.db)
        self.assertEqual(set(await monitoring.scope(doctor_actor)),
                         {patient_id, str(self.legacy_patient_id)})
        overview = await monitoring.overview(doctor_actor, patient_id=patient_id)
        self.assertEqual(overview.scope_kind, "selected_patient")
        self.assertEqual(overview.followups.selected_total, 1)
        self.assertEqual(overview.followups.unresolved_patient_count, 0)
        page = await monitoring.details("followup", doctor_actor, patient_id=patient_id)
        self.assertEqual(page.total, 1)
        self.assertTrue(page.items[0].issue_eligible)
        self.assertEqual(page.items[0].patient_reference_state, "valid")

        # -- 步骤 7：统计（波次 4 换源后 canonical 聚合读 clinical_patients）--
        overview = await AnalyticsService(self.db).get_stats_overview()
        self.assertEqual(overview["patientCount"], 2)  # canonical：2 名 active 临床患者均被计入
        self.assertEqual(await self.db[PATIENTS].count_documents(
            {"status": "active"}), 2)  # clinical_patients 实际有 2 名患者

        # -- 步骤 8：账号补关联（「账号可选」的正向证明，T64 显式绑定工作流）--
        # 全新源患者没有 users 同文档历史，唯一合法载体是 T64 的独立
        # explicit_binding origin：管理员人工核实（reviewer + evidence）后
        # 建立账号↔患者 verified 链接；不要求 legacy_user_id / ID 对齐
        # （那是 legacy_same_document 专属）。
        account_id = str(ObjectId())
        await self.db.users.insert_one({
            "_id": ObjectId(account_id), "role": "patient", "name": "演练无账号患者",
            "email": f"adopted-{account_id}@loop.invalid", "password_hash": "!",
            "permissions": [], "is_active": True,
            "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})
        link = await self.repo.bind_account(patient_id, account_id=account_id,
                                            reviewer="loop-reviewer",
                                            evidence_reference="adopt-evidence-1")
        self.assertEqual(link["source"], "explicit_binding")
        self.assertEqual(link["status"], "verified")
        self.assertEqual(link["audit"][0]["operation"], "explicit_binding")
        self.assertIsNone((await self.repo.get(patient_id)).get("legacy_user_id"))
        self.assertEqual((await self.repo.resolve_self(account_id))["patient_id"], patient_id)
        patient_actor = actor(account_id, "patient")
        self.assertEqual(await ensure_self_patient_access(self.db, patient_actor),
                         patient_id)
        self.assertEqual(await followup_patient_scope(self.db, patient_actor), [patient_id])
        # 对象级自取全通（T67 缺陷 2 修复后行为）：患者角色实体解析经内核
        # 域分派先走 repo.resolve_self（账号 ID→verified 链接→临床患者 ID）
        # 再做目标一致性比对与对象校验——显式绑定下账号 ID≠患者 ID 不再被
        # 同文档前置假设在 canonical resolve_self 之前拒绝（原登记缺口收口）。
        # 覆盖三条对象级路径：随访/健康档案的 ensure_*_patient_access 带目标
        # 形态与 device 内核（resolve_device_patient / device_patient_scope）。
        await ensure_followup_patient_access(self.db, patient_id, patient_actor)
        await ensure_health_record_patient_access(self.db, patient_id, patient_actor)
        self.assertEqual(await device_patient_scope(self.db, patient_actor), [patient_id])
        self.assertEqual(await resolve_device_patient(self.db, patient_actor, patient_id),
                         patient_id)
        # 康复发布读取与反馈通路打开（波次 2）：本人列表经 resolve_self 解析；
        # 反馈 recorded_by 经 verified 链接解析落账号 ID（显式绑定下账号 ID
        # 与临床患者 ID 不同——反馈身份锚定账号，临床归属锚定患者）。
        self.assertEqual((await publication.patient_list(patient_actor))["total"], 1)
        self.assertEqual((await publication.patient_detail(plan["_id"], patient_actor))["version_id"],
                         published["version_id"])
        adopted_feedback = await RehabFeedbackService(self.db).submit(plan["_id"], PatientFeedbackCreate(
            event_id="2b5e1f2a-0000-4000-8000-000000000002",
            version_id=published["version_id"], prescription_item_id=published["items"][0]["item_id"],
            execution_status=PatientExecutionStatus.COMPLETED,
            feelings="补关联后反馈", performed_at=datetime.now(timezone.utc) - timedelta(hours=1)),
            patient_actor)
        self.assertTrue(adopted_feedback.created)
        stored_event = await self.db.rehab_execution_events.find_one({"event_id": (
            f"patient-report:{account_id}:2b5e1f2a-0000-4000-8000-000000000002")})
        self.assertEqual(stored_event["recorded_by"], account_id)
        self.assertEqual(stored_event["patient_id"], patient_id)
        self.assertEqual((await RehabFeedbackService(self.db).list(
            plan["_id"], doctor_actor)).total, 1)
        # 医患通信通路打开（账号即通信成员；无账号时该患者不可达——预期形态）
        conversation_id = await CommunicationService.create_conversation(self.db, DOCTOR, account_id)
        await CommunicationService.send_message(self.db, conversation_id, DOCTOR, "您好")
        await CommunicationService.send_message(self.db, conversation_id, account_id, "收到")
        messages = await self.db.messages.find({"conversation_id": conversation_id}).to_list(2)
        self.assertEqual({message["sender_id"] for message in messages}, {DOCTOR, account_id})
        conversations = await CommunicationService.get_conversations(self.db, account_id)
        self.assertEqual(conversations[0]["other_user"]["name"], "演练医生")
        # 本人随访数据可达：患者账号经 verified 链接读取自己的随访
        self.assertEqual((await FollowupService(self.db).list_workbench(
            patient_ids=await followup_patient_scope(self.db, patient_actor))).total, 1)
        # 终态：管理员停用链接（verified→disabled 状态机，文档不删除、不复活）
        # 后自取通路如实关闭。
        disabled = await self.repo.disable_account_link(
            patient_id, reviewer="loop-reviewer", evidence_reference="unbind-evidence-1")
        self.assertEqual(disabled["status"], "disabled")
        self.assertIsNone(await self.repo.resolve_self(account_id))
        with self.assertRaises(PatientAccessError):
            await ensure_self_patient_access(self.db, patient_actor)

    async def test_people_import_creates_accountless_clinical_patients(self):
        """波次 6 切换演练：canonical 下导入名册 → subject 落 clinical_patients（无账号），
        member 仍落 users（账号域）；导入台账与实体创建同事务原子提交。"""
        await self.seed_and_migrate()

        class FakeSourceClient:
            source_origin = "https://source.example"

            def __init__(self, pages):
                self.pages = pages

            async def list_people(self, project_id, *, limit=50, cursor=None):
                return self.pages[cursor]

        def person(kind, number, name):
            prefix = "patient" if kind == "subject" else "user"
            return {
                "person_key": f"{prefix}:{number}", "kind": kind, "display_name": name,
                "project_id": 4, "source": {"system": "form-platform-11344",
                                            "environment": "production"},
                "subject_id": number if kind == "subject" else None,
                "center_id": 8, "subject_code": "S9" if kind == "subject" else None,
                "subject_status": "enrolled" if kind == "subject" else None,
                "source_patient_id": number if kind == "subject" else None,
                "source_user_id": None if kind == "subject" else number,
                "oidc_subject": None, "source_roles": [] if kind == "subject" else ["crc"],
            }

        from app.integrations.forms.people_import import (IMPORT_LEDGER,
                                                          import_project_people,
                                                          list_imported_people)
        page = {"data": [person("subject", 15, "导入受试者"), person("member", 9, "导入协调员")],
                "page": {"limit": 100, "has_more": False, "next_cursor": None}}
        actor_admin = actor("loop-admin", "admin")
        result = await import_project_people(self.db, FakeSourceClient({None: page}),
                                             actor_admin, 4)
        self.assertEqual((result["created"], result["existing"]), (2, 0))

        # subject → 无账号临床患者；member → users 账号（账号域不变）
        clinical = await self.db[PATIENTS].find_one({"source.patient_id": 15})
        self.assertIsNotNone(clinical)
        self.assertEqual(clinical["name"], "导入受试者")
        self.assertEqual(clinical["practitioners"], [])
        self.assertIsNone(clinical.get("legacy_user_id"))
        self.assertEqual(await self.db.users.count_documents({"role": "patient"}), 1)
        self.assertEqual(await self.db[ACCOUNT_LINKS].count_documents({}), 1)
        member = await self.db.users.find_one({"source_person_ref": "user:9"})
        self.assertEqual(member["role"], "unassigned")
        # 导入台账：外部引用 + 审计（与实体创建同事务）
        ledger = await self.db[IMPORT_LEDGER].find_one({"patient_id": clinical["patient_id"]})
        self.assertEqual(ledger["source_project_id"], 4)
        self.assertEqual(ledger["imported_by"], "loop-admin")
        self.assertEqual(ledger["source_person_ref"], "patient:15")
        self.assertTrue(ledger["evidence_reference"])

        # 幂等：同一名册重跑按已存在计数，不重复建实体
        again = await import_project_people(self.db, FakeSourceClient({None: page}),
                                            actor_admin, 4)
        self.assertEqual((again["created"], again["existing"]), (0, 2))
        self.assertEqual(await self.db[PATIENTS].count_documents(
            {"source.patient_id": 15}), 1)

        # 名册列表合并返回（subject 经台账 + clinical，member 经 users）
        people = await list_imported_people(self.db, "https://source.example", 4)
        self.assertEqual({(row["source_kind"], row["name"]) for row in people},
                         {("subject", "导入受试者"), ("member", "导入协调员")})
        subject = next(row for row in people if row["source_kind"] == "subject")
        self.assertEqual(subject["id"], clinical["patient_id"])
        self.assertEqual(subject["role"], "patient")

        # 医护关系：set_imported_care 写 clinical_patients（canonical 载体）
        from app.integrations.forms.people_import import assign_imported_role, set_imported_care
        assigned_member = await assign_imported_role(self.db, actor_admin,
                                                     str(member["_id"]), "doctor", "复核-1")
        self.assertEqual(assigned_member["role"], "doctor")
        linked = await set_imported_care(self.db, actor_admin, clinical["patient_id"],
                                         str(member["_id"]), assigned=True,
                                         evidence_reference="责任-1")
        self.assertEqual(linked["practitioners"], [str(member["_id"])])
        self.assertEqual((await self.repo.get(clinical["patient_id"]))["practitioners"],
                         [str(member["_id"])])
        self.assertEqual((await self.db.users.find_one({"_id": member["_id"]}))["patients"],
                         [clinical["patient_id"]])
        # 医护范围可见（与步骤 2 的内核断言同源）
        self.assertIn(clinical["patient_id"],
                      await assigned_scope_ids(self.db, str(member["_id"]), "doctor"))
        removed = await set_imported_care(self.db, actor_admin, clinical["patient_id"],
                                          str(member["_id"]), assigned=False,
                                          evidence_reference="责任-2")
        self.assertEqual(removed["practitioners"], [])
        # 重新建立归属后做角色变更：canonical 归属随之清空（不变量在两域一致）
        await set_imported_care(self.db, actor_admin, clinical["patient_id"],
                                str(member["_id"]), assigned=True,
                                evidence_reference="责任-3")
        await assign_imported_role(self.db, actor_admin, str(member["_id"]),
                                   "unassigned", "复核-2")
        self.assertEqual((await self.repo.get(clinical["patient_id"]))["practitioners"], [])


if __name__ == "__main__":
    unittest.main()
