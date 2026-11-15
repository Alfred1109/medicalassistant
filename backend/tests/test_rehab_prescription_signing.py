"""T72 结构化处方 / 禁忌阻断 / 签署记录的服务级验收（legacy 域模式）。

门控：复用 REHAB_TEST_PUBLICATION_MONGO_URI（test_rehab_publications.py
同一套一次性本地副本集约定）；无 URI 全部跳过。每个用例独立临时库并在
teardown drop。legacy 模式（不迁移患者域）验证：

1. 结构化处方增量字段（疗程 course / 执行要求 execution_requirements）
   进入发布快照并在患者投影可见；已发布历史快照（无增量字段的旧形态）
   重新投影不破坏——患者端只读语义不变；
2. 禁忌规则引擎在发布事务内复检：block 命中阻断发布（422
   REHAB_CONTRAINDICATION_BLOCK，findings 随 details 返回）；warn 命中
   不阻断、随草稿/发布版本落库；规则集合覆盖（rehab_clinical_rules）
   与结构坏规则 fail-closed（503）；
3. 签署记录：发布成功后在版本文档落 signature（签署人/时间/声明文案/
   快照哈希），医护草稿响应可见，患者投影不含签署内容；发布操作记录
   （rehab_publication_operations）同步携带 signature。
"""
import os
import unittest
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import ValidationError

from app.core.exceptions import AppBaseException
from app.schemas.rehab_publication import PublishDraft, SavePublicationDraft
from app.services.rehab_publication_service import RehabPublicationService

URI = os.environ.get("REHAB_TEST_PUBLICATION_MONGO_URI")

DOCTOR = str(ObjectId())


def doctor_actor():
    return SimpleNamespace(id=DOCTOR, role="doctor")


