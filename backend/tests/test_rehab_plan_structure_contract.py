"""REH01 康复方案域结构收敛契约测试。

覆盖：
1. 方案版本：白名单快照、版本号递增、审核字段位留空；
2. 处方项：服务端分配稳定 item_id、版本 item_ids 引用、_id 不入存储文档；
3. 执行事件：(plan_id, event_id) 幂等——重复提交返回既有事件、并发冲突不双写；
4. 对象级授权：患者归属校验复用 patient_access 内核，未归属 403、
   文档缺失/畸形 404、跨方案引用 404；
5. 审核修改白名单：GeneratedPlanEdits.exercises 拒绝 _id 等身份字段；
   四类干预字段位默认留空（待定 D05）。

全部使用内存打桩与合成数据，不触碰真实数据库、不调用 LLM。
"""

from copy import deepcopy
from datetime import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import AppBaseException
from app.core.patient_access import PatientAccessError
from app.schemas.rehab_plan_structure import (
    DietInterventionFields,
    ExecutionEventCreate,
    MedicationInterventionFields,
    PlanVersionCreate,
    PrescriptionItemCreate,
    PsychologyInterventionFields,
)
from app.schemas.rehabilitation import GeneratedPlanEdits
from app.services.rehab_plan_structure_service import RehabPlanStructureService

OPERATOR_ID = "507f1f77bcf86cd799439011"
OTHER_DOCTOR_ID = "507f1f77bcf86cd799439099"
PATIENT_ID = str(ObjectId())
PLAN_ID = str(ObjectId())


