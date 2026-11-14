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
   提醒扫描仍被 REMINDER_PATIENT_DOMAIN_UNSUPPORTED 503 门闩挡住（波次 3）。
4. 康复方案：方案创建/列表走通（list_rehab_plans 经 assigned_scope_ids 域感知）；
   发布/反馈被 REHAB_PATIENT_DOMAIN_UNSUPPORTED 503 门闩挡住（波次 2），
   与账号无关——门闩内行为如实记录。
5. 设备：对象授权读路径（resolve_device_patient/device_patient_scope）走通；
   绑定与手工读数被 users 载体并发栅栏挡住（device_access.py 栅栏写
   users 文档，canonical 患者文档不在 users，matched_count=0 → 403；
   §3 栅栏载体拆分为波次项）。设备读数读路径以合成设备文档验证。
6. 质控：QUALITY_PATIENT_DOMAIN_UNSUPPORTED 503 门闩（波次 2/3），门闩内行为。
7. 统计：analytics 患者聚合源仍是 users（analytics_service.py
   PATIENTS_COLLECTION_NAME），无账号患者不被统计（波次 4 缺口，如实断言）。
8. 账号补关联：为该患者创建账号 + verified 链接后 resolve_self 打通，
   患者随访/设备自取与医患通信通路打开——「账号可选」的正向证明。
   当前实现的 verified 链接唯一受支持载体是 legacy_same_document（同 ID 账号
   + clinical 文档 legacy_user_id），演练以该载体替位；面向全新源患者的显式
   绑定工作流（独立 binding origin）未实现，登记为波次项。