@unittest.skipUnless(URI, "set REHAB_TEST_PUBLICATION_MONGO_URI to an isolated local replica set")
class PrescriptionSigningTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue(URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")))
        self.mongo = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.mongo["rehab_prescription_signing_" + uuid4().hex]
        self.patient_id = ObjectId()
        self.plan_id = ObjectId()
        # 患者带诊断与过敏史字段位（legacy users 同文档医学字段）；各用例按需覆盖
        await self.db.users.insert_many([
            {"_id": self.patient_id, "role": "patient", "is_active": True,
             "name": "处方签署患者", "practitioners": [DOCTOR], "password_hash": "secret",
             "medical_info": {"diagnosis": "高血压"}, "allergies": []},
            {"_id": ObjectId(DOCTOR), "role": "doctor", "is_active": True},
        ])
        await self.db.rehab_plans.insert_one({"_id": self.plan_id, "patient_id": str(self.patient_id),
            "name": "签署演练方案", "status": "active"})
        self.svc = RehabPublicationService(self.db)
        self.doctor = doctor_actor()
        self.plan = str(self.plan_id)

    async def asyncTearDown(self):
        await self.mongo.drop_database(self.db.name)
        self.mongo.close()

    def draft_request(self, **updates):
        data = {"request_id": uuid4().hex, "content": {"name": "签署演练", "description": "Reviewed content",
            "goal": "A recorded goal", "start_date": "2026-11-15T08:00:00+08:00"},
            "items": [{"intervention_type": "exercise", "name": "平地步行训练", "schedule": {"sets": 2}}]}
        data.update(updates)
        return SavePublicationDraft.model_validate(data)

    def publish_request(self, draft, previous=None, **updates):
        data = {"request_id": uuid4().hex, "draft_id": draft["draft"]["id"],
            "expected_draft_revision": draft["draft"]["revision"], "expected_publication_id": previous,
            "confirmed": True, "declaration_acknowledged": True,
            "confirmation_note": "Clinician signed this publication"}
        data.update(updates)
        return PublishDraft.model_validate(data)

    async def save(self, **updates):
        return await self.svc.save_draft(self.plan, self.doctor, self.draft_request(**updates))

    async def test_block_finding_stops_publish_and_warn_is_stored(self):
        # 患者诊断「高血压」+ 运动项文本「倒立」→ 内置示例 warn 规则命中
        draft = await self.save(items=[{"intervention_type": "exercise", "name": "倒立拉伸训练"}])
        self.assertEqual([finding["rule_id"] for finding in draft["draft"]["contraindication_findings"]["warnings"]],
                         ["sample-warn-hypertension-inversion"])
        self.assertEqual(draft["draft"]["contraindication_findings"]["blocks"], [])
        published = await self.svc.publish(self.plan, self.doctor, self.publish_request(draft))
        version = await self.db.rehab_plan_versions.find_one({"_id": ObjectId(published["version_id"])})
        self.assertEqual(version["contraindication_findings"]["warnings"][0]["rule_id"],
                         "sample-warn-hypertension-inversion")
        self.assertEqual(version["contraindication_findings"]["blocks"], [])

    async def test_block_rule_stops_publish_with_findings_detail(self):
        await self.db.users.update_one({"_id": self.patient_id},
            {"$set": {"allergies": ["青霉素过敏"], "medical_info": {"diagnosis": "上呼吸道感染"}}})
        draft = await self.save(items=[{"intervention_type": "medication", "name": "青霉素V钾片",
            "medication_fields": {"drug_ref": "青霉素V钾片", "frequency": "每日三次"}}])
        # 草稿保存不阻断（block 预览可见）
        self.assertEqual(draft["draft"]["contraindication_findings"]["blocks"][0]["level"], "block")
        with self.assertRaises(AppBaseException) as caught:
            await self.svc.publish(self.plan, self.doctor, self.publish_request(draft))
        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(caught.exception.error_code, "REHAB_CONTRAINDICATION_BLOCK")
        self.assertEqual(caught.exception.details["findings"][0]["rule_id"],
                         "sample-block-penicillin-allergy")
        self.assertEqual(await self.db.rehab_plan_versions.count_documents({"status": "published"}), 0)

    async def test_signature_binds_version_snapshot_and_stays_clinician_visible(self):
        draft = await self.save()
        published = await self.svc.publish(self.plan, self.doctor, self.publish_request(draft))
        version = await self.db.rehab_plan_versions.find_one({"_id": ObjectId(published["version_id"])})
        signature = version["signature"]
        self.assertEqual(signature["signed_by"], DOCTOR)
        self.assertEqual(signature["signed_by_role"], "doctor")
        self.assertEqual(signature["declaration_acknowledged"], True)
        self.assertIn("待临床确认", signature["declaration_status"])
        self.assertRegex(signature["snapshot_hash"], r"^[0-9a-f]{64}$")
        self.assertEqual(signature["confirmation_note"], "Clinician signed this publication")

        # 医护草稿响应可见签署记录；发布操作记录同步携带
        state = await self.svc.draft(self.plan, self.doctor)
        self.assertEqual(state["signature"]["snapshot_hash"], signature["snapshot_hash"])
        operation = await self.db.rehab_publication_operations.find_one(
            {"plan_id": self.plan, "kind": "publish"})
        self.assertEqual(operation["result"]["signature"]["snapshot_hash"], signature["snapshot_hash"])

        # 患者投影不含签署内容（患者查看语义不变）
        detail = await self.svc.patient_detail(self.plan, SimpleNamespace(id=str(self.patient_id), role="patient"))
        self.assertNotIn("signature", detail)
        for item in detail["items"]:
            self.assertNotIn("signature", item)

    async def test_structured_prescription_fields_reach_snapshot_and_history_stays_valid(self):
        # 增量字段进入发布快照并对患者可见
        draft = await self.save(items=[{"intervention_type": "exercise", "name": "股四头肌训练",
            "course": {"duration_days": 14, "sessions_total": 6, "note": "两周复评"},
            "execution_requirements": ["每周复评一次"]}])
        published = await self.svc.publish(self.plan, self.doctor, self.publish_request(draft))
        self.assertEqual(published["items"][0]["course"]["duration_days"], 14)
        self.assertEqual(published["items"][0]["execution_requirements"], ["每周复评一次"])
        detail = await self.svc.patient_detail(self.plan, SimpleNamespace(id=str(self.patient_id), role="patient"))
        self.assertEqual(detail["items"][0]["course"]["sessions_total"], 6)

        # 已发布历史快照（旧形态：无增量字段）重新投影不破坏
        old_snapshot = deepcopy(published["items"][0])
        for key in ("course", "execution_requirements"):
            old_snapshot.pop(key, None)
        await self.db.rehab_plan_versions.update_one({"_id": ObjectId(published["version_id"])},
            {"$set": {"items_snapshot": [old_snapshot]}})
        detail = await self.svc.patient_detail(self.plan, SimpleNamespace(id=str(self.patient_id), role="patient"))
        self.assertNotIn("course", detail["items"][0])
        self.assertNotIn("execution_requirements", detail["items"][0])
        self.assertEqual(detail["items"][0]["name"], "股四头肌训练")

    async def test_rule_collection_override_replaces_builtin_and_fail_closed(self):
        # 覆盖规则：整集替换内置示例——内置过敏阻断与示例 warn 均不再生效
        await self.db.rehab_clinical_rules.insert_one({"rule_id": "custom-block", "level": "block",
            "scope": "any", "description": "自定义阻断", "message": "自定义规则命中：{item_name}",
            "when_item": {"text_includes_any": ["特殊禁用"]}})
        draft = await self.save(items=[{"intervention_type": "medication", "name": "青霉素V钾片",
            "medication_fields": {"drug_ref": "青霉素V钾片"}}])
        self.assertEqual(draft["draft"]["contraindication_findings"]["blocks"], [])
        self.assertEqual(draft["draft"]["contraindication_findings"]["warnings"], [])
        published = await self.svc.publish(self.plan, self.doctor, self.publish_request(draft))
        self.assertEqual(published["items"][0]["name"], "青霉素V钾片")
        # 新覆盖规则生效：命中「特殊禁用」字样的处方项被阻断
        draft2 = await self.save(items=[{"intervention_type": "exercise", "name": "倒立拉伸训练"}])
        self.assertEqual(draft2["draft"]["contraindication_findings"]["warnings"], [])
        draft3 = await self.save(items=[{"intervention_type": "exercise", "name": "特殊禁用动作"}],
            expected_draft_id=draft2["draft"]["id"], expected_draft_revision=draft2["draft"]["revision"])
        self.assertEqual(draft3["draft"]["contraindication_findings"]["blocks"][0]["rule_id"], "custom-block")
        with self.assertRaises(AppBaseException) as blocked:
            await self.svc.publish(self.plan, self.doctor,
                self.publish_request(draft3, published["version_id"]))
        self.assertEqual(blocked.exception.details["findings"][0]["rule_id"], "custom-block")
        self.assertEqual(blocked.exception.details["warnings"], [])

        # 结构坏规则 fail-closed：草稿保存被拒绝
        await self.db.rehab_clinical_rules.delete_many({})
        await self.db.rehab_clinical_rules.insert_one({"rule_id": "broken", "level": "fatal"})
        with self.assertRaises(AppBaseException) as invalid:
            await self.save(items=[{"intervention_type": "exercise", "name": "任意项"}],
                expected_draft_id=draft3["draft"]["id"], expected_draft_revision=draft3["draft"]["revision"])
        self.assertEqual(invalid.exception.error_code, "REHAB_CLINICAL_RULES_INVALID")

    async def test_signature_declaration_override_reaches_version(self):
        await self.db.rehab_clinical_signature.insert_one({"key": "publish_signature",
            "declaration": "临床确认后的签署声明", "status": "confirmed"})
        draft = await self.save()
        published = await self.svc.publish(self.plan, self.doctor, self.publish_request(draft))
        version = await self.db.rehab_plan_versions.find_one({"_id": ObjectId(published["version_id"])})
        self.assertEqual(version["signature"]["declaration"], "临床确认后的签署声明")
        self.assertEqual(version["signature"]["declaration_status"], "confirmed")

    async def test_clinician_info_endpoints_serve_declared_rules_and_declaration(self):
        self.assertEqual((await self.svc.signature_declaration(self.doctor))["status"], "待临床确认")
        rules = await self.svc.contraindication_rules(self.doctor)
        self.assertTrue(rules and all("description" in rule for rule in rules))
        # 患者身份不能读取临床口径
        patient = SimpleNamespace(id=str(self.patient_id), role="patient")
        for call in (self.svc.signature_declaration(patient), self.svc.contraindication_rules(patient)):
            with self.assertRaises(AppBaseException) as caught:
                await call
            self.assertEqual(caught.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
