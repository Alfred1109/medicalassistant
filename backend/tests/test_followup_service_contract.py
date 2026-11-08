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
)
from app.services.followup_service import FollowupService
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
    collections = {name: FakeCollection() for name in (
        FollowUpRecord.collection_name, "medical_timelines",
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
            self.service.complete_followup(invalid_id, CompleteFollowUpRequest()),
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
        followup_id = await self._seed_followup()
        actual_date = datetime.utcnow() - timedelta(hours=1)
        data = CompleteFollowUpRequest(
            actual_date=actual_date,
            answers=[FollowUpAnswer(question_id="q1", answer_value=8, answer_text="恢复较好")],
            notes="随访完成，恢复良好",
            follow_up_result="completed",
        )

        response = await self.service.complete_followup(followup_id, data)

        self.assertIsNotNone(response)
        self.assertEqual(response.status, FollowUpStatus.COMPLETED)
        doc = self.followup_records.docs[ObjectId(followup_id)]
        encode(doc)  # answers 已转 dict，文档可序列化
        self.assertEqual(doc["status"], "completed")
        self.assertEqual(doc["actual_date"], actual_date)
        self.assertIsInstance(doc["answers"][0], dict)
        self.assertEqual(doc["answers"][0]["question_id"], "q1")
        self.assertEqual(doc["answers"][0]["answer_value"], 8)
        # FU01 S1：完成数据落顶层正式字段，停止 metadata.completion_data / metadata.result
        self.assertEqual(doc["completion_data"]["result"], "completed")
        self.assertEqual(doc["completion_data"]["notes"], "随访完成，恢复良好")
        self.assertEqual(doc["follow_up_result"], "completed")
        self.assertNotIn("completion_data", doc.get("metadata", {}))
        self.assertNotIn("result", doc.get("metadata", {}))
        self.assertEqual(doc["notes"], "随访完成，恢复良好")

    async def test_complete_followup_creates_next_followup(self):
        followup_id = await self._seed_followup()
        data = CompleteFollowUpRequest(
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


if __name__ == "__main__":
    unittest.main()
