"""随访服务契约测试（FU01 S2：FollowupService 唯一随访服务入口）。

覆盖从 HealthRecordService 拆出的随访方法组（原 test_health_record_service_contract.py
随访用例随域拆分迁入），并新增 S2 语义修正用例：

1. 创建/更新随访：description -> notes、related_records -> health_record_ids 映射；
   FU01 S1 起扩展数据写顶层正式字段，不再经 metadata.* 缝合；
2. complete / cancel / reschedule：cancel_reason 等第二代语义正确；
3. FU01 S2 取消/改期语义修正（设计稿 §2.2）：cancel(reschedule_date) 原节点一律
   canceled（拼写归一，不再改写为 rescheduled）、新建节点 previous_visit_id 关联、
   原节点回写 next_follow_up_id / next_visit_id；
4. FU01 S1 兼容：正式字段读回不报错、存量文档 metadata.* 回退、FollowUpRecordDB
   校验、list / upcoming / provider 维度列表。

不连接真实数据库：集合用内存 FakeCollection 打桩，并用 bson.encode 验证落库文档
可被 BSON 序列化。
"""

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from bson import ObjectId, encode
from followup_transaction_fake import FakeTransactionalDatabase

from app.models.health_record import FollowUpRecord
from app.schemas.followup import (
    FollowUpAnswer,
    FollowUpQuestion,
    FollowUpRecordCreate,
    FollowUpRecordDB,
    FollowUpRecordUpdate,
    FollowUpStatus,
    CancelFollowUpRequest,
    CompleteFollowUpRequest,
    RescheduleFollowUpRequest,
    ReviewDecision,
    ReviewFollowUpRequest,
    ReEvaluateFollowUpRequest,
)
from app.services.followup_service import FollowupService, select_effective_response
from app.core.exceptions import AppBaseException

PATIENT_ID = str(ObjectId())
DOCTOR_ID = str(ObjectId())


def _match(doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
    """极简 Mongo 查询匹配：等值 / $ne / $in / $gte / $lte，列表字段包含匹配。"""
    for key, cond in query.items():
        actual = doc.get(key)
        if isinstance(cond, dict) and cond and all(k.startswith("$") for k in cond):
            for op, val in cond.items():
                if op == "$ne" and actual == val:
                    return False
                if op == "$in" and actual not in val:
                    return False
                if op == "$gte" and (actual is None or actual < val):
                    return False
                if op == "$lte" and (actual is None or actual > val):
                    return False
        elif isinstance(actual, list):
            if cond not in actual:
                return False
        elif actual != cond:
            return False
    return True


class FakeCursor:
    """模拟 motor 协程游标的链式排序/分页接口。"""

    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = list(docs)

    def sort(self, *args, **kwargs):
        return self

    def skip(self, n: int):
        self._docs = self._docs[n:]
        return self

    def limit(self, n: int):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, length: Optional[int] = None):
        return list(self._docs[:length] if length is not None else self._docs)


class FakeCollection:
    """内存集合打桩：记录落库文档，供断言与 bson.encode 校验。"""

    def __init__(self):
        self.docs: Dict[Any, Dict[str, Any]] = {}

    async def insert_one(self, doc: Dict[str, Any], **kwargs):
        doc = dict(doc)
        _id = doc.get("_id") or ObjectId()
        doc["_id"] = _id
        self.docs[_id] = doc
        return SimpleNamespace(inserted_id=_id)

    async def find_one(self, query: Dict[str, Any], *args, **kwargs):
        for doc in self.docs.values():
            if _match(doc, query):
                return dict(doc)
        return None

    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any], **kwargs):
        modified = 0
        for _id, doc in self.docs.items():
            if _match(doc, query):
                self._apply_set(doc, update.get("$set", {}))
                for key, value in update.get("$inc", {}).items():
                    doc[key] = doc.get(key, 0) + value
                self.docs[_id] = doc
                modified += 1
        return SimpleNamespace(modified_count=modified, matched_count=modified)

    async def replace_one(self, query: Dict[str, Any], doc: Dict[str, Any]):
        for _id in list(self.docs):
            if _match(self.docs[_id], query):
                self.docs[_id] = dict(doc)
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)

    async def count_documents(self, query: Dict[str, Any]):
        return sum(1 for doc in self.docs.values() if _match(doc, query))

    def find(self, query: Dict[str, Any]):
        return FakeCursor([dict(d) for d in self.docs.values() if _match(d, query)])

    def aggregate(self, pipeline: List[Dict[str, Any]]):
        return FakeCursor([])

    @staticmethod
    def _apply_set(doc: Dict[str, Any], set_data: Dict[str, Any]):
        for key, value in set_data.items():
            # 支持 "metadata.status" 等点号路径
            parts = key.split(".")
            target = doc
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = value


def _make_service():
    # audit_logs：FU01 S5 起手工录入/审阅在同一事务写审计，需要预置该集合
    collections = {name: FakeCollection() for name in (
        FollowUpRecord.collection_name, "medical_timelines", "audit_logs",
        "integration_fill_tasks",
    )}
    service = FollowupService(FakeTransactionalDatabase(collections))
    return service, collections


