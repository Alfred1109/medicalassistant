"""One authoritative, immutable patient self-report stream.

Reports use rehab_execution_events with a protected event namespace and explicit
type. They are observations by the patient, never inferred adherence or diagnosis.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.exceptions import AppBaseException
from app.schemas.rehab_feedback import (
    PatientFeedbackCreate, PatientFeedbackPage, PatientFeedbackResponse,
    PatientFeedbackResult,
)
from app.services.rehab_publication_service import RehabPublicationService, run_rehab_transaction

PATIENT_REPORT = "patient_report"
REPORT_NAMESPACE = "patient-report:"
REPORT_SCHEMA = 1
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
            attachments=document.get("attachments") or [])
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
        self.db = db
        self.events = db.rehab_execution_events
        self.publication = RehabPublicationService(db)

    async def _plan(self, plan_id, *, session=None):
        if not ObjectId.is_valid(plan_id):
            raise _error("REHAB_PLAN_NOT_FOUND", "康复方案不存在", 404)
        plan = await self.db.rehab_plans.find_one({"_id": ObjectId(plan_id)}, session=session)
        if not plan or not isinstance(plan.get("patient_id"), str):
            raise _error("REHAB_PLAN_NOT_FOUND", "康复方案不存在", 404)
        return plan

    def _identity_query(self, plan):
        # The current publication domain is legacy account-backed patients.
        # Authorization below refuses the canonical domain; do not infer links.
        patient_account = str(ObjectId(plan["patient_id"])) if ObjectId.is_valid(plan["patient_id"]) else plan["patient_id"]
        return {"plan_id": str(plan["_id"]), "patient_id": plan["patient_id"],
                "recorded_by": patient_account, "event_type": PATIENT_REPORT,
                "schema_version": REPORT_SCHEMA}

    async def submit(self, plan_id, payload: PatientFeedbackCreate, actor):
        if getattr(actor, "role", None) != "patient":
            raise _error("REHAB_FEEDBACK_PATIENT_REQUIRED", "仅患者本人可以提交执行反馈", 403)
        await ensure_feedback_indexes(self.db)
        event_id = f"{REPORT_NAMESPACE}{actor.id}:{payload.event_id}"
        fingerprint = _fingerprint(payload)

        async def transaction(session):
            plan = await self._plan(plan_id, session=session)
            await self.publication._authorize(plan, actor, session, write=False, fence=True)
            existing = await self.events.find_one({"plan_id": str(plan["_id"]),
                                                    "event_id": event_id}, session=session)
            if existing is not None:
                expected = {**self._identity_query(plan), "event_id": event_id,
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
            guard = plan.get("_publication_fence", 0)
            if type(guard) is not int or guard < 0:
                raise _error("REHAB_FEEDBACK_INVALID_FENCE", "方案并发状态异常，请联系管理员核查", 503)
            # A real write serializes feedback against publication/withdrawal.
            # Mongo no-op writes cannot provide this guarantee.
            locked = await self.db.rehab_plans.find_one_and_update(
                {"_id": plan["_id"], "patient_id": plan["patient_id"],
                 "published_version_id": payload.version_id,
                 "status": plan.get("status"), "deleted": plan.get("deleted")},
                {"$inc": {"_publication_fence": 1}}, return_document=ReturnDocument.AFTER,
                session=session)
            if locked is None:
                raise _error("REHAB_FEEDBACK_VERSION_CHANGED", "方案已变化，请刷新后重新确认")
            attachments = await self._claim_media(plan, event_id, payload.media_ids, session)
            now = datetime.now(timezone.utc)
            if payload.performed_at > now:
                raise _error("REHAB_FEEDBACK_FUTURE_TIME", "执行时间不能晚于当前时间", 422)
            document = {"_id": ObjectId(), **self._identity_query(plan),
                "event_id": event_id, "client_event_id": str(payload.event_id),
                "request_fingerprint": fingerprint, "version_id": payload.version_id,
                "version_no": version.get("version_no"),
                "prescription_item_id": payload.prescription_item_id,
                "execution_status": payload.execution_status.value, "feelings": payload.feelings,
                "performed_at": payload.performed_at, "created_at": now,
                "attachments": attachments, "source": "patient_self_report"}
            await self.events.insert_one(document, session=session)
            return PatientFeedbackResult(feedback=_response(document), created=True)

        for attempt in range(3):
            try:
                return await run_rehab_transaction(self.db, transaction)
            except AppBaseException as error:
                if not isinstance(error.__cause__, DuplicateKeyError) or attempt == 2:
                    raise

    async def list(self, plan_id, actor, *, version_id=None, prescription_item_id=None, skip=0, limit=20):
        plan = await self._plan(plan_id)
        await self.publication._authorize(plan, actor, None, write=False, fence=False)
        if skip < 0 or not 1 <= limit <= 100:
            raise _error("REHAB_FEEDBACK_PAGINATION", "分页参数无效", 422)
        query = self._identity_query(plan)
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
            {"items_snapshot.item_id": 1}).to_list(length=len(identifiers)) if identifiers else []
        version_items = {str(version["_id"]): {entry.get("item_id") for entry in version.get("items_snapshot", [])
                         if isinstance(entry, dict)} for version in versions}
        for item in page["items"]:
            if item.get("prescription_item_id") not in version_items.get(item["version_id"], set()):
                raise _error("REHAB_FEEDBACK_INVALID_HISTORY", "反馈处方引用异常", 503)
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
