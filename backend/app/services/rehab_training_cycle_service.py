"""Plan-level training cycles that remain stable across prescription revisions."""
import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import AppBaseException
from app.schemas.rehab_training_cycle import TrainingCycleCreate, TrainingCycleUpdate, TrainingCycleAcceptance
from app.services.rehab_publication_service import RehabPublicationService, run_rehab_transaction

SHANGHAI = ZoneInfo("Asia/Shanghai")
PATIENT_REPORT = "patient_report"
REPORT_SCHEMA = 1


def _error(code, message, status=409, details=None):
    return AppBaseException(message, status_code=status, error_code=code, details=details)


def _period_bounds(start_date, end_date):
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    if isinstance(end_date, str):
        end_date = date.fromisoformat(end_date)
    start = datetime.combine(start_date, time.min, tzinfo=SHANGHAI).astimezone(timezone.utc)
    end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=SHANGHAI).astimezone(timezone.utc)
    return start, end


class RehabTrainingCycleService:
    def __init__(self, db):
        self.db = db
        self.publication = RehabPublicationService(db)
        self.cycles = db.rehab_training_cycles
        self.operations = db.rehab_training_cycle_operations

    async def ensure_storage(self):
        await self.cycles.create_index([("plan_id", 1), ("_id", 1)], unique=True,
                                       name="rehab_training_cycle_plan_id")
        await self.cycles.create_index([("plan_id", 1), ("start_date", 1), ("end_date", 1)],
                                       name="rehab_training_cycle_dates")

    @staticmethod
    def _operation_key(plan_id, actor, action, request_id):
        raw = json.dumps([plan_id, str(actor.id), action, request_id], separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _fingerprint(payload):
        raw = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()

    async def _prior_operation(self, key, fingerprint, session):
        prior = await self.operations.find_one({"_id": key}, session=session)
        if prior and prior.get("fingerprint") != fingerprint:
            raise _error("REHAB_TRAINING_CYCLE_IDEMPOTENCY_CONFLICT", "相同请求标识不能提交不同内容")
        return prior

    async def _record_operation(self, key, fingerprint, plan_id, actor, cycle_id, session):
        await self.operations.insert_one({"_id": key, "fingerprint": fingerprint,
            "plan_id": plan_id, "actor_id": str(actor.id), "cycle_id": cycle_id,
            "created_at": datetime.now(timezone.utc)}, session=session)

    async def _plan(self, plan_id, session=None):
        if not ObjectId.is_valid(plan_id):
            raise _error("REHAB_PLAN_NOT_FOUND", "康复方案不存在", 404)
        plan = await self.db.rehab_plans.find_one({"_id": ObjectId(plan_id)}, session=session)
        if not plan or not isinstance(plan.get("patient_id"), str):
            raise _error("REHAB_PLAN_NOT_FOUND", "康复方案不存在", 404)
        return plan

    def _projection(self, cycle, counts=None):
        acceptance = cycle.get("acceptance")
        result = {"id": str(cycle["_id"]), "plan_id": cycle["plan_id"],
                  "title": cycle["title"], "start_date": str(cycle["start_date"]),
                  "end_date": str(cycle["end_date"]), "status": cycle.get("status", "open"),
                  "revision": cycle.get("revision", 0),
                  "acceptance": ({"status": "accepted", "note": acceptance["note"],
                                  "accepted_at": acceptance["accepted_at"].replace(tzinfo=timezone.utc).isoformat()
                                  if acceptance["accepted_at"].tzinfo is None else acceptance["accepted_at"].astimezone(timezone.utc).isoformat()}
                                 if isinstance(acceptance, dict) else None)}
        if counts is not None:
            result.update({key: counts[key] for key in ("feedback_count", "verified_count", "pending_reviews_count")
                           if key in counts})
        return result

    async def _count_cycle_feedback(self, plan_id, cycle, session=None):
        start, end = _period_bounds(cycle["start_date"], cycle["end_date"])
        docs = await self.db.rehab_execution_events.find({"plan_id": plan_id,
            "event_type": PATIENT_REPORT, "schema_version": REPORT_SCHEMA,
            "performed_at": {"$gte": start, "$lt": end}}, session=session).to_list(length=None)
        version_ids = {row.get("version_id") for row in docs}
        if any(not isinstance(item, str) or not ObjectId.is_valid(item) for item in version_ids):
            raise _error("REHAB_TRAINING_CYCLE_HISTORY_INVALID", "周期内存在无法识别的反馈版本，暂不能验收", 503)
        versions = await self.db.rehab_plan_versions.find({"_id": {"$in": [ObjectId(item) for item in version_ids]},
            "plan_id": plan_id}, {"items_snapshot": 1}, session=session).to_list(length=len(version_ids)) if version_ids else []
        if len(versions) != len(version_ids):
            raise _error("REHAB_TRAINING_CYCLE_HISTORY_INVALID", "周期内存在无法识别的方案版本，暂不能验收", 503)
        item_types = {}
        for version in versions:
            for item in version.get("items_snapshot") or []:
                if isinstance(item, dict):
                    item_types[(str(version["_id"]), item.get("item_id"))] = item.get("intervention_type")
        for row in docs:
            if (row.get("version_id"), row.get("prescription_item_id")) not in item_types:
                raise _error("REHAB_TRAINING_CYCLE_HISTORY_INVALID", "周期内存在无法识别的处方项，暂不能验收", 503)
        relevant = [row for row in docs if item_types[(row.get("version_id"),
                      row.get("prescription_item_id"))] == "exercise"
                    and row.get("execution_status") in {"completed", "partial"}]
        verified = [row for row in relevant if (row.get("clinical_review") or {}).get("status") == "verified"]
        return {"feedback_count": len(relevant), "verified_count": len(verified),
                "pending_reviews_count": len(relevant) - len(verified),
                "reviewed_feedback": [{"feedback_id": str(row["_id"]),
                    "version_id": row["version_id"],
                    "prescription_item_id": row["prescription_item_id"],
                    "review_revision": (row.get("clinical_review") or {}).get("revision", 0),
                    "reviewed_at": (row.get("clinical_review") or {}).get("reviewed_at")}
                    for row in verified]}

    async def list(self, plan_id, actor):
        plan = await self._plan(plan_id)
        await self.publication._authorize(plan, actor, None, write=False)
        cycles = await self.cycles.find({"plan_id": str(plan["_id"])}).sort("start_date", 1).to_list(length=200)
        items = []
        for cycle in cycles:
            items.append(self._projection(cycle, await self._count_cycle_feedback(str(plan["_id"]), cycle)))
        return {"items": items, "total": len(items)}

    async def create(self, plan_id, actor, payload: TrainingCycleCreate):
        if actor.role not in {"doctor", "health_manager"}:
            raise _error("REHAB_CLINICIAN_REQUIRED", "需要医护设置训练周期权限", 403)
        await self.ensure_storage()
        operation_key = self._operation_key(plan_id, actor, "create", payload.request_id)
        fingerprint = self._fingerprint(payload)
        async def write(session):
            plan = await self._plan(plan_id, session)
            await self.publication._authorize(plan, actor, session, write=True, fence=True)
            prior = await self._prior_operation(operation_key, fingerprint, session)
            if prior:
                cycle = await self.cycles.find_one({"_id": prior["cycle_id"], "plan_id": str(plan["_id"])}, session=session)
                if not cycle:
                    raise _error("REHAB_TRAINING_CYCLE_HISTORY_INVALID", "幂等记录引用的周期不存在", 503)
                return {"cycle": self._projection(cycle, await self._count_cycle_feedback(str(plan["_id"]), cycle, session=session)), "created": False}
            if not plan.get("published_version_id"):
                raise _error("REHAB_TRAINING_CYCLE_PUBLICATION_REQUIRED", "请先发布康复方案，再设置训练周期")
            overlaps = await self.cycles.find_one({"plan_id": str(plan["_id"]),
                "start_date": {"$lte": payload.end_date.isoformat()},
                "end_date": {"$gte": payload.start_date.isoformat()}}, session=session)
            if overlaps:
                raise _error("REHAB_TRAINING_CYCLE_OVERLAP", "训练周期不能与已有周期重叠")
            stamp = datetime.now(timezone.utc)
            cycle = {"_id": str(ObjectId()), "plan_id": str(plan["_id"]),
                "patient_id": plan["patient_id"], "title": payload.title,
                "start_date": payload.start_date.isoformat(), "end_date": payload.end_date.isoformat(),
                "status": "open", "revision": 0, "created_by": str(actor.id),
                "created_at": stamp, "updated_at": stamp}
            try:
                await self.cycles.insert_one(cycle, session=session)
            except DuplicateKeyError:
                raise _error("REHAB_TRAINING_CYCLE_CONFLICT", "训练周期已创建，请刷新后重试") from None
            await self.publication._touch_plan(plan, session)
            await self._record_operation(operation_key, fingerprint, str(plan["_id"]), actor, cycle["_id"], session)
            return {"cycle": self._projection(cycle, {"feedback_count": 0, "verified_count": 0,
                    "pending_reviews_count": 0}), "created": True}
        return await run_rehab_transaction(self.db, write)

    async def update(self, plan_id, cycle_id, actor, payload: TrainingCycleUpdate):
        if actor.role not in {"doctor", "health_manager"}:
            raise _error("REHAB_CLINICIAN_REQUIRED", "需要医护设置训练周期权限", 403)
        if not ObjectId.is_valid(cycle_id):
            raise _error("REHAB_TRAINING_CYCLE_NOT_FOUND", "训练周期不存在", 404)
        operation_key = self._operation_key(plan_id, actor, f"update:{cycle_id}", payload.request_id)
        fingerprint = self._fingerprint(payload)
        async def write(session):
            plan = await self._plan(plan_id, session)
            await self.publication._authorize(plan, actor, session, write=True, fence=True)
            prior = await self._prior_operation(operation_key, fingerprint, session)
            if prior:
                current_cycle = await self.cycles.find_one({"_id": cycle_id, "plan_id": str(plan["_id"])}, session=session)
                if not current_cycle:
                    raise _error("REHAB_TRAINING_CYCLE_NOT_FOUND", "训练周期不存在", 404)
                return {"cycle": self._projection(current_cycle, await self._count_cycle_feedback(str(plan["_id"]), current_cycle, session=session)), "updated": False}
            cycle = await self.cycles.find_one({"_id": cycle_id, "plan_id": str(plan["_id"])}, session=session)
            if not cycle:
                raise _error("REHAB_TRAINING_CYCLE_NOT_FOUND", "训练周期不存在", 404)
            counts = await self._count_cycle_feedback(str(plan["_id"]), cycle, session=session)
            today = datetime.now(SHANGHAI).date()
            if cycle.get("status") != "open" or date.fromisoformat(str(cycle["start_date"])) <= today or counts["feedback_count"]:
                raise _error("REHAB_TRAINING_CYCLE_LOCKED", "已开始或已有训练反馈的周期不能修改")
            overlaps = await self.cycles.find_one({"plan_id": str(plan["_id"]), "_id": {"$ne": cycle_id},
                "start_date": {"$lte": payload.end_date.isoformat()},
                "end_date": {"$gte": payload.start_date.isoformat()}}, session=session)
            if overlaps:
                raise _error("REHAB_TRAINING_CYCLE_OVERLAP", "训练周期不能与已有周期重叠")
            if cycle.get("revision", 0) != payload.expected_revision:
                raise _error("REHAB_TRAINING_CYCLE_CONFLICT", "训练周期已变化，请刷新后重试")
            stamp = datetime.now(timezone.utc)
            changes = {"title": payload.title, "start_date": payload.start_date.isoformat(),
                       "end_date": payload.end_date.isoformat(), "revision": payload.expected_revision + 1,
                       "updated_at": stamp}
            result = await self.cycles.update_one({"_id": cycle_id, "plan_id": str(plan["_id"]),
                "revision": payload.expected_revision, "status": "open"}, {"$set": changes}, session=session)
            if result.matched_count != 1:
                raise _error("REHAB_TRAINING_CYCLE_CONFLICT", "训练周期已变化，请刷新后重试")
            await self.publication._touch_plan(plan, session)
            await self._record_operation(operation_key, fingerprint, str(plan["_id"]), actor, cycle_id, session)
            return {"cycle": self._projection({**cycle, **changes}, counts), "updated": True}
        return await run_rehab_transaction(self.db, write)

    async def accept(self, plan_id, cycle_id, actor, payload: TrainingCycleAcceptance):
        if actor.role not in {"doctor", "health_manager"}:
            raise _error("REHAB_CLINICIAN_REQUIRED", "需要医护验收训练周期权限", 403)
        if not ObjectId.is_valid(cycle_id):
            raise _error("REHAB_TRAINING_CYCLE_NOT_FOUND", "训练周期不存在", 404)
        operation_key = self._operation_key(plan_id, actor, f"accept:{cycle_id}", payload.request_id)
        fingerprint = self._fingerprint(payload)
        async def write(session):
            plan = await self._plan(plan_id, session)
            await self.publication._authorize(plan, actor, session, write=True, fence=True)
            prior = await self._prior_operation(operation_key, fingerprint, session)
            if prior:
                current_cycle = await self.cycles.find_one({"_id": cycle_id, "plan_id": str(plan["_id"])}, session=session)
                if not current_cycle:
                    raise _error("REHAB_TRAINING_CYCLE_NOT_FOUND", "训练周期不存在", 404)
                return {"cycle": self._projection(current_cycle, await self._count_cycle_feedback(str(plan["_id"]), current_cycle, session=session)), "created": False}
            cycle = await self.cycles.find_one({"_id": cycle_id, "plan_id": str(plan["_id"])}, session=session)
            if not cycle:
                raise _error("REHAB_TRAINING_CYCLE_NOT_FOUND", "训练周期不存在", 404)
            if cycle.get("status") == "accepted":
                return {"cycle": self._projection(cycle, await self._count_cycle_feedback(str(plan["_id"]), cycle, session=session)), "created": False}
            if cycle.get("revision", 0) != payload.expected_revision:
                raise _error("REHAB_TRAINING_CYCLE_CONFLICT", "训练周期已变化，请刷新后重试")
            if datetime.now(SHANGHAI).date() <= date.fromisoformat(str(cycle["end_date"])):
                raise _error("REHAB_TRAINING_CYCLE_NOT_ENDED", "训练周期最后一天结束后才能统一验收")
            counts = await self._count_cycle_feedback(str(plan["_id"]), cycle, session=session)
            if counts["pending_reviews_count"]:
                raise _error("REHAB_TRAINING_CYCLE_REVIEWS_PENDING", "请先核验完周期内所有已执行或部分执行的训练视频", 409,
                    details=counts)
            stamp = datetime.now(timezone.utc)
            acceptance = {"status": "accepted", "note": payload.note,
                "accepted_at": stamp, "accepted_by": str(actor.id),
                "reviewed_feedback_count": counts["feedback_count"],
                "verified_feedback_count": counts["verified_count"],
                "reviewed_feedback": counts["reviewed_feedback"]}
            result = await self.cycles.update_one({"_id": cycle_id, "plan_id": str(plan["_id"]),
                "status": "open", "revision": payload.expected_revision},
                {"$set": {"status": "accepted", "acceptance": acceptance,
                          "revision": payload.expected_revision + 1, "updated_at": stamp}}, session=session)
            if result.matched_count != 1:
                raise _error("REHAB_TRAINING_CYCLE_CONFLICT", "训练周期状态已变化，请刷新后重试")
            # Touch same plan document used by feedback submission. Transaction write conflict
            # serializes acceptance against any in-flight report or review.
            await self.publication._touch_plan(plan, session)
            await self._record_operation(operation_key, fingerprint, str(plan["_id"]), actor, cycle_id, session)
            updated = {**cycle, "status": "accepted", "acceptance": acceptance,
                       "revision": payload.expected_revision + 1, "updated_at": stamp}
            return {"cycle": self._projection(updated, counts), "created": True}
        return await run_rehab_transaction(self.db, write)