class FollowupServiceContractTests(unittest.IsolatedAsyncioTestCase):
    """按生效（第二代）schema 直测 FollowupService 契约。"""

    async def asyncSetUp(self):
        self.service, self.collections = _make_service()
        self.followup_records = self.collections[FollowUpRecord.collection_name]
        self.timelines = self.collections["medical_timelines"]

    async def _seed_followup(self) -> str:
        seed = FollowUpRecord(
            patient_id=PATIENT_ID, created_by=DOCTOR_ID,
            follow_up_type="in_person",
            scheduled_date=datetime.utcnow() + timedelta(days=2),
            notes="待随访")
        seed_doc = seed.to_mongo()
        self.followup_records.docs[seed_doc["_id"]] = seed_doc
        return str(seed_doc["_id"])

    async def test_invalid_ids_are_treated_as_missing_by_all_node_operations(self):
        invalid_id = "not-an-object-id"
        operations = (
            self.service.get_followup_record(invalid_id),
            self.service.update_followup_record(invalid_id, FollowUpRecordUpdate()),
            self.service.complete_followup(invalid_id, CompleteFollowUpRequest(expected_version=0)),
            self.service.cancel_followup(invalid_id, CancelFollowUpRequest(cancel_reason="test")),
            self.service.reschedule_followup(
                invalid_id, RescheduleFollowUpRequest(new_date=datetime.utcnow(), reason="test")),
        )
        for operation in operations:
            self.assertIsNone(await operation)
        self.assertEqual(self.followup_records.docs, {})
        self.assertEqual(self.timelines.docs, {})

    async def test_declared_soft_delete_fields_are_readable(self):
        followup_id = await self._seed_followup()
        doc = self.followup_records.docs[ObjectId(followup_id)]
        doc.update(deleted=False, deleted_at=None, deleted_by=None)
        response = await self.service.get_followup_record(followup_id)
        self.assertEqual(response.id, followup_id)

    # -------- 创建 / 更新随访记录 --------

    async def test_create_followup_record_maps_effective_fields(self):
        followup_data = FollowUpRecordCreate(
            patient_id=PATIENT_ID,
            provider_id=DOCTOR_ID,
            follow_up_type="phone",
            scheduled_date=datetime.utcnow() + timedelta(days=1),
            description="术后两周电话随访",
            questions=[FollowUpQuestion(question_id="q1", question_text="恢复如何",
                                        question_type="text", order=1)],
            related_records=[str(ObjectId())],
            template_id="tpl-009",
            reminder_before=15,
        )

        response = await self.service.create_followup_record(followup_data)

        self.assertEqual(response.patient_id, PATIENT_ID)
        self.assertEqual(response.provider_id, DOCTOR_ID)
        self.assertEqual(response.description, "术后两周电话随访")
        self.assertEqual(response.template_id, "tpl-009")
        self.assertEqual(response.reminder_before, 15)

        self.assertEqual(len(self.followup_records.docs), 1)
        doc = next(iter(self.followup_records.docs.values()))
        encode(doc)  # questions 已转 dict，文档可序列化
        # description -> 存储字段 notes、related_records -> 存储字段 health_record_ids
        self.assertEqual(doc["notes"], "术后两周电话随访")
        self.assertEqual(doc["health_record_ids"], followup_data.related_records)
        # FU01 S1：扩展数据落顶层正式字段，停止 metadata.* 缝合
        self.assertEqual(doc["provider_id"], DOCTOR_ID)
        self.assertEqual(doc["template_id"], "tpl-009")
        self.assertEqual(doc["reminder_before"], 15)
        self.assertNotIn("provider_id", doc.get("metadata", {}))
        self.assertNotIn("template_id", doc.get("metadata", {}))

    async def test_update_followup_record_maps_effective_fields(self):
        seed = FollowUpRecord(
            patient_id=PATIENT_ID, created_by=DOCTOR_ID,
            follow_up_type="phone",
            scheduled_date=datetime.utcnow() + timedelta(days=1),
            notes="旧描述")
        seed_doc = seed.to_mongo()
        followup_id = str(seed_doc["_id"])
        self.followup_records.docs[seed_doc["_id"]] = seed_doc

        followup_data = FollowUpRecordUpdate(
            description="新描述",
            related_records=[str(ObjectId())],
            provider_id=DOCTOR_ID,
            reminder_before=30,
        )

        response = await self.service.update_followup_record(followup_id, followup_data)

        self.assertIsNotNone(response)
        doc = self.followup_records.docs[ObjectId(followup_id)]
        self.assertEqual(doc["notes"], "新描述")
        self.assertEqual(doc["health_record_ids"], followup_data.related_records)
        self.assertEqual(doc["provider_id"], DOCTOR_ID)
        self.assertEqual(doc["reminder_before"], 30)

    # -------- complete / cancel / reschedule 随访 --------

    async def test_complete_followup_converts_answers_and_sets_completion(self):
        """FU01 S5（D-2 默认决策）：complete 降级为手工录入——节点转 in_review
        而非 completed，带显式 source=manual_entry 标记并写审计。"""
        followup_id = await self._seed_followup()
        actual_date = datetime.utcnow() - timedelta(hours=1)
        data = CompleteFollowUpRequest(expected_version=0,
            actual_date=actual_date,
            answers=[FollowUpAnswer(question_id="q1", answer_value=8, answer_text="恢复较好")],
            notes="随访完成，恢复良好",
            follow_up_result="completed",
        )

        response = await self.service.complete_followup(followup_id, data, operator_id=DOCTOR_ID)

        self.assertIsNotNone(response)
        # D-2：手工录入只转待审阅，completed 只能由审阅通过置达
        self.assertEqual(response.status, FollowUpStatus.IN_REVIEW)
        doc = self.followup_records.docs[ObjectId(followup_id)]
        encode(doc)  # answers 已转 dict，文档可序列化
        self.assertEqual(doc["status"], "in_review")
        self.assertEqual(doc["actual_date"], actual_date)
        self.assertIsInstance(doc["answers"][0], dict)
        self.assertEqual(doc["answers"][0]["question_id"], "q1")
        self.assertEqual(doc["answers"][0]["answer_value"], 8)
        # FU01 S1：完成数据落顶层正式字段，停止 metadata.completion_data / metadata.result
        self.assertEqual(doc["completion_data"]["result"], "completed")
        self.assertEqual(doc["completion_data"]["notes"], "随访完成，恢复良好")
        # D-2：显式 source 标记，区别于外部表单填报
        self.assertEqual(doc["completion_data"]["source"], "manual_entry")
        self.assertEqual(doc["follow_up_result"], "completed")
        self.assertNotIn("completion_data", doc.get("metadata", {}))
        self.assertNotIn("result", doc.get("metadata", {}))
        self.assertEqual(doc["notes"], "随访完成，恢复良好")
        # D-2：手工录入不允许冒充表单答卷状态——不写 effective_response / fill_task_ids
        self.assertIsNone(doc.get("effective_response"))
        self.assertNotIn("fill_task_ids", doc)
        # D-2：同一事务写审计
        audit_docs = list(self.collections["audit_logs"].docs.values())
        self.assertEqual(len(audit_docs), 1)
        self.assertEqual(audit_docs[0]["action"], "followup_manual_entry")
        self.assertEqual(audit_docs[0]["resource_id"], followup_id)
        self.assertEqual(audit_docs[0]["user_id"], DOCTOR_ID)
        self.assertEqual(audit_docs[0]["details"]["source"], "manual_entry")

    async def test_complete_followup_creates_next_followup(self):
        followup_id = await self._seed_followup()
        data = CompleteFollowUpRequest(expected_version=0,
            next_follow_up_date=datetime.utcnow() + timedelta(days=7),
        )

        await self.service.complete_followup(followup_id, data)

        self.assertEqual(len(self.followup_records.docs), 2)
        original = self.followup_records.docs[ObjectId(followup_id)]
        new_docs = [d for _id, d in self.followup_records.docs.items()
                    if str(_id) != followup_id]
        self.assertEqual(len(new_docs), 1)
        # FU01 S1：next_follow_up_id 落顶层正式字段
        self.assertEqual(original["next_follow_up_id"], str(new_docs[0]["_id"]))
        encode(new_docs[0])

    async def test_cancel_followup_records_cancel_reason(self):
        followup_id = await self._seed_followup()
        data = CancelFollowUpRequest(
            cancel_reason="患者临时有事",
            canceled_by=DOCTOR_ID,
        )

        response = await self.service.cancel_followup(followup_id, data)

        self.assertIsNotNone(response)
        self.assertEqual(response.status, FollowUpStatus.CANCELED)
        doc = self.followup_records.docs[ObjectId(followup_id)]
        encode(doc)
        self.assertEqual(doc["status"], "canceled")
        # FU01 S1：取消数据落顶层正式字段，停止 metadata.cancellation_data
        self.assertEqual(doc["cancellation_data"]["reason"], "患者临时有事")
        self.assertEqual(doc["cancellation_data"]["canceled_by"], DOCTOR_ID)
        self.assertNotIn("cancellation_data", doc.get("metadata", {}))
        self.assertIn("已取消", doc["notes"])

    # -------- FU01 S2：取消/改期语义修正（设计稿 §2.2） --------

    async def test_cancel_with_reschedule_keeps_original_canceled(self):
        """cancel(reschedule_date)：原节点一律 canceled，不再改写为 rescheduled。"""
        followup_id = await self._seed_followup()
        data = CancelFollowUpRequest(
            cancel_reason="医生出差",
            canceled_by=DOCTOR_ID,
            reschedule_date=datetime.utcnow() + timedelta(days=3),
        )

        response = await self.service.cancel_followup(followup_id, data)

        self.assertIsNotNone(response)
        self.assertEqual(response.status, FollowUpStatus.CANCELED)
        doc = self.followup_records.docs[ObjectId(followup_id)]
        encode(doc)
        # 原缺陷（models.cancel_followup 带 reschedule_date 时改写 rescheduled）已修正
        self.assertEqual(doc["status"], "canceled")
        self.assertNotEqual(doc["status"], "rescheduled")

    async def test_cancel_with_reschedule_creates_new_node_with_previous_link(self):
        """cancel(reschedule_date)：新建节点且 previous_visit_id 关联原节点。"""
        followup_id = await self._seed_followup()
        reschedule_date = datetime.utcnow() + timedelta(days=3)
        data = CancelFollowUpRequest(
            cancel_reason="医生出差",
            canceled_by=DOCTOR_ID,
            reschedule_date=reschedule_date,
        )

        await self.service.cancel_followup(followup_id, data)

        self.assertEqual(len(self.followup_records.docs), 2)
        original = self.followup_records.docs[ObjectId(followup_id)]
        new_docs = [d for _id, d in self.followup_records.docs.items()
                    if str(_id) != followup_id]
        self.assertEqual(len(new_docs), 1)
        new_doc = new_docs[0]
        encode(new_doc)
        # 新节点：新排期、scheduled 起点语义、携带取消原因
        self.assertEqual(new_doc["scheduled_date"], reschedule_date)
        self.assertEqual(new_doc["status"], "scheduled")
        self.assertIn("医生出差", new_doc["notes"])
        # §2.2 复评链：新节点 previous_visit_id -> 原节点
        self.assertEqual(str(new_doc["previous_visit_id"]), followup_id)
        # 原节点回写链后继（next_follow_up_id 兼容字段 + next_visit_id 节点字段）
        new_id = str(new_doc["_id"])
        self.assertEqual(original["next_follow_up_id"], new_id)
        self.assertEqual(original["next_visit_id"], new_id)
        # 新节点时间线同步创建
        # 即使原节点缺历史时间线，也在同一事务补建原节点和新节点时间线。
        self.assertEqual(len(self.timelines.docs), 2)

    async def test_cancel_without_reschedule_creates_no_new_node(self):
        """纯取消不产生新节点，也不写链后继。"""
        followup_id = await self._seed_followup()
        data = CancelFollowUpRequest(cancel_reason="患者放弃随访", canceled_by=DOCTOR_ID)

        await self.service.cancel_followup(followup_id, data)

        self.assertEqual(len(self.followup_records.docs), 1)
        doc = self.followup_records.docs[ObjectId(followup_id)]
        self.assertEqual(doc["status"], "canceled")
        self.assertIsNone(doc.get("next_follow_up_id"))
        self.assertIsNone(doc.get("next_visit_id"))

    async def test_model_cancel_followup_normalizes_spelling_and_never_reschedules(self):
        """存储模型 cancel_followup：拼写归一 canceled；无 reschedule_date 参数可改写状态。"""
        record = FollowUpRecord(
            patient_id=PATIENT_ID, created_by=DOCTOR_ID,
            follow_up_type="phone",
            scheduled_date=datetime.utcnow() + timedelta(days=1))
        record.cancel_followup(reason="测试取消")
        self.assertEqual(record.status, "canceled")

    async def test_reschedule_followup_updates_schedule_and_reason(self):
        followup_id = await self._seed_followup()
        new_date = datetime.utcnow() + timedelta(days=5)
        data = RescheduleFollowUpRequest(new_date=new_date, reason="医生临时有事")

        response = await self.service.reschedule_followup(followup_id, data)

        self.assertIsNotNone(response)
        doc = self.followup_records.docs[ObjectId(followup_id)]
        encode(doc)
        self.assertEqual(doc["status"], "rescheduled")
        self.assertEqual(doc["scheduled_date"], new_date)
        self.assertEqual(doc["metadata"]["reschedule_reason"], "医生临时有事")

    async def test_reschedule_retry_cannot_succeed_after_node_is_canceled(self):
        followup_id = await self._seed_followup()
        request = RescheduleFollowUpRequest(new_date=datetime.utcnow() + timedelta(days=3), reason="test")
        await self.service.reschedule_followup(followup_id, request)
        await self.service.cancel_followup(followup_id, CancelFollowUpRequest(cancel_reason="cancel"))
        with self.assertRaises(AppBaseException) as error:
            await self.service.reschedule_followup(followup_id, request)
        self.assertEqual(error.exception.status_code, 409)

    async def test_reschedule_retry_after_intervening_date_change_applies_requested_date(self):
        followup_id = await self._seed_followup()
        request = RescheduleFollowUpRequest(new_date=datetime.utcnow() + timedelta(days=3), reason="test")
        await self.service.reschedule_followup(followup_id, request)
        await self.service.update_followup_record(followup_id, FollowUpRecordUpdate(scheduled_date=datetime.utcnow()))
        response = await self.service.reschedule_followup(followup_id, request)
        self.assertEqual(response.scheduled_date, request.new_date)

    async def test_authorized_scope_applies_before_pagination_and_empty_scope_denies(self):
        allowed = PATIENT_ID
        for patient in [str(ObjectId()), allowed, allowed]:
            doc = FollowUpRecord(patient_id=patient, created_by=DOCTOR_ID,
                scheduled_date=datetime.utcnow() + timedelta(days=1), notes="scope").to_mongo()
            self.followup_records.docs[doc["_id"]] = doc
        for method in [self.service.list_all_followups,
                       lambda **kwargs: self.service.list_followups_for_provider(DOCTOR_ID, **kwargs)]:
            rows = await method(patient_ids=[allowed], skip=1, limit=1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].patient_id, allowed)
            self.assertEqual(await method(patient_ids=[]), [])
        self.assertEqual(await self.service.get_upcoming_followups(patient_ids=[]), [])
        self.assertEqual(len(await self.service.get_upcoming_followups(patient_ids=[allowed])), 2)
        self.assertEqual(await self.service.list_all_followups(patient_id=allowed, patient_ids=[]), [])
        self.assertEqual(await self.service.get_upcoming_followups(patient_id=allowed, patient_ids=[]), [])

    # -------- FU01 S1：正式字段读回 / metadata.* 回退 / list·upcoming·provider --------

    async def test_formal_fields_read_back_without_error(self):
        """正式字段落顶层后，服务层 from_mongo 读回路径不报错且映射正确。"""
        doc = FollowUpRecord(
            patient_id=PATIENT_ID, created_by=DOCTOR_ID,
            follow_up_type="phone",
            scheduled_date=datetime.utcnow() + timedelta(days=2),
            notes="待随访").to_mongo()
        completion = {"completed_at": datetime.utcnow(), "result": "improved", "notes": "恢复良好"}
        doc.update({
            "provider_id": DOCTOR_ID,
            "template_id": "tpl-009",
            "reminder_before": 45,
            "completion_data": completion,
            "follow_up_result": "improved",
            "next_follow_up_id": str(ObjectId()),
        })
        self.followup_records.docs[doc["_id"]] = doc
        followup_id = str(doc["_id"])

        response = await self.service.get_followup_record(followup_id)

        self.assertIsNotNone(response)
        self.assertEqual(response.provider_id, DOCTOR_ID)
        self.assertEqual(response.template_id, "tpl-009")
        self.assertEqual(response.reminder_before, 45)
        self.assertEqual(response.completion_data, completion)
        self.assertEqual(response.follow_up_result, "improved")
        self.assertEqual(response.next_follow_up_id, doc["next_follow_up_id"])

    async def test_legacy_metadata_fields_still_map_with_fallback(self):
        """存量文档（e7e8706 缝合层约定 metadata.*，无顶层正式字段）读取回退仍生效。"""
        next_id = str(ObjectId())
        doc = FollowUpRecord(
            patient_id=PATIENT_ID, created_by=DOCTOR_ID,
            follow_up_type="phone",
            scheduled_date=datetime.utcnow() + timedelta(days=1),
            notes="存量随访").to_mongo()
        doc["metadata"] = {
            "provider_id": DOCTOR_ID,
            "template_id": "tpl-legacy",
            "reminder_before": 20,
            "result": "legacy-result",
            "next_follow_up_id": next_id,
            "completion_data": {"result": "legacy-result"},
            "cancellation_data": {"reason": "legacy-cancel"},
        }
        self.followup_records.docs[doc["_id"]] = doc
        followup_id = str(doc["_id"])

        response = await self.service.get_followup_record(followup_id)

        self.assertIsNotNone(response)
        self.assertEqual(response.provider_id, DOCTOR_ID)
        self.assertEqual(response.template_id, "tpl-legacy")
        self.assertEqual(response.reminder_before, 20)
        self.assertEqual(response.follow_up_result, "legacy-result")
        self.assertEqual(response.next_follow_up_id, next_id)
        self.assertEqual(response.completion_data, {"result": "legacy-result"})
        self.assertEqual(response.cancellation_data, {"reason": "legacy-cancel"})

    async def test_followup_record_db_validates_service_document_shape(self):
        """FollowUpRecordDB 可直接校验服务层落库文档（新写入与存量 metadata 两种形状）。"""
        scheduled = datetime.utcnow() + timedelta(days=1)
        service_doc = FollowUpRecord(
            patient_id=PATIENT_ID, created_by=DOCTOR_ID,
            follow_up_type="phone", scheduled_date=scheduled, notes="描述",
            questions=[{"question_id": "q1", "question_text": "恢复如何",
                        "question_type": "text", "order": 1}]).to_mongo()
        service_doc.update({
            "provider_id": DOCTOR_ID, "template_id": "tpl-001",
            "reminder_before": 30, "status": "scheduled",
        })

        model = FollowUpRecordDB.model_validate(service_doc)
        self.assertEqual(model.provider_id, DOCTOR_ID)
        self.assertEqual(model.template_id, "tpl-001")
        self.assertEqual(model.reminder_before, 30)
        self.assertIsNone(model.completion_data)

        legacy_doc = FollowUpRecord(
            patient_id=PATIENT_ID, created_by=DOCTOR_ID,
            follow_up_type="phone", scheduled_date=scheduled, notes="存量").to_mongo()
        legacy_doc["metadata"] = {"provider_id": DOCTOR_ID, "completion_data": {"result": "ok"}}

        legacy_model = FollowUpRecordDB.model_validate(legacy_doc)
        # 存量文档无顶层正式字段（免回填），DB 模型全部 Optional 不报错
        self.assertIsNone(legacy_model.provider_id)
        self.assertIsNone(legacy_model.description)  # 存储字段为 notes
        self.assertEqual(legacy_model.notes, "存量")

    async def test_list_and_upcoming_and_provider_views_read_formal_fields(self):
        """list / upcoming / provider 维度列表：正式字段文档读回不报错且映射正确。"""
        formal_doc = FollowUpRecord(
            patient_id=PATIENT_ID, created_by=DOCTOR_ID,
            follow_up_type="phone",
            scheduled_date=datetime.utcnow() + timedelta(days=1),
            notes="即将到来").to_mongo()
        formal_doc["provider_id"] = DOCTOR_ID
        formal_doc["template_id"] = "tpl-100"
        other_doc = FollowUpRecord(
            patient_id=str(ObjectId()), created_by=DOCTOR_ID,
            follow_up_type="phone",
            scheduled_date=datetime.utcnow() + timedelta(days=1),
            notes="其他患者").to_mongo()
        self.followup_records.docs[formal_doc["_id"]] = formal_doc
        self.followup_records.docs[other_doc["_id"]] = other_doc

        listed = await self.service.list_followup_records(PATIENT_ID)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].id, str(formal_doc["_id"]))
        self.assertEqual(listed[0].provider_id, DOCTOR_ID)
        self.assertEqual(listed[0].template_id, "tpl-100")

        upcoming = await self.service.get_upcoming_followups(patient_id=PATIENT_ID)
        self.assertEqual(len(upcoming), 1)
        self.assertEqual(upcoming[0].id, str(formal_doc["_id"]))

        # doctor_router GET /follow-ups 的转调入口（created_by 维度）
        for_provider = await self.service.list_followups_for_provider(DOCTOR_ID)
        self.assertEqual(len(for_provider), 2)
        for_provider_status = await self.service.list_followups_for_provider(
            DOCTOR_ID, status="scheduled")
        self.assertEqual(len(for_provider_status), 2)

        # health_manager_router GET /follow-ups 的转调入口（全量/患者过滤）
        all_followups = await self.service.list_all_followups()
        self.assertEqual(len(all_followups), 2)
        by_patient = await self.service.list_all_followups(patient_id=PATIENT_ID)
        self.assertEqual(len(by_patient), 1)
        self.assertEqual(by_patient[0].patient_id, PATIENT_ID)

    async def test_count_upcoming_for_stats(self):
        """count_upcoming：健康档案统计域转调入口。"""
        doc = FollowUpRecord(
            patient_id=PATIENT_ID, created_by=DOCTOR_ID,
            follow_up_type="phone",
            scheduled_date=datetime.utcnow() + timedelta(days=1),
            notes="未来随访").to_mongo()
        self.followup_records.docs[doc["_id"]] = doc

        count = await self.service.count_upcoming(PATIENT_ID, since=datetime.utcnow())
        self.assertEqual(count, 1)
        other = await self.service.count_upcoming(str(ObjectId()), since=datetime.utcnow())
        self.assertEqual(other, 0)

    # -------- FU01 S5：医护审阅与证据链（设计稿 §4.3，D-2 默认决策） --------

    async def _seed_with_status(self, status, **extra):
        """按指定状态直接落库一个节点（绕过状态机，模拟已发生的上游流转）。"""
        doc = FollowUpRecord(
            patient_id=PATIENT_ID, created_by=DOCTOR_ID,
            follow_up_type="phone",
            scheduled_date=datetime.utcnow() + timedelta(days=1),
            notes="待审阅随访").to_mongo()
        doc.update(status=status, provider_id=DOCTOR_ID)
        if status == "in_review" and "effective_response" not in extra:
            doc["completion_data"] = {"source": "manual_entry", "result": "synthetic legacy result"}
        doc.update(extra)
        self.followup_records.docs[doc["_id"]] = doc
        return str(doc["_id"])

    def _audit_docs(self):
        return list(self.collections["audit_logs"].docs.values())

    async def test_completed_is_only_reachable_through_review_approval(self):
        """S5 验收：completed 只能由审阅通过产生——手工录入后无法直达 completed。"""
        followup_id = await self._seed_followup()
        await self.service.complete_followup(followup_id, CompleteFollowUpRequest(expected_version=0))
        self.assertEqual(
            self.followup_records.docs[ObjectId(followup_id)]["status"], "in_review")
        # 换内容再录入（新指纹）→ 已是 in_review 仍允许录入，但不直达 completed
        response = await self.service.complete_followup(
            followup_id,
            CompleteFollowUpRequest(expected_version=1, notes="补充记录", follow_up_result="stable"))
        self.assertEqual(response.status, FollowUpStatus.IN_REVIEW)

    async def test_review_approval_completes_node_with_evidence_chain(self):
        """approved：completed + actual_date=reviewed_at，review.history[] 全链可追溯。"""
        followup_id = await self._seed_with_status("in_review")
        evidence = {"task_id": str(ObjectId()), "response_id": "resp-1", "revision": 1}
        data = ReviewFollowUpRequest(expected_version=0, decision=ReviewDecision.APPROVED,
                                     comment="恢复良好", evidence=evidence)

        response = await self.service.review_followup(
            followup_id, data, reviewer_id=DOCTOR_ID, reviewer_role="doctor")

        self.assertEqual(response.status, FollowUpStatus.COMPLETED)
        self.assertIsNotNone(response.actual_date)
        doc = self.followup_records.docs[ObjectId(followup_id)]
        encode(doc)
        self.assertEqual(doc["status"], "completed")
        review = doc["review"]
        self.assertEqual(review["decision"], "approved")
        self.assertEqual(review["reviewer_id"], DOCTOR_ID)
        self.assertEqual(len(review["history"]), 1)
        entry = review["history"][0]
        self.assertEqual(entry["decision"], "approved")
        self.assertEqual(entry["reviewer_id"], DOCTOR_ID)
        self.assertEqual(entry["reviewer_role"], "doctor")
        self.assertEqual(entry["evidence"], evidence)
        self.assertIn("reviewed_at", entry)
        # 表单路径的有效答卷在审阅通过后保留
        self.assertEqual(len(self._audit_docs()), 1)
        self.assertEqual(self._audit_docs()[0]["action"], "followup_review")

    async def test_review_approval_keeps_effective_response_from_form_task(self):
        """approved：表单答卷的 effective_response 保留（证据链不丢）。"""
        effective = {"task_id": str(ObjectId()), "response_id": "resp-1"}
        followup_id = await self._seed_with_status("in_review", effective_response=effective)
        await self.collections["integration_fill_tasks"].insert_one({
            "_id": ObjectId(effective["task_id"]), "status": "confirmed", "patient_id": PATIENT_ID,
            "followup_visit_id": followup_id,
            "confirmation": {"response_id": "resp-1", "remote_status": "submitted", "answers": []}})
        await self.service.review_followup(
            followup_id, ReviewFollowUpRequest(expected_version=0, decision=ReviewDecision.APPROVED),
            reviewer_id=DOCTOR_ID)
        doc = self.followup_records.docs[ObjectId(followup_id)]
        self.assertEqual(doc["effective_response"], effective)

    async def test_review_returned_sets_awaiting_fill_and_clears_effective_response(self):
        """returned：节点回 awaiting_fill、清除 effective_response（旧任务保持终态），
        历史留痕于 review.history[]。"""
        effective = {"task_id": str(ObjectId()), "response_id": "resp-1"}
        followup_id = await self._seed_with_status(
            "in_review", effective_response=effective,
            fill_task_ids=[ObjectId(effective["task_id"])])
        data = ReviewFollowUpRequest(expected_version=0, decision=ReviewDecision.RETURNED,
                                     comment="答案不完整，需重新填报")

        response = await self.service.review_followup(
            followup_id, data, reviewer_id=DOCTOR_ID)

        self.assertEqual(response.status, FollowUpStatus.AWAITING_FILL)
        doc = self.followup_records.docs[ObjectId(followup_id)]
        encode(doc)
        self.assertEqual(doc["status"], "awaiting_fill")
        self.assertIsNone(doc.get("effective_response"))
        # 旧任务保持 confirmed 终态：节点仍保留任务反向索引，需新建任务重填
        self.assertEqual([str(t) for t in doc["fill_task_ids"]], [effective["task_id"]])
        self.assertEqual(doc["review"]["history"][0]["decision"], "returned")

    async def test_review_requires_in_review_status(self):
        """非 in_review 节点拒绝审阅（scheduled/completed 均冲突 409）。"""
        for status in ("scheduled", "completed", "canceled"):
            followup_id = await self._seed_with_status(status)
            with self.subTest(status=status):
                with self.assertRaises(AppBaseException) as error:
                    await self.service.review_followup(
                        followup_id, ReviewFollowUpRequest(expected_version=0, decision=ReviewDecision.APPROVED),
                        reviewer_id=DOCTOR_ID)
                self.assertEqual(error.exception.status_code, 409)

    async def test_review_reviewer_must_be_provider_or_admin(self):
        """审阅人必须是责任医护本人或 admin；其他医护 403。"""
        followup_id = await self._seed_with_status("in_review")
        with self.assertRaises(AppBaseException) as error:
            await self.service.review_followup(
                followup_id, ReviewFollowUpRequest(expected_version=0, decision=ReviewDecision.APPROVED),
                reviewer_id=str(ObjectId()), reviewer_role="doctor")
        self.assertEqual(error.exception.status_code, 403)
        # admin 可审阅
        response = await self.service.review_followup(
            followup_id, ReviewFollowUpRequest(expected_version=0, decision=ReviewDecision.APPROVED),
            reviewer_id=str(ObjectId()), reviewer_role="admin")
        self.assertEqual(response.status, FollowUpStatus.COMPLETED)

    async def test_review_idempotent_retry_does_not_duplicate_history(self):
        """相同审阅请求重试返回当前节点，不追加 history、不重复审计。"""
        followup_id = await self._seed_with_status("in_review")
        data = ReviewFollowUpRequest(expected_version=0, decision=ReviewDecision.APPROVED, comment="ok")
        first = await self.service.review_followup(followup_id, data, reviewer_id=DOCTOR_ID)
        retry = await self.service.review_followup(followup_id, data, reviewer_id=DOCTOR_ID)
        self.assertEqual(retry.status, first.status)
        doc = self.followup_records.docs[ObjectId(followup_id)]
        self.assertEqual(len(doc["review"]["history"]), 1)
        self.assertEqual(len(self._audit_docs()), 1)

    async def test_manual_entry_review_full_flow(self):
        """端到端：手工录入 → in_review（带 manual_entry 标记）→ 审阅通过 → completed。"""
        followup_id = await self._seed_followup()
        await self.service.complete_followup(
            followup_id, CompleteFollowUpRequest(expected_version=0, notes="电话随访结果"), operator_id=DOCTOR_ID)
        doc = self.followup_records.docs[ObjectId(followup_id)]
        self.assertEqual(doc["status"], "in_review")
        self.assertEqual(doc["completion_data"]["source"], "manual_entry")
        response = await self.service.review_followup(
            followup_id, ReviewFollowUpRequest(expected_version=1, decision=ReviewDecision.APPROVED,
                                               comment="录入结果已核实"),
            reviewer_id=DOCTOR_ID)
        self.assertEqual(response.status, FollowUpStatus.COMPLETED)
        # 录入来源标记保留，审阅证据链与手工录入审计并存
        doc = self.followup_records.docs[ObjectId(followup_id)]
        self.assertEqual(doc["completion_data"]["source"], "manual_entry")
        self.assertEqual(doc["review"]["decision"], "approved")
        actions = {a["action"] for a in self._audit_docs()}
        self.assertEqual(actions, {"followup_manual_entry", "followup_review"})

    async def test_return_resubmit_same_content_uses_new_version_and_preserves_history(self):
        followup_id = await self._seed_followup()
        initial = await self.service.get_followup_record(followup_id)
        self.assertEqual(initial.mutation_version, 0)  # historical nodes have no version
        for version in (0, 2):
            entry = CompleteFollowUpRequest(expected_version=version, notes="相同录入")
            submitted = await self.service.complete_followup(followup_id, entry)
            retry = await self.service.complete_followup(followup_id, entry)
            self.assertEqual(submitted.mutation_version, version + 1)
            self.assertEqual(retry.mutation_version, submitted.mutation_version)
            decision = ReviewFollowUpRequest(expected_version=version + 1,
                decision=ReviewDecision.RETURNED, comment="请核实")
            returned = await self.service.review_followup(followup_id, decision, reviewer_id=DOCTOR_ID)
            retried = await self.service.review_followup(followup_id, decision, reviewer_id=DOCTOR_ID)
            self.assertEqual(returned.status, FollowUpStatus.AWAITING_FILL)
            self.assertEqual(retried.mutation_version, version + 2)
            with self.assertRaises(AppBaseException) as stale:
                await self.service.complete_followup(followup_id, entry)
            self.assertEqual(stale.exception.status_code, 409)
        submitted = await self.service.complete_followup(followup_id,
            CompleteFollowUpRequest(expected_version=4, notes="相同录入"))
        approved = await self.service.review_followup(followup_id,
            ReviewFollowUpRequest(expected_version=submitted.mutation_version,
                decision=ReviewDecision.APPROVED), reviewer_id=DOCTOR_ID)
        self.assertEqual(approved.status, FollowUpStatus.COMPLETED)
        history = approved.review["history"]
        self.assertEqual([item["reviewed_version"] for item in history], [1, 3, 5])
        self.assertEqual(len(self._audit_docs()), 6)

    async def test_stale_review_cannot_approve_updated_content_or_replay_across_rounds(self):
        followup_id = await self._seed_with_status("in_review")
        decision = ReviewFollowUpRequest(expected_version=0,
            decision=ReviewDecision.RETURNED, comment="重新录入")
        await self.service.review_followup(followup_id, decision, reviewer_id=DOCTOR_ID)
        await self.service.complete_followup(followup_id,
            CompleteFollowUpRequest(expected_version=1, notes="新内容"))
        with self.assertRaises(AppBaseException) as stale:
            await self.service.review_followup(followup_id, decision, reviewer_id=DOCTOR_ID)
        self.assertEqual(stale.exception.status_code, 409)
        current = await self.service.get_followup_record(followup_id)
        self.assertEqual(current.status, FollowUpStatus.IN_REVIEW)
        await self.service.update_followup_record(followup_id,
            FollowUpRecordUpdate(description="再次变更"))
        with self.assertRaises(AppBaseException) as stale:
            await self.service.review_followup(followup_id,
                ReviewFollowUpRequest(expected_version=current.mutation_version,
                    decision=ReviewDecision.APPROVED), reviewer_id=DOCTOR_ID)
        self.assertEqual(stale.exception.status_code, 409)
        self.assertEqual(len(self._audit_docs()), 2)

    async def test_ambiguous_or_missing_legacy_evidence_cannot_be_approved(self):
        for extra in (
            {"completion_data": None},
            {"completion_data": {"source": "manual_entry", "result": "old"},
             "effective_response": {"task_id": "old-task", "response_id": 1}},
        ):
            followup_id = await self._seed_with_status("in_review", **extra)
            response = await self.service.get_followup_record(followup_id)
            self.assertIn(response.current_evidence["source"], {"unknown", "ambiguous"})
            with self.assertRaises(AppBaseException) as error:
                await self.service.review_followup(followup_id,
                    ReviewFollowUpRequest(expected_version=0, decision=ReviewDecision.APPROVED),
                    reviewer_id=DOCTOR_ID)
            self.assertEqual(error.exception.status_code, 409)
            returned = await self.service.review_followup(followup_id,
                ReviewFollowUpRequest(expected_version=0, decision=ReviewDecision.RETURNED),
                reviewer_id=DOCTOR_ID)
            self.assertIsNone(returned.current_evidence)
            if extra.get("effective_response"):
                self.assertEqual(returned.submission_history[0]["snapshot"]["effective_response"],
                                 extra["effective_response"])

    async def test_manual_submission_clears_old_form_evidence_and_shadows_metadata(self):
        followup_id = await self._seed_with_status("awaiting_fill",
            metadata={"effective_response": {"task_id": "legacy", "response_id": 42}})
        response = await self.service.complete_followup(followup_id,
            CompleteFollowUpRequest(expected_version=0, notes="current"))
        self.assertIsNone(response.effective_response)
        self.assertEqual(response.current_evidence["source"], "manual_entry")
        self.assertEqual(response.submission_history[0]["snapshot"]["effective_response"]["response_id"], 42)
        self.assertEqual(response.submission_history[-1]["snapshot"]["notes"], "current")

    async def test_external_approval_requires_matching_persisted_confirmation(self):
        for override in (
            {"status": "failed"}, {"patient_id": "other"}, {"followup_visit_id": "other"},
            {"confirmation": {"response_id": 43, "remote_status": "submitted"}},
            {"confirmation": {"response_id": 42, "remote_status": "voided"}},
            {"visit_code": "other"}, {},
        ):
            task_id = ObjectId()
            followup_id = await self._seed_with_status("in_review", visit_code="V1",
                effective_response={"task_id": str(task_id), "response_id": 42, "visit_code": "V1"})
            task = {"_id": task_id, "status": "confirmed", "patient_id": PATIENT_ID,
                    "followup_visit_id": followup_id, "visit_code": "V1",
                    "confirmation": {"response_id": 42, "remote_status": "submitted", "visit_code": "V1"}}
            if override:
                task.update(override)
                await self.collections["integration_fill_tasks"].insert_one(task)
            with self.assertRaises(AppBaseException) as error:
                await self.service.review_followup(followup_id,
                    ReviewFollowUpRequest(expected_version=0, decision="approved",
                        evidence={"response_id": 42, "status": "confirmed"}), reviewer_id=DOCTOR_ID)
            self.assertEqual(error.exception.status_code, 409)
            await self.service.review_followup(followup_id,
                ReviewFollowUpRequest(expected_version=0, decision="returned"), reviewer_id=DOCTOR_ID)

    # -------- FU01 S6：复评链与有效答卷（设计稿 §4.4） --------

    async def test_re_evaluate_creates_linked_node_without_overwriting_original(self):
        """复评新建节点：复制处方配置、previous/next 双向关联；原节点除链接
        字段外不覆盖不改写（A06）。"""
        doc = FollowUpRecord(
            patient_id=PATIENT_ID, created_by=DOCTOR_ID,
            follow_up_type="phone",
            scheduled_date=datetime.utcnow() - timedelta(days=7),
            notes="首评随访",
            questions=[{"question_id": "q1", "question_text": "恢复如何",
                        "question_type": "text", "order": 1}],
            answers=[{"question_id": "q1", "answer_value": "良好"}],
            reminder_settings={"enabled": True, "days_before": 1}).to_mongo()
        doc.update(status="completed", provider_id=DOCTOR_ID, template_id="tpl-009",
                   reminder_before=30, form_binding={"questionnaire_id": 7},
                   visit_code="V-001", effective_response={"response_id": "resp-1"},
                   review={"decision": "approved"}, actual_date=datetime.utcnow(),
                   current_evidence={"source": "external_form", "submission_id": "original"},
                   submission_history=[{"submission_id": "original", "source": "external_form",
                                        "snapshot": {"effective_response": {"response_id": "resp-1"}}}])
        before = dict(doc)
        followup_id = str(doc["_id"])
        self.followup_records.docs[doc["_id"]] = doc
        data = ReEvaluateFollowUpRequest(
            scheduled_date=datetime.utcnow() + timedelta(days=14), reason="按计划复评")

        response = await self.service.re_evaluate_followup(
            followup_id, data, operator_id=DOCTOR_ID)

        self.assertIsNotNone(response)
        self.assertEqual(len(self.followup_records.docs), 2)
        child = self.followup_records.docs[ObjectId(response.id)]
        encode(child)
        # 新节点：复评链与处方配置
        self.assertEqual(str(child["previous_visit_id"]), followup_id)
        self.assertEqual(child["status"], "scheduled")
        self.assertEqual(child["scheduled_date"], data.scheduled_date)
        self.assertEqual(child["provider_id"], DOCTOR_ID)
        self.assertEqual(child["template_id"], "tpl-009")
        self.assertEqual(child["reminder_before"], 30)
        self.assertEqual(child["form_binding"], {"questionnaire_id": 7})
        self.assertEqual(child["questions"], before["questions"])
        self.assertEqual(child["follow_up_type"], "phone")
        self.assertIn("复评", child["notes"])
        # visit_code 不继承：同一患者各节点 visit_code 唯一
        self.assertNotIn("visit_code", child)
        # 空状态开始：答案、结果、审阅、任务引用不继承
        self.assertEqual(child["answers"], [])
        self.assertNotIn("effective_response", child)
        self.assertNotIn("review", child)
        self.assertNotIn("current_evidence", child)
        self.assertNotIn("submission_history", child)
        self.assertIsNone(response.current_evidence)
        self.assertEqual(response.submission_history, [])
        # 原节点只写链接字段，其余不覆盖不改写
        original = self.followup_records.docs[ObjectId(followup_id)]
        self.assertEqual(original["next_visit_id"], response.id)
        self.assertEqual(original["next_follow_up_id"], response.id)
        for key in ("status", "provider_id", "template_id", "form_binding",
                    "visit_code", "effective_response", "review", "answers",
                    "scheduled_date", "notes", "reminder_before", "current_evidence", "submission_history"):
            self.assertEqual(original[key], before[key], key)
        # 新节点时间线创建（原节点状态未变，时间线不重写）
        self.assertEqual(len(self.timelines.docs), 1)

    async def test_re_evaluate_retry_returns_same_child(self):
        """相同复评请求重试返回同一后继节点（幂等，不产生分叉）。"""
        followup_id = await self._seed_with_status("completed")
        data = ReEvaluateFollowUpRequest(scheduled_date=datetime.utcnow() + timedelta(days=7))
        first = await self.service.re_evaluate_followup(followup_id, data, operator_id=DOCTOR_ID)
        retry = await self.service.re_evaluate_followup(followup_id, data, operator_id=DOCTOR_ID)
        self.assertEqual(retry.id, first.id)
        self.assertEqual(len(self.followup_records.docs), 2)

    async def test_re_evaluate_conflicts_when_successor_exists(self):
        """已有后继节点（无论何种来源）拒绝再次复评；不同请求并发只成功一个。"""
        followup_id = await self._seed_with_status("completed")
        first = await self.service.re_evaluate_followup(
            followup_id, ReEvaluateFollowUpRequest(
                scheduled_date=datetime.utcnow() + timedelta(days=7)), operator_id=DOCTOR_ID)
        with self.assertRaises(AppBaseException) as error:
            await self.service.re_evaluate_followup(
                followup_id, ReEvaluateFollowUpRequest(
                    scheduled_date=datetime.utcnow() + timedelta(days=10), reason="其他"),
                operator_id=DOCTOR_ID)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(len(self.followup_records.docs), 2)
        original = self.followup_records.docs[ObjectId(followup_id)]
        self.assertEqual(original["next_visit_id"], first.id)

    async def test_re_evaluate_rejects_active_node(self):
        """进行中的节点（scheduled/in_review/awaiting_fill/rescheduled）拒绝复评。"""
        for status in ("scheduled", "in_review", "awaiting_fill", "rescheduled"):
            followup_id = await self._seed_with_status(status)
            with self.subTest(status=status):
                with self.assertRaises(AppBaseException) as error:
                    await self.service.re_evaluate_followup(
                        followup_id, ReEvaluateFollowUpRequest(
                            scheduled_date=datetime.utcnow() + timedelta(days=7)))
                self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(len(self.followup_records.docs), 4)

    async def test_re_evaluate_provider_override(self):
        """复评显式指定新责任医护时，子节点 provider_id 覆盖、created_by 保留原值。"""
        followup_id = await self._seed_with_status("completed")
        new_provider = str(ObjectId())
        response = await self.service.re_evaluate_followup(
            followup_id,
            ReEvaluateFollowUpRequest(
                scheduled_date=datetime.utcnow() + timedelta(days=7),
                provider_id=new_provider),
            operator_id=DOCTOR_ID)
        child = self.followup_records.docs[ObjectId(response.id)]
        self.assertEqual(child["provider_id"], new_provider)
        self.assertEqual(child["created_by"], DOCTOR_ID)

    async def test_select_effective_response_follows_selection_rule(self):
        """有效答卷规则：仅 confirmed 任务参与、voided 排除、取最新修订、可解释。"""
        task_a = {"_id": ObjectId(), "status": "confirmed", "followup_visit_id": "v1",
                  "fill_sessions": [{"confirmation": {
                      "response_id": "resp-a", "revision": 1,
                      "remote_status": "submitted", "submitted_at": "2026-11-01T08:00:00Z"}}]}
        task_b = {"_id": ObjectId(), "status": "confirmed",
                  "fill_sessions": [{"confirmation": {
                      "response_id": "resp-b", "revision": 3,
                      "remote_status": "submitted", "submitted_at": "2026-11-02T08:00:00Z"}}]}
        task_voided = {"_id": ObjectId(), "status": "confirmed",
                       "fill_sessions": [{"confirmation": {
                           "response_id": "resp-v", "revision": 9,
                           "remote_status": "voided", "submitted_at": "2026-11-03T08:00:00Z"}}]}
        task_unconfirmed = {"_id": ObjectId(), "status": "submitted",
                            "fill_sessions": [{"confirmation": {
                                "response_id": "resp-u", "revision": 9,
                                "remote_status": "submitted"}}]}
        task_not_linked = {"_id": ObjectId(), "status": "confirmed",
                           "followup_visit_id": "other-visit",
                           "fill_sessions": [{"confirmation": {
                               "response_id": "resp-x", "revision": 9,
                               "remote_status": "submitted"}}]}

        selected = select_effective_response(
            [task_a, task_b, task_voided, task_unconfirmed])
        # 取最新修订：revision 3 的 resp-b 胜出（voided rev9 排除，未确认任务排除）
        self.assertEqual(selected["response_id"], "resp-b")
        self.assertEqual(selected["task_id"], str(task_b["_id"]))
        self.assertEqual(selected["revision"], 3)
        self.assertEqual(selected["selection_basis"]["candidates_considered"], 2)
        # 同修订取最晚提交
        task_c = {"_id": ObjectId(), "status": "confirmed",
                  "fill_sessions": [{"confirmation": {
                      "response_id": "resp-c", "revision": 3,
                      "remote_status": "submitted", "submitted_at": "2026-11-04T08:00:00Z"}}]}
        selected_latest = select_effective_response([task_b, task_c])
        self.assertEqual(selected_latest["response_id"], "resp-c")
        # 全部无效返回 None
        self.assertIsNone(select_effective_response([task_voided, task_unconfirmed]))
        self.assertIsNone(select_effective_response([]))
        # 跨访视任务由 resolve 层排除（此处验证纯函数不越权选定它，
        # 排除逻辑在 resolve_effective_response 中按 followup_visit_id 过滤）
        self.assertEqual(
            select_effective_response([task_not_linked])["task_id"], str(task_not_linked["_id"]))

    async def test_resolve_effective_response_excludes_cross_visit_tasks(self):
        """resolve 只读重算：跨访视任务被排除，选定结果不回写节点。"""
        followup_id = await self._seed_with_status("in_review")
        own_task = {"_id": ObjectId(), "status": "confirmed",
                    "followup_visit_id": followup_id,
                    "fill_sessions": [{"confirmation": {
                        "response_id": "resp-own", "revision": 2,
                        "remote_status": "submitted", "submitted_at": "2026-11-05T08:00:00Z"}}]}
        foreign_task = {"_id": ObjectId(), "status": "confirmed",
                        "followup_visit_id": str(ObjectId()),
                        "fill_sessions": [{"confirmation": {
                            "response_id": "resp-foreign", "revision": 9,
                            "remote_status": "submitted"}}]}
        self.collections["integration_fill_tasks"].docs[own_task["_id"]] = own_task
        self.collections["integration_fill_tasks"].docs[foreign_task["_id"]] = foreign_task
        doc = self.followup_records.docs[ObjectId(followup_id)]
        doc["fill_task_ids"] = [own_task["_id"], foreign_task["_id"]]

        resolved = await self.service.resolve_effective_response(followup_id)

        self.assertEqual(resolved["response_id"], "resp-own")
        # 只读：节点未回写
        self.assertNotIn("effective_response", doc)

    async def test_resolve_effective_response_invalid_or_missing_node(self):
        self.assertIsNone(await self.service.resolve_effective_response("not-an-object-id"))
        self.assertIsNone(await self.service.resolve_effective_response(str(ObjectId())))

    # -------- D-3：逾期/失访状态机（结构先行，口径待 FU03） --------

    async def test_mark_overdue_transitions_open_nodes_and_is_idempotent(self):
        """open 状态 → overdue；重复标记幂等；终态拒绝。"""
        for status in ("scheduled", "awaiting_fill", "rescheduled"):
            followup_id = await self._seed_with_status(status)
            with self.subTest(status=status):
                response = await self.service.mark_overdue(followup_id, operator_id=DOCTOR_ID)
                self.assertEqual(response.status, FollowUpStatus.OVERDUE)
                doc = self.followup_records.docs[ObjectId(followup_id)]
                encode(doc)
                self.assertEqual(doc["metadata"]["overdue"]["operator_id"], DOCTOR_ID)
                # 幂等：重复标记返回当前节点，版本不再递增
                version = doc["mutation_version"]
                again = await self.service.mark_overdue(followup_id)
                self.assertEqual(again.status, FollowUpStatus.OVERDUE)
                self.assertEqual(
                    self.followup_records.docs[ObjectId(followup_id)]["mutation_version"], version)

    async def test_mark_overdue_rejects_terminal_and_review_states(self):
        for status in ("completed", "canceled", "in_review"):
            followup_id = await self._seed_with_status(status)
            with self.subTest(status=status):
                with self.assertRaises(AppBaseException) as error:
                    await self.service.mark_overdue(followup_id)
                self.assertEqual(error.exception.status_code, 409)

    async def test_mark_lost_requires_overdue_and_is_terminal(self):
        """失访认定仅允许 overdue 节点；认定后为终态，重复认定幂等。"""
        scheduled_id = await self._seed_with_status("scheduled")
        with self.assertRaises(AppBaseException) as error:
            await self.service.mark_lost(scheduled_id)
        self.assertEqual(error.exception.status_code, 409)

        overdue_id = await self._seed_with_status("overdue")
        response = await self.service.mark_lost(overdue_id, operator_id=DOCTOR_ID)
        self.assertEqual(response.status, FollowUpStatus.LOST)
        doc = self.followup_records.docs[ObjectId(overdue_id)]
        encode(doc)
        self.assertEqual(doc["metadata"]["lost"]["recognized_by"], DOCTOR_ID)
        # 幂等
        again = await self.service.mark_lost(overdue_id)
        self.assertEqual(again.status, FollowUpStatus.LOST)
        # lost 是终态：不能 overdue/审阅/复评
        with self.assertRaises(AppBaseException):
            await self.service.mark_overdue(overdue_id)
        with self.assertRaises(AppBaseException):
            await self.service.re_evaluate_followup(
                overdue_id, ReEvaluateFollowUpRequest(
                    scheduled_date=datetime.utcnow() + timedelta(days=1)))


if __name__ == "__main__":
    unittest.main()
