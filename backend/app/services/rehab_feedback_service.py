"""One authoritative, immutable patient self-report stream.

Reports use rehab_execution_events with a protected event namespace and explicit
type. They are observations by the patient, never inferred adherence or diagnosis.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from bson import ObjectId
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.exceptions import AppBaseException
from app.core.patient_access import patient_domain_context
from app.schemas.rehab_feedback import (
    ClinicalFeedbackReview, PatientFeedbackCreate, PatientFeedbackPage,
    PatientFeedbackResponse, PatientFeedbackSupplement,
    PatientFeedbackResult,
)
from app.services.rehab_publication_service import RehabPublicationService, run_rehab_transaction

PATIENT_REPORT = "patient_report"
REPORT_NAMESPACE = "patient-report:"
REPORT_SCHEMA = 1
SHANGHAI = ZoneInfo("Asia/Shanghai")
EVENT_INDEX = "uniq_plan_event_id"
MEDIA_DIR = Path(__file__).resolve().parents[2] / "data" / "patient-feedback"
MEDIA_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
               "video/mp4": ".mp4", "video/webm": ".webm"}


def _error(code, message, status=409):
    return AppBaseException(message, status_code=status, error_code=code)


def _utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _request_data(payload):
    data = {"version_id": payload.version_id,
            "prescription_item_id": payload.prescription_item_id,
            "execution_status": payload.execution_status.value,
            "feelings": payload.feelings,
            "performed_at": payload.performed_at.isoformat()}
    if payload.media_ids:
        data["media_ids"] = sorted(payload.media_ids)
    return data


def _fingerprint(payload):
    return hashlib.sha256(json.dumps(_request_data(payload), sort_keys=True,
        ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _response(document):
    """An explicit projection: never return old events or internal metadata."""
    try:
        if document.get("event_type") != PATIENT_REPORT or document.get("schema_version") != REPORT_SCHEMA:
            raise ValueError("not a patient report")
        return PatientFeedbackResponse(
            id=str(document["_id"]), event_id=document["client_event_id"],
            plan_id=document["plan_id"], version_id=document["version_id"],
            prescription_item_id=document["prescription_item_id"],
            execution_status=document["execution_status"], feelings=document["feelings"],
            performed_at=_utc(document["performed_at"]), recorded_by=document["recorded_by"],
            created_at=_utc(document["created_at"]),
            attachments=document.get("attachments") or [], cycle_id=document.get("cycle_id"),
            intervention_type=document.get("intervention_type"),
            clinical_review=RehabFeedbackService._review_projection(document.get("clinical_review")),
            supplements=[RehabFeedbackService._supplement_projection(item)
                         for item in document.get("supplements") or []])
    except (KeyError, TypeError, ValueError, AttributeError):
        raise _error("REHAB_FEEDBACK_INVALID_HISTORY", "反馈历史格式异常，请联系管理员核查", 503) from None


async def ensure_feedback_indexes(db):
    """An absent/unsafe unique index is an error, never a best-effort write."""
    try:
        await db.rehab_execution_events.create_index(
            [("plan_id", 1), ("event_id", 1)], unique=True, name=EVENT_INDEX)
        spec = (await db.rehab_execution_events.index_information()).get(EVENT_INDEX, {})
        if (spec.get("key") != [("plan_id", 1), ("event_id", 1)]
                or spec.get("unique") is not True or spec.get("partialFilterExpression")
                or spec.get("sparse")):
            raise ValueError("unsafe event index")
    except (PyMongoError, ValueError, AttributeError):
        raise _error("REHAB_FEEDBACK_INDEX_UNAVAILABLE", "反馈唯一索引不可用，暂不能保存", 503) from None


class RehabFeedbackService:
    def __init__(self, db):
        # 患者资料读取（存在性/可用性/医护归属）不在此处直查 users，统一委托
        # RehabPublicationService._authorize（域分派：legacy 经患者读取适配器，
        # canonical 经 clinical_patients + 链接解析）。本服务其余读取以
        # plan.patient_id 为域内身份锚点；recorded_by 的解析规则见
        # _identity_query 注释（legacy 同文档假设 / canonical 链接解析）。
        self.db = db
        self.events = db.rehab_execution_events
        self.publication = RehabPublicationService(db)

    @staticmethod
    def _review_projection(value):
        if not isinstance(value, dict):
            return {"status": "pending", "revision": 0, "note": "", "reviewed_at": None}
        reviewed_at = value.get("reviewed_at")
        return {"status": value.get("status", "pending"),
                "revision": value.get("revision", 0), "note": value.get("note", ""),
                "reviewed_at": _utc(reviewed_at) if isinstance(reviewed_at, datetime) else None}

    @staticmethod
    def _supplement_projection(value):
        return {"id": value["id"], "event_id": value["event_id"],
                "note": value["note"], "submitted_at": _utc(value["submitted_at"]),
                "attachments": value.get("attachments") or []}

    async def _plan(self, plan_id, *, session=None):
        if not ObjectId.is_valid(plan_id):
            raise _error("REHAB_PLAN_NOT_FOUND", "康复方案不存在", 404)
        plan = await self.db.rehab_plans.find_one({"_id": ObjectId(plan_id)}, session=session)
        if not plan or not isinstance(plan.get("patient_id"), str):
            raise _error("REHAB_PLAN_NOT_FOUND", "康复方案不存在", 404)
        return plan

    async def _identity_query(self, plan, *, session=None, context=None):
        # DOMAIN-BRANCH: 反馈身份锚点按域分派（canonical 全量后，legacy 同文档
        # 分支可整体删除；域分派读取下沉内核，同一请求内只读一次域状态）。
        # - legacy 同文档假设：plan.patient_id 同时是患者实体 ID 与患者账号 ID
        #   （recorded_by 锚点，提交路径的 _authorize 已确保账号与患者同文档）。
        # - canonical：recorded_by 经 patient_account_links 显式解析（verified
        #   链接），不再把 plan.patient_id 当账号 ID。提交路径中链接核验已由
        #   发布域授权（resolve_self）完成；无链接患者没有可锚定的反馈身份，
        #   在此 fail-closed 抛 503，绝不回退同 ID 假设（无链接患者无法提交
        #   反馈是预期形态）。
        if context is None:
            context = await patient_domain_context(self.db, session=session)
        patient_id = plan["patient_id"]
        # domain-dispatch: 迁移完成后可删
        if context.is_canonical:
            recorded_by = await context.linked_account_id(patient_id)
            if recorded_by is None:
                raise _error("REHAB_PATIENT_ACCOUNT_UNAVAILABLE",
                             "该患者尚未关联患者账号，无法定位反馈身份", 503)
        else:
            # LEGACY-SHAPE: legacy 同文档假设——plan.patient_id 即患者账号 ID。
            recorded_by = str(ObjectId(patient_id)) if ObjectId.is_valid(patient_id) else patient_id
        return {"plan_id": str(plan["_id"]), "patient_id": patient_id,
                "recorded_by": recorded_by, "event_type": PATIENT_REPORT,
                "schema_version": REPORT_SCHEMA}

    async def _feedback_intervention_type(self, document, session=None):
        version_id = document.get("version_id")
        if not isinstance(version_id, str) or not ObjectId.is_valid(version_id):
            raise _error("REHAB_FEEDBACK_INVALID_HISTORY", "反馈方案版本无效，无法核验", 503)
        version = await self.db.rehab_plan_versions.find_one({"_id": ObjectId(version_id),
            "plan_id": document.get("plan_id"), "workflow": "patient_publication",
            "status": {"$in": ["published", "withdrawn"]}},
            {"items_snapshot": 1}, session=session)
        if not version:
            raise _error("REHAB_FEEDBACK_INVALID_HISTORY", "反馈方案版本不存在，无法核验", 503)
        item = next((item for item in version.get("items_snapshot", [])
                     if isinstance(item, dict) and item.get("item_id") == document.get("prescription_item_id")), None)
        if not item or item.get("intervention_type") not in {"exercise", "diet", "medication", "psychology"}:
            raise _error("REHAB_FEEDBACK_INVALID_HISTORY", "反馈处方项无效，无法核验", 503)
        return item["intervention_type"]

    async def _cycle_for_feedback(self, plan_id, performed_at, session=None):
        local_day = _utc(performed_at).astimezone(SHANGHAI).date().isoformat()
        cycles = await self.db.rehab_training_cycles.find({"plan_id": plan_id,
            "start_date": {"$lte": local_day}, "end_date": {"$gte": local_day}}, session=session).to_list(length=2)
        if len(cycles) > 1:
            raise _error("REHAB_TRAINING_CYCLE_OVERLAP", "存在重叠训练周期，暂不能记录训练", 503)
        return cycles[0] if cycles else None

    async def submit(self, plan_id, payload: PatientFeedbackCreate, actor):
        if getattr(actor, "role", None) != "patient":
            raise _error("REHAB_FEEDBACK_PATIENT_REQUIRED", "仅患者本人可以提交执行反馈", 403)
        await ensure_feedback_indexes(self.db)
        event_id = f"{REPORT_NAMESPACE}{actor.id}:{payload.event_id}"
        fingerprint = _fingerprint(payload)

        async def transaction(session):
            plan = await self._plan(plan_id, session=session)
            # 域分派一次读取：发布域授权与反馈身份锚点复用同一上下文
            # （事务内透传 session，状态读取落在同一事务快照内）。
            context = await patient_domain_context(self.db, session=session)
            await self.publication._authorize(plan, actor, session, write=False, fence=True,
                                              context=context)
            existing = await self.events.find_one({"plan_id": str(plan["_id"]),
                                                    "event_id": event_id}, session=session)
            if existing is not None:
                expected = {**(await self._identity_query(plan, session=session, context=context)), "event_id": event_id,
                            "request_fingerprint": fingerprint, "client_event_id": str(payload.event_id)}
                if any(existing.get(key) != value for key, value in expected.items()):
                    raise _error("REHAB_FEEDBACK_EVENT_CONFLICT", "此提交标识已用于其他内容，请重新核对")
                return PatientFeedbackResult(feedback=_response(existing), created=False)

            if plan.get("deleted") or plan.get("status") in {"cancelled", "canceled", "archived"}:
                raise _error("REHAB_FEEDBACK_PLAN_INACTIVE", "该方案已结束或撤回，不能提交新的反馈")
            if plan.get("published_version_id") != payload.version_id:
                raise _error("REHAB_FEEDBACK_VERSION_CHANGED", "已发布方案已变化，请刷新后重新确认")
            version = await self.db.rehab_plan_versions.find_one({
                "_id": ObjectId(payload.version_id), "plan_id": str(plan["_id"]),
                "patient_id": plan["patient_id"], "workflow": "patient_publication",
                "status": "published"}, session=session)
            if not version:
                raise _error("REHAB_FEEDBACK_VERSION_CHANGED", "该发布版本已不可用，请刷新方案")
            snapshots = version.get("items_snapshot")
            if not isinstance(snapshots, list) or not any(
                    isinstance(item, dict) and item.get("item_id") == payload.prescription_item_id
                    for item in snapshots):
                raise _error("REHAB_FEEDBACK_ITEM_MISMATCH", "该处方项不属于已确认的发布版本")
            item_snapshot = next(item for item in snapshots if item.get("item_id") == payload.prescription_item_id)
            # A real write serializes feedback against publication/withdrawal.
            # Mongo no-op writes cannot provide this guarantee.
            # （R1-A2 收敛：_publication_fence 载体复用 publication._touch_plan
            # 的唯一实现，消除同一字段两套错误码——503 栅栏形态码由
            # REHAB_FEEDBACK_INVALID_FENCE 统一为 REHAB_PUBLICATION_INVALID
            # （前端未消费旧码）；CAS miss 保留本域 409 码
            # REHAB_FEEDBACK_VERSION_CHANGED，经 conflict_code 参数化注入。）
            await self.publication._touch_plan(plan, session, extra_query={
                "patient_id": plan["patient_id"],
                "published_version_id": payload.version_id,
                "status": plan.get("status"), "deleted": plan.get("deleted")},
                conflict_code="REHAB_FEEDBACK_VERSION_CHANGED",
                conflict_message="方案已变化，请刷新后重新确认")
            attachments = await self._claim_media(plan, event_id, payload.media_ids, session)
            now = datetime.now(timezone.utc)
            if payload.performed_at > now:
                raise _error("REHAB_FEEDBACK_FUTURE_TIME", "执行时间不能晚于当前时间", 422)
            if (item_snapshot.get("intervention_type") == "exercise"
                    and payload.execution_status.value in {"completed", "partial"}
                    and not any(item["content_type"].startswith("video/") for item in attachments)):
                raise _error("REHAB_FEEDBACK_VIDEO_REQUIRED", "已执行或部分执行的训练必须上传训练视频", 422)
            cycle = None
            if item_snapshot.get("intervention_type") == "exercise":
                cycle = await self._cycle_for_feedback(str(plan["_id"]), payload.performed_at, session=session)
                configured_cycles = await self.db.rehab_training_cycles.find_one(
                    {"plan_id": str(plan["_id"])}, {"_id": 1}, session=session)
                if configured_cycles and cycle is None:
                    raise _error("REHAB_TRAINING_CYCLE_REQUIRED", "本次训练时间不在医护设置的训练周期内", 422)
            if cycle and cycle.get("status") == "accepted":
                raise _error("REHAB_TRAINING_CYCLE_ACCEPTED", "该训练周期已验收，不能再添加训练反馈")
            document = {"_id": ObjectId(), **(await self._identity_query(plan, session=session, context=context)),
                "event_id": event_id, "client_event_id": str(payload.event_id),
                "request_fingerprint": fingerprint, "version_id": payload.version_id,
                "version_no": version.get("version_no"),
                "prescription_item_id": payload.prescription_item_id,
                "intervention_type": item_snapshot["intervention_type"],
                "execution_status": payload.execution_status.value, "feelings": payload.feelings,
                "performed_at": payload.performed_at, "created_at": now,
                "attachments": attachments, "source": "patient_self_report",
                "cycle_id": cycle["_id"] if cycle else None,
                "clinical_review": {"status": "pending", "revision": 0,
                                    "note": "", "history": []}, "supplements": []}
            await self.events.insert_one(document, session=session)
            return PatientFeedbackResult(feedback=_response(document), created=True)

        for attempt in range(3):
            try:
                return await run_rehab_transaction(self.db, transaction)
            except AppBaseException as error:
                if not isinstance(error.__cause__, DuplicateKeyError) or attempt == 2:
                    raise

    async def review(self, plan_id, feedback_id, payload: ClinicalFeedbackReview, actor):
        if getattr(actor, "role", None) not in {"doctor", "health_manager"}:
            raise _error("REHAB_CLINICIAN_REQUIRED", "需要医护核验权限", 403)
        if not ObjectId.is_valid(feedback_id):
            raise _error("REHAB_FEEDBACK_NOT_FOUND", "训练反馈不存在", 404)

        async def write(session):
            plan = await self._plan(plan_id, session=session)
            await self.publication._authorize(plan, actor, session, write=True, fence=True)
            document = await self.events.find_one({"_id": ObjectId(feedback_id),
                "plan_id": str(plan["_id"]), "event_type": PATIENT_REPORT,
                "schema_version": REPORT_SCHEMA}, session=session)
            if not document:
                raise _error("REHAB_FEEDBACK_NOT_FOUND", "训练反馈不存在", 404)
            current = document.get("clinical_review") or {"status": "pending", "revision": 0,
                                                           "note": "", "history": []}
            if current.get("status") != "pending":
                raise _error("REHAB_FEEDBACK_REVIEW_CONFLICT", "该反馈已核验，请刷新后查看")
            if current.get("revision", 0) != payload.expected_revision:
                raise _error("REHAB_FEEDBACK_REVIEW_CONFLICT", "反馈核验状态已变化，请刷新后重试")
            if await self._feedback_intervention_type(document, session=session) != "exercise":
                raise _error("REHAB_FEEDBACK_REVIEW_NOT_EXERCISE", "此核验流程只适用于运动训练反馈", 422)
            if document.get("execution_status") not in {"completed", "partial"}:
                raise _error("REHAB_FEEDBACK_REVIEW_NOT_REQUIRED", "未执行的训练反馈无需视频核验", 422)
            if payload.status == "verified":
                attachments = list(document.get("attachments") or [])
                for supplement in document.get("supplements") or []:
                    attachments.extend(supplement.get("attachments") or [])
                if not any(item.get("content_type", "").startswith("video/") for item in attachments):
                    raise _error("REHAB_FEEDBACK_VIDEO_REQUIRED", "没有训练视频，不能核验通过；请退回患者补充", 422)
            cycle = await self._cycle_for_feedback(str(plan["_id"]), document["performed_at"], session=session)
            if cycle and cycle.get("status") == "accepted":
                raise _error("REHAB_TRAINING_CYCLE_ACCEPTED", "该训练周期已验收，不能再修改核验")
            stamp = datetime.now(timezone.utc)
            item = {"status": payload.status, "revision": payload.expected_revision + 1,
                    "note": payload.note.strip(), "reviewed_at": stamp,
                    "reviewed_by": str(actor.id)}
            history = list(current.get("history") or []) + [item]
            review = {**item, "history": history}
            await self.publication._touch_plan(plan, session)
            revision_filter = {"_id": document["_id"], "$or": [
                {"clinical_review.revision": payload.expected_revision},
                {"clinical_review": {"$exists": False}}]}
            result = await self.events.update_one(revision_filter,
                {"$set": {"clinical_review": review}}, session=session)
            if result.matched_count != 1:
                raise _error("REHAB_FEEDBACK_REVIEW_CONFLICT", "反馈核验状态已变化，请刷新后重试")
            return {"feedback": _response({**document, "clinical_review": review})}
        return await run_rehab_transaction(self.db, write)

    async def supplement(self, plan_id, feedback_id, payload: PatientFeedbackSupplement, actor):
        if getattr(actor, "role", None) != "patient":
            raise _error("REHAB_FEEDBACK_PATIENT_REQUIRED", "仅患者本人可以补充训练材料", 403)
        if not ObjectId.is_valid(feedback_id):
            raise _error("REHAB_FEEDBACK_NOT_FOUND", "训练反馈不存在", 404)
        await ensure_feedback_indexes(self.db)
        supplement_event_id = f"patient-supplement:{actor.id}:{payload.event_id}"
        fingerprint = hashlib.sha256(json.dumps([payload.note, sorted(payload.media_ids)],
            ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()

        async def write(session):
            plan = await self._plan(plan_id, session=session)
            context = await patient_domain_context(self.db, session=session)
            await self.publication._authorize(plan, actor, session, write=False, fence=True,
                                              context=context)
            document = await self.events.find_one({"_id": ObjectId(feedback_id),
                "plan_id": str(plan["_id"]), "recorded_by": str(actor.id),
                "event_type": PATIENT_REPORT, "schema_version": REPORT_SCHEMA}, session=session)
            if not document:
                raise _error("REHAB_FEEDBACK_NOT_FOUND", "训练反馈不存在", 404)
            existing = next((item for item in document.get("supplements", [])
                             if item.get("event_id") == supplement_event_id), None)
            if existing:
                if existing.get("request_fingerprint") != fingerprint:
                    raise _error("REHAB_FEEDBACK_EVENT_CONFLICT", "此补充标识已用于其他内容")
                return {"feedback": _response(document), "created": False}
            current = document.get("clinical_review") or {"status": "pending", "revision": 0,
                                                           "note": "", "history": []}
            if current.get("status") != "return_for_supplement":
                raise _error("REHAB_FEEDBACK_SUPPLEMENT_UNEXPECTED", "当前反馈不需要补充材料")
            if await self._feedback_intervention_type(document, session=session) != "exercise":
                raise _error("REHAB_FEEDBACK_SUPPLEMENT_UNEXPECTED", "此补充流程只适用于运动训练反馈", 422)
            cycle = await self._cycle_for_feedback(str(plan["_id"]), document["performed_at"], session=session)
            if cycle and cycle.get("status") == "accepted":
                raise _error("REHAB_TRAINING_CYCLE_ACCEPTED", "该训练周期已验收，不能再补充")
            attachments = await self._claim_media(plan, supplement_event_id, payload.media_ids, session)
            if (document.get("execution_status") in {"completed", "partial"}
                    and not any(item["content_type"].startswith("video/") for item in attachments)):
                raise _error("REHAB_FEEDBACK_VIDEO_REQUIRED", "训练补充材料必须包含视频", 422)
            stamp = datetime.now(timezone.utc)
            supplement = {"id": str(ObjectId()), "event_id": supplement_event_id,
                "request_fingerprint": fingerprint, "note": payload.note,
                "submitted_at": stamp, "attachments": attachments}
            review = {"status": "pending", "revision": current.get("revision", 0) + 1,
                "note": "", "reviewed_at": None, "history": list(current.get("history") or [])}
            await self.publication._touch_plan(plan, session)
            result = await self.events.update_one({"_id": document["_id"],
                "clinical_review.revision": current.get("revision", 0),
                "clinical_review.status": "return_for_supplement"},
                {"$push": {"supplements": supplement}, "$set": {"clinical_review": review}},
                session=session)
            if result.matched_count != 1:
                raise _error("REHAB_FEEDBACK_REVIEW_CONFLICT", "反馈状态已变化，请刷新后重试")
            updated = {**document, "supplements": list(document.get("supplements") or []) + [supplement],
                       "clinical_review": review}
            return {"feedback": _response(updated), "created": True}
        return await run_rehab_transaction(self.db, write)

    async def list(self, plan_id, actor, *, version_id=None, prescription_item_id=None, skip=0, limit=20):
        plan = await self._plan(plan_id)
        # 域分派一次读取：发布域授权与反馈身份锚点复用同一上下文。
        context = await patient_domain_context(self.db)
        await self.publication._authorize(plan, actor, None, write=False, fence=False, context=context)
        if skip < 0 or not 1 <= limit <= 100:
            raise _error("REHAB_FEEDBACK_PAGINATION", "分页参数无效", 422)
        query = await self._identity_query(plan, context=context)
        if version_id:
            if not ObjectId.is_valid(version_id):
                raise _error("REHAB_FEEDBACK_FILTER", "反馈版本筛选无效", 422)
            query["version_id"] = str(ObjectId(version_id))
        if prescription_item_id:
            if not ObjectId.is_valid(prescription_item_id):
                raise _error("REHAB_FEEDBACK_FILTER", "反馈处方筛选无效", 422)
            query["prescription_item_id"] = str(ObjectId(prescription_item_id))
        rows = await self.events.aggregate([
            {"$match": query}, {"$sort": {"created_at": -1, "_id": -1}},
            {"$facet": {"items": [{"$skip": skip}, {"$limit": limit}],
                        "count": [{"$count": "total"}]}}
        ]).to_list(length=1)
        page = rows[0] if rows else {"items": [], "count": []}
        # Every returned historical report must still point to its exact frozen
        # publication and item; do not relabel untyped/foreign event history.
        identifiers = [item.get("version_id") for item in page["items"]]
        if any(not isinstance(value, str) or not ObjectId.is_valid(value) for value in identifiers):
            raise _error("REHAB_FEEDBACK_INVALID_HISTORY", "反馈版本引用异常", 503)
        identifiers = set(identifiers)
        versions = await self.db.rehab_plan_versions.find({"_id": {"$in": [ObjectId(value) for value in identifiers]},
            "plan_id": str(plan["_id"]), "patient_id": plan["patient_id"],
            "workflow": "patient_publication", "status": {"$in": ["published", "withdrawn"]}},
            {"items_snapshot.item_id": 1, "items_snapshot.intervention_type": 1}).to_list(length=len(identifiers)) if identifiers else []
        version_items = {str(version["_id"]): {entry.get("item_id") for entry in version.get("items_snapshot", [])
                         if isinstance(entry, dict)} for version in versions}
        for item in page["items"]:
            if item.get("prescription_item_id") not in version_items.get(item["version_id"], set()):
                raise _error("REHAB_FEEDBACK_INVALID_HISTORY", "反馈处方引用异常", 503)
            version = next((row for row in versions if str(row["_id"]) == item["version_id"]), None)
            snapshot_item = next((entry for entry in version.get("items_snapshot", [])
                                  if isinstance(entry, dict) and entry.get("item_id") == item["prescription_item_id"]), None) if version else None
            if not snapshot_item or snapshot_item.get("intervention_type") not in {"diet", "exercise", "medication", "psychology"}:
                raise _error("REHAB_FEEDBACK_INVALID_HISTORY", "反馈处方类型异常", 503)
            item["intervention_type"] = snapshot_item["intervention_type"]
        return PatientFeedbackPage(items=[_response(item) for item in page["items"]],
            total=page["count"][0]["total"] if page["count"] else 0, skip=skip, limit=limit)

    async def _claim_media(self, plan, event_id, media_ids, session):
        attachments = []
        for media_id in media_ids:
            row = await self.db.patient_feedback_media.find_one(
                {"_id": media_id, "plan_id": str(plan["_id"]), "patient_id": plan["patient_id"]}, session=session)
            if not row:
                raise _error("REHAB_FEEDBACK_MEDIA_MISSING", "图片或视频还没有保存，请重新上传", 422)
            bound = row.get("bound_event_id")
            if bound not in (None, event_id):
                raise _error("REHAB_FEEDBACK_MEDIA_USED", "该图片或视频已经用于另一条反馈", 409)
            if bound is None:
                updated = await self.db.patient_feedback_media.update_one(
                    {"_id": media_id, "bound_event_id": None},
                    {"$set": {"bound_event_id": event_id}}, session=session)
                if updated.matched_count != 1:
                    raise _error("REHAB_FEEDBACK_MEDIA_USED", "该图片或视频已经用于另一条反馈", 409)
            attachments.append({"id": media_id, "content_type": row["content_type"], "name": row.get("name") or "附件"})
        return attachments

    async def save_media(self, plan_id, actor, content: bytes, content_type: str, filename: str):
        if getattr(actor, "role", None) != "patient":
            raise _error("REHAB_FEEDBACK_PATIENT_REQUIRED", "仅患者本人可以上传任务检查附件", 403)
        plan = await self._plan(plan_id)
        await self.publication._authorize(plan, actor, None, write=False, fence=False)
        content_type = (content_type or "").split(";", 1)[0].strip().lower()
        suffix = MEDIA_TYPES.get(content_type)
        limit = 8 * 1024 * 1024 if content_type.startswith("image/") else 20 * 1024 * 1024
        if suffix is None or not content or len(content) > limit:
            raise _error("REHAB_FEEDBACK_MEDIA_INVALID", "请上传 8MB 以内的 JPG、PNG、WebP，或 20MB 以内的 MP4、WebM", 422)
        media_id = uuid.uuid4().hex
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        (MEDIA_DIR / f"{media_id}{suffix}").write_bytes(content)
        name = (filename or "附件")[:80]
        await self.db.patient_feedback_media.insert_one({
            "_id": media_id, "plan_id": str(plan["_id"]), "patient_id": plan["patient_id"],
            "content_type": content_type, "name": name, "suffix": suffix, "size": len(content),
            "bound_event_id": None, "created_at": datetime.now(timezone.utc)})
        return {"id": media_id, "content_type": content_type, "name": name}

    async def open_media(self, plan_id, media_id, actor):
        plan = await self._plan(plan_id)
        await self.publication._authorize(plan, actor, None, write=False, fence=False)
        if not isinstance(media_id, str) or len(media_id) != 32:
            raise _error("REHAB_FEEDBACK_MEDIA_MISSING", "附件不存在", 404)
        row = await self.db.patient_feedback_media.find_one(
            {"_id": media_id, "plan_id": str(plan["_id"]), "patient_id": plan["patient_id"]})
        if not row:
            raise _error("REHAB_FEEDBACK_MEDIA_MISSING", "附件不存在", 404)
        if getattr(actor, "role", None) != "patient" and not row.get("bound_event_id"):
            raise _error("REHAB_FEEDBACK_MEDIA_MISSING", "附件不存在", 404)
        path = MEDIA_DIR / f"{media_id}{row.get('suffix') or ''}"
        if not path.is_file():
            raise _error("REHAB_FEEDBACK_MEDIA_MISSING", "附件文件不存在", 404)
        return path, row["content_type"]