"""
import os
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from bson import ObjectId
from fastapi import HTTPException
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
from app.schemas.quality_issue import QualityIssueCreate
from app.schemas.rehab_feedback import PatientFeedbackCreate, PatientExecutionStatus
from app.schemas.rehab_publication import PublishDraft
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
        # 提醒扫描：canonical 门闩（波次 3，账号解析未接链接解析）
        with self.assertRaises(AppBaseException) as reminder_gate:
            await FollowupReminderService(self.db).dispatch_one(followup.id)
        self.assertEqual(reminder_gate.exception.error_code, "REMINDER_PATIENT_DOMAIN_UNSUPPORTED")
        self.assertEqual(reminder_gate.exception.status_code, 503)
        with self.assertRaises(AppBaseException) as scan_gate:
            await FollowupReminderService(self.db).scan()
        self.assertEqual(scan_gate.exception.error_code, "REMINDER_PATIENT_DOMAIN_UNSUPPORTED")
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

        # -- 步骤 4：康复方案（创建/列表走通；发布/反馈在门闩内）--
        plan = await RehabilitationService(self.db).create_rehab_plan(RehabPlanCreate(
            name="无账号患者方案", description="canonical 演练", patient_id=patient_id,
            start_date=datetime.now(timezone.utc), goal="恢复上肢功能"))
        plans = await RehabilitationService(self.db).list_rehab_plans(
            actor_id=DOCTOR, actor_role="doctor")
        self.assertIn(plan["_id"], {item["_id"] for item in plans})
        publication = RehabPublicationService(self.db)
        with self.assertRaises(AppBaseException) as publish_gate:
            await publication.publish(plan["_id"], doctor_actor, PublishDraft(
                request_id="loop-publish-1", draft_id="a" * 24, expected_draft_revision=0,
                confirmed=True, confirmation_note="演练"))
        self.assertEqual(publish_gate.exception.error_code, "REHAB_PATIENT_DOMAIN_UNSUPPORTED")
        self.assertEqual(publish_gate.exception.status_code, 503)
        with self.assertRaises(AppBaseException) as feedback_gate:
            await RehabFeedbackService(self.db).submit(plan["_id"], PatientFeedbackCreate(
                event_id="2b5e1f2a-0000-4000-8000-000000000001",
                version_id="b" * 24, prescription_item_id="c" * 24,
                execution_status=PatientExecutionStatus.COMPLETED,
                feelings="演练", performed_at=datetime.now(timezone.utc) - timedelta(hours=1)),
                actor(patient_id, "patient"))
        self.assertEqual(feedback_gate.exception.error_code, "REHAB_PATIENT_DOMAIN_UNSUPPORTED")

        # -- 步骤 5：设备（读路径走通；写路径被 users 载体栅栏挡住）--
        self.assertEqual(await resolve_device_patient(self.db, doctor_actor, patient_id),
                         patient_id)
        self.assertIn(patient_id, await device_patient_scope(self.db, doctor_actor))
        device_service = DeviceService(self.db)
        with self.assertRaises(HTTPException) as bind_denied:
            await device_service.bind_device(patient_id, {
                "device_type": "血压计", "name": "loop-device"}, actor=doctor_actor)
        self.assertEqual(bind_denied.exception.status_code, 403)  # users 载体栅栏
        device_id = str(ObjectId())
        await self.db.devices.insert_one({
            "_id": ObjectId(device_id), "device_id": "loop-device-1", "device_type": "血压计",
            "name": "合成绑定设备", "patient_id": patient_id, "status": "active",
            "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})
        device = await device_service.get_device(device_id)
        from app.core.device_access import ensure_device_access
        from app.services.device_service import DEVICE_READ_ROLES
        await ensure_device_access(self.db, device, doctor_actor, list(DEVICE_READ_ROLES))
        await self.db.device_data.insert_one({
            "_id": ObjectId(), "device_id": device_id, "timestamp": datetime.now(timezone.utc),
            "data_type": "systolic", "value": "118", "unit": "mmHg",
            "metadata": {"source": "手工登记"}, "created_at": datetime.now(timezone.utc)})
        readings = await device_service.get_device_data(device_id)
        self.assertEqual(len(readings), 1)
        with self.assertRaises(HTTPException) as reading_denied:
            await device_service.record_manual_reading(
                device_id, "diastolic", "76", "mmHg", datetime.now(timezone.utc),
                actor=doctor_actor)
        self.assertEqual(reading_denied.exception.status_code, 403)  # 同一 users 载体栅栏

        # -- 步骤 6：质控（503 门闩内行为，波次 2/3）--
        with self.assertRaises(AppBaseException) as issue_gate:
            await QualityIssueService(self.db).create(QualityIssueCreate(
                request_id="loop-qc-create-1", patient_id=patient_id,
                source_type="followup", source_id=followup.id,
                title="随访逾期", description="质控门闩演练", evidence_refs=["loop-evidence-2"]),
                doctor_actor)
        self.assertEqual(issue_gate.exception.error_code, "QUALITY_PATIENT_DOMAIN_UNSUPPORTED")
        self.assertEqual(issue_gate.exception.status_code, 503)
        with self.assertRaises(AppBaseException) as scope_gate:
            await QualityMonitoringService(self.db).scope(doctor_actor)
        self.assertEqual(scope_gate.exception.error_code, "QUALITY_PATIENT_DOMAIN_UNSUPPORTED")

        # -- 步骤 7：统计（聚合源仍在 users，无账号患者不被统计——波次 4 缺口）--
        overview = await AnalyticsService(self.db).get_stats_overview()
        self.assertEqual(overview["patientCount"], 1)  # 只有 legacy 迁移患者被计入
        self.assertEqual(await self.db[PATIENTS].count_documents(
            {"status": "active"}), 2)  # clinical_patients 实际有 2 名患者

        # -- 步骤 8：账号补关联（「账号可选」的正向证明）--
        await self.db.users.insert_one({
            "_id": ObjectId(patient_id), "role": "patient", "name": "演练无账号患者",
            "email": f"adopted-{patient_id}@loop.invalid", "password_hash": "!",
            "permissions": [], "is_active": True,
            "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})
        await self.db[PATIENTS].update_one({"patient_id": patient_id},
                                           {"$set": {"legacy_user_id": patient_id}})
        # verified 链接：现行实现唯一受支持载体是 legacy_same_document（账号与
        # 临床实体同 ID）。面向全新源患者的显式绑定 origin 工作流未实现——登记波次项。
        await self.db[ACCOUNT_LINKS].insert_one({
            "_id": f"legacy:{patient_id}", "account_id": patient_id,
            "account_document_id": ObjectId(patient_id), "patient_id": patient_id,
            "status": "verified", "source": "legacy_same_document", "schema_version": 1,
            "audit": {"reviewer": "loop-reviewer", "evidence_reference": "adopt-evidence-1",
                      "operation": "legacy_same_document_migration",
                      "at": datetime.now(timezone.utc)}})
        self.assertEqual((await self.repo.resolve_self(patient_id))["patient_id"], patient_id)
        self.assertEqual(await ensure_self_patient_access(self.db, actor(patient_id, "patient")),
                         patient_id)
        patient_actor = actor(patient_id, "patient")
        self.assertEqual(await followup_patient_scope(self.db, patient_actor), [patient_id])
        await ensure_followup_patient_access(self.db, patient_id, patient_actor)
        self.assertEqual(await device_patient_scope(self.db, patient_actor), [patient_id])
        # 医患通信通路打开（账号即通信成员；无账号时该患者不可达——预期形态）
        conversation_id = await CommunicationService.create_conversation(self.db, DOCTOR, patient_id)
        await CommunicationService.send_message(self.db, conversation_id, DOCTOR, "您好")
        await CommunicationService.send_message(self.db, conversation_id, patient_id, "收到")
        messages = await self.db.messages.find({"conversation_id": conversation_id}).to_list(2)
        self.assertEqual({message["sender_id"] for message in messages}, {DOCTOR, patient_id})
        conversations = await CommunicationService.get_conversations(self.db, patient_id)
        self.assertEqual(conversations[0]["other_user"]["name"], "演练医生")
        # 本人随访数据可达：患者账号经 verified 链接读取自己的随访
        self.assertEqual((await FollowupService(self.db).list_workbench(
            patient_ids=await followup_patient_scope(self.db, patient_actor))).total, 1)

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