class FakeCursor:
    """内存 find 游标：支持 sort/skip/limit 与 async for。"""

    def __init__(self, docs, sort=None, skip=0, limit=0):
        self._docs = docs
        self._sort = sort
        self._skip = skip
        self._limit = limit

    def sort(self, key, direction):
        return FakeCursor(self._docs, sort=(key, direction),
                          skip=self._skip, limit=self._limit)

    def skip(self, count):
        return FakeCursor(self._docs, sort=self._sort, skip=count, limit=self._limit)

    def limit(self, count):
        return FakeCursor(self._docs, sort=self._sort, skip=self._skip, limit=count)

    def __aiter__(self):
        docs = deepcopy(self._docs)
        if self._sort:
            key, direction = self._sort
            docs.sort(key=lambda d: d.get(key) or 0, reverse=direction < 0)
        if self._skip:
            docs = docs[self._skip:]
        if self._limit:
            docs = docs[:self._limit]
        self._iter = iter(docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class FakeCollection:
    """内存集合打桩：覆盖本服务用到的最小 Mongo 接口。"""

    def __init__(self):
        self.docs = []
        self.insert_error = None
        self.insert_side_effect = None
        self.writes = 0

    def _match(self, query):
        matched = []
        for doc in self.docs:
            ok = True
            for key, value in query.items():
                if key == "_id":
                    if isinstance(value, ObjectId):
                        ok = doc.get("_id") == value
                    else:
                        ok = str(doc.get("_id")) == str(value)
                else:
                    ok = doc.get(key) == value
                if not ok:
                    break
            if ok:
                matched.append(doc)
        return matched

    async def find_one(self, query, **kwargs):
        matched = self._match(query)
        sort = kwargs.get("sort")
        if sort and matched:
            key, direction = sort[0]
            matched = sorted(matched, key=lambda d: d.get(key) or 0,
                             reverse=direction < 0)
        return deepcopy(matched[0]) if matched else None

    def find(self, query):
        return FakeCursor(deepcopy(self._match(query)))

    async def insert_one(self, doc):
        if self.insert_side_effect:
            # 模拟并发写入方先落库成功、当前请求收到唯一键冲突
            self.docs.append(deepcopy(self.insert_side_effect))
            raise self.insert_error
        if self.insert_error:
            raise self.insert_error
        stored = deepcopy(doc)
        stored["_id"] = ObjectId()
        self.docs.append(stored)
        return SimpleNamespace(inserted_id=stored["_id"])

    async def update_one(self, query, update):
        matched = self._match(query)
        for doc in matched:
            for key, value in update.get("$set", {}).items():
                doc[key] = deepcopy(value)
            for key, value in update.get("$push", {}).items():
                doc.setdefault(key, []).append(deepcopy(value))
            for key, amount in update.get("$inc", {}).items():
                doc[key] = doc.get(key, 0) + amount
        self.writes += 1
        return SimpleNamespace(modified_count=len(matched))

    async def create_index(self, *args, **kwargs):
        return "synthetic_index"


def make_db(patient_doc=None):
    users = FakeCollection()
    if patient_doc is not None:
        users.docs = [patient_doc]
    db = SimpleNamespace(
        users=users,
        rehab_plans=FakeCollection(),
        rehab_plan_versions=FakeCollection(),
        rehab_prescription_items=FakeCollection(),
        rehab_execution_events=FakeCollection(),
    )
    return db


def plan_doc(**overrides):
    doc = {
        "_id": ObjectId(PLAN_ID),
        "patient_id": PATIENT_ID,
        "name": "合成方案",
        "goal": "结构测试目标",
        "status": "draft",
        "exercises": [{"exercise_id": "ex-1", "progress": [{"completed": True}]}],
        "notes": "内部备注",
        # 中心/项目字段位（值待定 D02）
        "center_id": None,
        "project_id": None,
    }
    doc.update(overrides)
    return doc


def assigned_patient():
    return {"_id": ObjectId(PATIENT_ID), "role": "patient",
            "practitioners": [OPERATOR_ID]}


def make_service(db=None, patient=None):
    db = db or make_db(patient or assigned_patient())
    db.rehab_plans.docs = [plan_doc()]
    return RehabPlanStructureService(db), db


class PlanVersionContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_version_snapshot_whitelist_and_increment(self):
        service, db = make_service()
        first = await service.create_plan_version(
            PLAN_ID, PlanVersionCreate(note="初始快照"),
            operator_id=OPERATOR_ID, operator_role="doctor")
        second = await service.create_plan_version(
            PLAN_ID, PlanVersionCreate(), operator_id=OPERATOR_ID, operator_role="doctor")
        self.assertEqual(first["version_no"], 1)
        self.assertEqual(second["version_no"], 2)
        # 快照只含白名单内容字段
        self.assertEqual(first["snapshot"]["name"], "合成方案")
        self.assertEqual(first["snapshot"]["goal"], "结构测试目标")
        self.assertIn("exercises", first["snapshot"])
        self.assertNotIn("_id", first["snapshot"])
        self.assertNotIn("patient_id", first["snapshot"])
        self.assertNotIn("status", first["snapshot"])
        # 审核字段位一律留空（口径待定 REH02/D05）
        for field in ("reviewed_by", "reviewed_at", "review_note"):
            self.assertIsNone(first[field])
        # 中心/项目字段位透传（值待定 D02）
        self.assertIsNone(first["center_id"])
        self.assertIsNone(first["project_id"])
        self.assertEqual(first["created_by"], OPERATOR_ID)

    async def test_version_missing_or_malformed_plan_returns_404(self):
        service, db = make_service()
        db.rehab_plans.docs = []
        with self.assertRaises(AppBaseException) as error:
            await service.create_plan_version(PLAN_ID, PlanVersionCreate(),
                operator_id=OPERATOR_ID, operator_role="doctor")
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(db.rehab_plan_versions.docs, [])
        # 畸形文档（缺失 patient_id）同样 404，不暴露存在性
        db.rehab_plans.docs = [plan_doc(patient_id=None)]
        with self.assertRaises(AppBaseException) as error:
            await service.get_plan_version(PLAN_ID, str(ObjectId()),
                operator_id=OPERATOR_ID, operator_role="doctor")
        self.assertEqual(error.exception.status_code, 404)

    async def test_cross_plan_version_reference_returns_404(self):
        service, db = make_service()
        version = await service.create_plan_version(
            PLAN_ID, PlanVersionCreate(), operator_id=OPERATOR_ID, operator_role="doctor")
        other_plan = plan_doc(_id=ObjectId(), patient_id=PATIENT_ID)
        db.rehab_plans.docs.append(other_plan)
        with self.assertRaises(AppBaseException) as error:
            await service.get_plan_version(str(other_plan["_id"]), version["_id"],
                operator_id=OPERATOR_ID, operator_role="doctor")
        self.assertEqual(error.exception.status_code, 404)


class PrescriptionItemContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service, self.db = make_service()
        self.version = await self.service.create_plan_version(
            PLAN_ID, PlanVersionCreate(), operator_id=OPERATOR_ID, operator_role="doctor")

    async def test_item_gets_server_assigned_stable_id(self):
        item = await self.service.add_prescription_item(
            PLAN_ID, self.version["_id"],
            PrescriptionItemCreate(intervention_type="exercise", exercise_id="ex-1"),
            operator_id=OPERATOR_ID, operator_role="doctor")
        self.assertTrue(item["item_id"])
        # item_id 服务端分配（非 _id 本身），跨字段稳定存在
        self.assertNotEqual(item["item_id"], item["_id"])
        # _id 不进入存储语义字段
        self.assertNotIn("_id", {k for k in item if k == "item_id"})
        stored = self.db.rehab_prescription_items.docs[0]
        self.assertEqual(stored["item_id"], item["item_id"])
        self.assertEqual(stored["plan_id"], PLAN_ID)
        self.assertEqual(stored["version_id"], self.version["_id"])
        self.assertEqual(stored["patient_id"], PATIENT_ID)
        # 版本 item_ids 引用处方式方项
        version_doc = self.db.rehab_plan_versions.docs[0]
        self.assertEqual(version_doc["item_ids"], [item["item_id"]])

    async def test_item_clinical_field_slots_stay_empty(self):
        item = await self.service.add_prescription_item(
            PLAN_ID, self.version["_id"], PrescriptionItemCreate(),
            operator_id=OPERATOR_ID, operator_role="doctor")
        # 字段位存在且为空：适用条件 / 禁忌 / 来源 / 审核要求（待定 D05）
        for field in ("applicability_conditions", "contraindications",
                      "source_ref", "review_requirements",
                      "diet_fields", "medication_fields", "psychology_fields"):
            self.assertNotIn(field, item)  # exclude_unset：未提供即不预填
        self.assertIsNone(DietInterventionFields().energy_target)
        self.assertIsNone(MedicationInterventionFields().dosage)
        self.assertIsNone(PsychologyInterventionFields().session_plan)

    async def test_item_rejects_identity_and_unknown_fields(self):
        with self.assertRaises(Exception):
            # _id / patient_id 等身份字段不在白名单，extra=forbid 拒绝
            PrescriptionItemCreate(_id=str(ObjectId()))
        with self.assertRaises(Exception):
            PrescriptionItemCreate(patient_id="someone-else")

    async def test_item_in_unknown_version_returns_404(self):
        with self.assertRaises(AppBaseException) as error:
            await self.service.add_prescription_item(
                PLAN_ID, str(ObjectId()), PrescriptionItemCreate(),
                operator_id=OPERATOR_ID, operator_role="doctor")
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(self.db.rehab_prescription_items.docs, [])


class ExecutionEventContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service, self.db = make_service()
        self.version = await self.service.create_plan_version(
            PLAN_ID, PlanVersionCreate(), operator_id=OPERATOR_ID, operator_role="doctor")
        self.item = await self.service.add_prescription_item(
            PLAN_ID, self.version["_id"],
            PrescriptionItemCreate(intervention_type="exercise", exercise_id="ex-1"),
            operator_id=OPERATOR_ID, operator_role="doctor")

    def event(self, event_id="evt-001"):
        return ExecutionEventCreate(event_id=event_id, pain_level=2,
                                    difficulty_rating=3)

    async def test_duplicate_event_id_is_idempotent(self):
        first = await self.service.record_execution_event(
            PLAN_ID, self.item["item_id"], self.event(),
            operator_id=OPERATOR_ID, operator_role="doctor")
        self.assertTrue(first["created"])
        replay = await self.service.record_execution_event(
            PLAN_ID, self.item["item_id"], self.event(),
            operator_id=OPERATOR_ID, operator_role="doctor")
        self.assertFalse(replay["created"])
        self.assertEqual(replay["event"]["_id"], first["event"]["_id"])
        # 重复提交不产生第二条记录
        self.assertEqual(len(self.db.rehab_execution_events.docs), 1)

    async def test_concurrent_same_event_id_writes_once(self):
        # 模拟并发：另一请求先落库成功，当前请求收到唯一键冲突后回读既有事件
        winner_doc = {"_id": ObjectId(), "event_id": "evt-race", "plan_id": PLAN_ID,
                      "prescription_item_id": self.item["item_id"],
                      "patient_id": PATIENT_ID}
        self.db.rehab_execution_events.insert_error = \
            DuplicateKeyError("uniq_plan_event_id")
        self.db.rehab_execution_events.insert_side_effect = winner_doc
        result = await self.service.record_execution_event(
            PLAN_ID, self.item["item_id"], self.event("evt-race"),
            operator_id=OPERATOR_ID, operator_role="doctor")
        self.assertFalse(result["created"])
        self.assertEqual(result["event"]["event_id"], "evt-race")
        # 并发冲突后不产生第二条记录
        self.assertEqual(len(self.db.rehab_execution_events.docs), 1)

    async def test_event_binds_item_version_and_patient(self):
        result = await self.service.record_execution_event(
            PLAN_ID, self.item["item_id"], self.event(),
            operator_id=OPERATOR_ID, operator_role="doctor")
        event = result["event"]
        self.assertEqual(event["prescription_item_id"], self.item["item_id"])
        self.assertEqual(event["version_id"], self.version["_id"])
        self.assertEqual(event["patient_id"], PATIENT_ID)
        self.assertEqual(event["recorded_by"], OPERATOR_ID)
        # 计划训练实例与更正历史为字段位（口径待定 REH03）
        self.assertIsNone(event["training_instance"])
        self.assertEqual(event["correction_history"], [])

    async def test_event_for_item_of_other_plan_returns_404(self):
        other_plan = plan_doc(_id=ObjectId(), patient_id=PATIENT_ID)
        self.db.rehab_plans.docs.append(other_plan)
        with self.assertRaises(AppBaseException) as error:
            await self.service.record_execution_event(
                str(other_plan["_id"]), self.item["item_id"], self.event(),
                operator_id=OPERATOR_ID, operator_role="doctor")
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(self.db.rehab_execution_events.docs, [])


class StructureAccessContractTests(unittest.IsolatedAsyncioTestCase):
    """对象级授权：复用 patient_access 内核，未归属默认拒绝且零写入。"""

    async def test_unassigned_doctor_rejected_with_zero_writes(self):
        db = make_db({"_id": ObjectId(PATIENT_ID), "role": "patient",
                      "practitioners": [OTHER_DOCTOR_ID]})
        db.rehab_plans.docs = [plan_doc()]
        service = RehabPlanStructureService(db)
        for call in (
            lambda: service.create_plan_version(PLAN_ID, PlanVersionCreate(),
                operator_id=OPERATOR_ID, operator_role="doctor"),
            lambda: service.list_plan_versions(PLAN_ID,
                operator_id=OPERATOR_ID, operator_role="doctor"),
            lambda: service.add_prescription_item(PLAN_ID, str(ObjectId()),
                PrescriptionItemCreate(), operator_id=OPERATOR_ID,
                operator_role="doctor"),
            lambda: service.record_execution_event(PLAN_ID, "item-x",
                ExecutionEventCreate(event_id="evt-x"),
                operator_id=OPERATOR_ID, operator_role="doctor"),
            lambda: service.list_execution_events(PLAN_ID,
                operator_id=OPERATOR_ID, operator_role="doctor"),
        ):
            with self.assertRaises(PatientAccessError) as error:
                await call()
            self.assertEqual(error.exception.error_code, "PATIENT_NOT_ASSIGNED")
        # 默认拒绝：任何集合都不发生写入
        for collection in (db.rehab_plan_versions, db.rehab_prescription_items,
                           db.rehab_execution_events):
            self.assertEqual(collection.docs, [])
            self.assertEqual(collection.writes, 0)

    async def test_admin_bypass_without_patient_lookup(self):
        db = make_db({"_id": ObjectId(PATIENT_ID), "role": "patient",
                      "practitioners": [OTHER_DOCTOR_ID]})
        db.rehab_plans.docs = [plan_doc()]
        db.users.find_one = AsyncMock(return_value=None)
        service = RehabPlanStructureService(db)
        version = await service.create_plan_version(PLAN_ID, PlanVersionCreate(),
            operator_id="admin-1", operator_role="admin")
        self.assertEqual(version["version_no"], 1)
        db.users.find_one.assert_not_awaited()


class ApprovalEditWhitelistContractTests(unittest.TestCase):
    """审核修改白名单：嵌套处方项拒绝 _id 等身份字段（核查文档 :23 收尾）。"""

    def test_top_level_identity_fields_rejected(self):
        for key, value in (("_id", str(ObjectId())), ("patient_id", "other"),
                           ("status", "active"), ("metadata", {"is_approved": True})):
            with self.subTest(key=key):
                with self.assertRaises(Exception):
                    GeneratedPlanEdits(**{key: value})

    def test_nested_exercise_item_rejects_id_and_unknown_fields(self):
        with self.assertRaises(Exception):
            GeneratedPlanEdits(exercises=[{"_id": str(ObjectId()), "name": "x"}])
        with self.assertRaises(Exception):
            GeneratedPlanEdits(exercises=[{"patient_id": "someone-else"}])
        with self.assertRaises(Exception):
            GeneratedPlanEdits(exercises=[{"unknown_field": 1}])

    def test_nested_exercise_item_allows_whitelisted_structure(self):
        edits = GeneratedPlanEdits(exercises=[{
            "intervention_type": "exercise",
            "exercise_id": "ex-1",
            "name": "合成动作",
            "schedule": {"days_per_week": 3, "sets": 3, "reps": 10},
        }])
        dumped = edits.model_dump(exclude_unset=True, exclude_none=True)
        item = dumped["exercises"][0]
        self.assertNotIn("_id", item)
        self.assertEqual(item["schedule"]["sets"], 3)

        def assert_no_id_key(node):
            """任意一层都不允许出现键 `_id`（exercise_id 等含子串的不算）。"""
            if isinstance(node, dict):
                self.assertNotIn("_id", node)
                for value in node.values():
                    assert_no_id_key(value)
            elif isinstance(node, list):
                for value in node:
                    assert_no_id_key(value)

        assert_no_id_key(dumped)


if __name__ == "__main__":
    unittest.main()


# ── 真实 Mongo（隔离副本集）验证：幂等唯一索引与嵌套 _id 不落库 ────────────
# 与 test_generated_plan_approval_contract.py 相同的环境约定：
# 仅在设置 REHAB_TEST_REPLICA_URI 时运行，库按 uuid 隔离、结束后丢弃。
import asyncio
import os
from uuid import uuid4
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import ValidationError

REPLICA_URI = os.environ.get('REHAB_TEST_REPLICA_URI')


@unittest.skipUnless(REPLICA_URI, 'set isolated REHAB_TEST_REPLICA_URI')
class StructureMongoContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue(REPLICA_URI.startswith(('mongodb://127.0.0.1:', 'mongodb://localhost:')))
        self.client = AsyncIOMotorClient(REPLICA_URI, serverSelectionTimeoutMS=3000)
        self.db = self.client['rehab_structure_' + uuid4().hex]
        self.service = RehabPlanStructureService(self.db)
        await self.db.users.insert_one({"_id": ObjectId(PATIENT_ID), "role": "patient",
                                        "practitioners": [OPERATOR_ID]})
        await self.db.rehab_plans.insert_one(plan_doc())
        self.version = await self.service.create_plan_version(
            PLAN_ID, PlanVersionCreate(), operator_id=OPERATOR_ID, operator_role="doctor")

    async def asyncTearDown(self):
        await self.client.drop_database(self.db.name)
        self.client.close()

    async def test_execution_event_idempotent_under_real_unique_index(self):
        item = await self.service.add_prescription_item(
            PLAN_ID, self.version["_id"],
            PrescriptionItemCreate(intervention_type="exercise", exercise_id="ex-1"),
            operator_id=OPERATOR_ID, operator_role="doctor")
        results = await asyncio.gather(*[
            self.service.record_execution_event(
                PLAN_ID, item["item_id"],
                ExecutionEventCreate(event_id="evt-parallel", pain_level=2),
                operator_id=OPERATOR_ID, operator_role="doctor")
            for _ in range(8)])
        # 8 个并发同 event_id：仅 1 条 created=True，其余幂等回放
        self.assertEqual(sum(1 for r in results if r["created"]), 1)
        self.assertEqual(sum(1 for r in results if not r["created"]), 7)
        self.assertEqual(await self.db.rehab_execution_events.count_documents(
            {"plan_id": PLAN_ID, "event_id": "evt-parallel"}), 1)
        stored = await self.db.rehab_execution_events.find_one(
            {"plan_id": PLAN_ID, "event_id": "evt-parallel"})
        self.assertEqual(stored["patient_id"], PATIENT_ID)
        self.assertIsNone(stored["training_instance"])

    async def test_version_and_item_have_no_id_leak_and_review_slots_empty(self):
        item = await self.service.add_prescription_item(
            PLAN_ID, self.version["_id"], PrescriptionItemCreate(),
            operator_id=OPERATOR_ID, operator_role="doctor")
        stored_version = await self.db.rehab_plan_versions.find_one(
            {"_id": ObjectId(self.version["_id"])})
        self.assertEqual(stored_version["item_ids"], [item["item_id"]])
        for field in ("reviewed_by", "reviewed_at", "review_note"):
            self.assertIsNone(stored_version[field])
        stored_item = await self.db.rehab_prescription_items.find_one(
            {"item_id": item["item_id"]})
        # 存储文档以稳定 item_id 为业务身份，_id 仅为 Mongo 主键
        self.assertEqual(stored_item["item_id"], item["item_id"])
        self.assertEqual(stored_item["plan_id"], PLAN_ID)

    async def test_approval_nested_item_id_rejected_and_clean_fields_persist(self):
        from app.services.rehabilitation_service import RehabilitationService
        from app.schemas.rehabilitation import GeneratedPlanEdits
        rehab = RehabilitationService(self.db)
        draft = {"patient_id": PATIENT_ID, "status": "draft", "name": "synthetic",
                 "generation_source": "llm", "content_revision": 0,
                 "updated_at": datetime.utcnow(),
                 "metadata": {"generated_by": "llm", "approval_history": []}}
        result = await self.db.rehab_plans.insert_one(draft)
        plan_id = str(result.inserted_id)
        # 嵌套处方项携带 _id：schema 白名单直接 422，绝不进入 $set
        with self.assertRaises(ValidationError):
            GeneratedPlanEdits(exercises=[{"_id": str(ObjectId()), "name": "x"}])
        stored_before = await self.db.rehab_plans.find_one({"_id": result.inserted_id})
        self.assertEqual(stored_before["status"], "draft")
        # 白名单字段审核后正常落库，且存储文档的 exercises 无 _id 键
        approved = await rehab.approve_generated_plan(
            plan_id,
            GeneratedPlanEdits(exercises=[{"exercise_id": "ex-1", "name": "合成动作",
                                           "schedule": {"sets": 3, "reps": 10}}]),
            approved_by=OPERATOR_ID, patient_id=PATIENT_ID)
        self.assertEqual(approved["status"], "active")
        stored = await self.db.rehab_plans.find_one({"_id": result.inserted_id})
        for exercise in stored["exercises"]:
            self.assertNotIn("_id", exercise)
        self.assertEqual(stored["exercises"][0]["exercise_id"], "ex-1")
