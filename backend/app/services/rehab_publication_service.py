"""Structured clinical drafts and immutable patient-visible versions.

The existing version/item collections own prescription content. Legacy raw
plans and exercises are never silently promoted into patient instructions.
"""
import hashlib
from copy import deepcopy
from datetime import datetime, timezone

from bson import ObjectId, json_util
from pymongo.errors import PyMongoError, DuplicateKeyError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern
from pydantic import ValidationError

from app.core.exceptions import AppBaseException
from app.schemas.rehab_publication import PublicationContent, PublicationItem

WORKFLOW = "patient_publication"
OPERATIONS = "rehab_publication_operations"


def error(code, message, status=409):
    return AppBaseException(message, status_code=status, error_code=code)


async def run_rehab_transaction(db, callback):
    try:
        async with await db.client.start_session() as session:
            return await session.with_transaction(callback, read_concern=ReadConcern("snapshot"),
                                                  write_concern=WriteConcern("majority"))
    except AppBaseException:
        raise
    except PyMongoError as exc:
        raise error("REHAB_TRANSACTION_UNAVAILABLE", "康复事务未能确认提交，请使用相同请求重试", 503) from exc


def now_utc():
    stamp = datetime.now(timezone.utc).replace(tzinfo=None)
    return stamp.replace(microsecond=(stamp.microsecond // 1000) * 1000)


def utc_iso(value):
    if not isinstance(value, datetime):
        raise error("REHAB_PUBLICATION_INVALID", "已发布方案时间结构异常", 503)
    return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.astimezone(timezone.utc).isoformat()


def public_content(snapshot):
    if not isinstance(snapshot, dict):
        raise error("REHAB_PUBLICATION_INVALID", "康复方案内容结构异常", 503)
    keys = ("name", "description", "goal", "start_date", "end_date", "frequency", "patient_instructions")
    result = {key: deepcopy(snapshot[key]) for key in keys if key in snapshot}
    for key in ("start_date", "end_date"):
        if result.get(key) is not None:
            result[key] = utc_iso(result[key])
    try:
        return PublicationContent.model_validate(result).model_dump(mode="json", exclude_none=True)
    except ValidationError:
        raise error("REHAB_PUBLICATION_INVALID", "康复方案内容结构异常", 503) from None


def public_item(item):
    # Validation is also a projection: no raw metadata, history or account data.
    keys = PublicationItem.model_fields
    try:
        value = PublicationItem.model_validate({key: value for key, value in item.items() if key in keys})
        if not value.item_id:
            raise ValueError("missing item identity")
        return value.model_dump(exclude_none=True)
    except (ValidationError, ValueError, AttributeError):
        raise error("REHAB_PUBLICATION_INVALID", "康复处方内容结构异常", 503) from None


class RehabPublicationService:
    def __init__(self, db):
        self.db = db
        self.plans = db.rehab_plans
        self.versions = db.rehab_plan_versions
        self.items = db.rehab_prescription_items
        self.operations = db[OPERATIONS]

    async def quality_process_snapshot(self, patient_ids, **options):
        """Read current publication facts without exposing draft content."""
        from app.services.quality_process_queries import monitoring_pipeline
        rows = await self.plans.aggregate(monitoring_pipeline("rehab_plan", patient_ids,
            versions_collection=self.versions.name, **options)).to_list(length=1)
        return rows[0] if rows else {}

    @staticmethod
    def _clinical_writer(actor):
        if actor.role not in {"doctor", "health_manager"}:
            raise error("REHAB_CLINICIAN_REQUIRED", "需要医护确认权限", 403)

    async def ensure_storage(self):
        hello = await self.db.client.admin.command("hello")
        if not hello.get("setName"):
            raise error("REHAB_TRANSACTIONS_REQUIRED", "康复发布需要 MongoDB 副本集事务", 503)
        await self.versions.create_index([("plan_id", 1), ("version_no", 1)], unique=True,
                                        name="rehab_plan_version_number_unique")
        await self.items.create_index([("version_id", 1), ("item_id", 1)], unique=True,
                                     name="rehab_version_item_unique")

    async def _legacy(self, session):
        if await self.db.patient_domain_state.find_one({"_id": "clinical-patients-v1"}, session=session):
            raise error("REHAB_PATIENT_DOMAIN_UNSUPPORTED", "当前患者档案尚未接入康复账号解析", 503)

    async def _account(self, identifier, session):
        keys = [str(identifier)]
        if ObjectId.is_valid(str(identifier)):
            keys.append(ObjectId(str(identifier)))
        rows = await self.db.users.find({"_id": {"$in": keys}}, session=session).to_list(length=2)
        return rows[0] if len(rows) == 1 else None

    async def _access_fence(self, document, session):
        value = document.get("_access_fence", 0)
        if type(value) is not int or value < 0:
            raise error("REHAB_ACCESS_FENCE_INVALID", "账号并发状态异常", 503)
        await self.db.users.update_one({"_id": document["_id"]}, {"$inc": {"_access_fence": 1}}, session=session)

    async def _authorize(self, plan, actor, session, *, write=False, fence=False):
        await self._legacy(session)
        account = await self._account(str(actor.id), session)
        if not account or account.get("is_active") is not True or account.get("role") != actor.role:
            raise error("REHAB_ACCOUNT_UNAVAILABLE", "当前账号不可用", 403)
        patient = await self._account(str(plan.get("patient_id", "")), session)
        if not patient or patient.get("is_active") is not True or patient.get("role") != "patient":
            raise error("REHAB_PATIENT_UNAVAILABLE", "患者档案不可用", 404)
        if actor.role == "patient":
            if write or str(patient["_id"]) != str(account["_id"]):
                raise error("REHAB_PATIENT_FORBIDDEN", "无权访问该患者的康复方案", 403)
        elif actor.role in {"doctor", "health_manager"}:
            field = "practitioners" if actor.role == "doctor" else "health_managers"
            assigned = patient.get(field)
            if not isinstance(assigned, list) or str(account["_id"]) not in {str(value) for value in assigned}:
                raise error("REHAB_PATIENT_NOT_ASSIGNED", "当前未分配管理该患者", 403)
        elif actor.role != "admin" or write:
            raise error("REHAB_CLINICIAN_REQUIRED", "需要医护确认权限", 403)
        if fence:
            await self._access_fence(account, session)
            if account["_id"] != patient["_id"]:
                await self._access_fence(patient, session)
        return patient

    async def _plan(self, plan_id, session):
        if not ObjectId.is_valid(plan_id):
            raise error("REHAB_PLAN_NOT_FOUND", "康复方案不存在", 404)
        plan = await self.plans.find_one({"_id": ObjectId(plan_id)}, session=session)
        if not plan or not plan.get("patient_id"):
            raise error("REHAB_PLAN_NOT_FOUND", "康复方案不存在", 404)
        return plan

    async def _touch_plan(self, plan, session, *, changes=None):
        guard = plan.get("_publication_fence", 0)
        if type(guard) is not int or guard < 0:
            raise error("REHAB_PUBLICATION_INVALID", "康复方案并发状态异常", 503)
        update = {"$inc": {"_publication_fence": 1}}
        if changes:
            update["$set"] = changes
        result = await self.plans.update_one({"_id": plan["_id"]}, update, session=session)
        if result.matched_count != 1:
            raise error("REHAB_PLAN_CONFLICT", "康复方案已变化，请重新读取")

    def _operation(self, plan_id, actor, kind, payload):
        identity = [plan_id, str(actor.id), payload.request_id]
        key = hashlib.sha256(json_util.dumps(identity).encode()).hexdigest()
        fingerprint = hashlib.sha256(json_util.dumps([kind, payload.model_dump(mode="json")], sort_keys=True).encode()).hexdigest()
        return key, fingerprint

    async def _prior(self, key, fingerprint, session):
        previous = await self.operations.find_one({"_id": key}, session=session)
        if previous and previous["fingerprint"] != fingerprint:
            raise error("REHAB_IDEMPOTENCY_CONFLICT", "相同请求标识不能提交不同内容")
        return previous

    async def _record_operation(self, key, fingerprint, kind, plan_id, actor, result, session):
        await self.operations.insert_one({"_id": key, "fingerprint": fingerprint, "kind": kind,
            "plan_id": plan_id, "actor_id": str(actor.id), "at": now_utc(), "result": result}, session=session)

    async def _run(self, callback):
        for attempt in range(3):
            try:
                return await run_rehab_transaction(self.db, callback)
            except AppBaseException as exc:
                if not isinstance(exc.__cause__, DuplicateKeyError) or attempt == 2:
                    raise

    async def _draft_response(self, plan, session):
        identifier = plan.get("active_draft_version_id")
        draft = None
        if identifier:
            if not isinstance(identifier, str) or not ObjectId.is_valid(identifier):
                raise error("REHAB_DRAFT_INVALID", "康复草稿引用异常", 503)
            version = await self.versions.find_one({"_id": ObjectId(identifier), "plan_id": str(plan["_id"]),
                "workflow": WORKFLOW, "status": "draft"}, session=session)
            if not version:
                raise error("REHAB_DRAFT_INVALID", "康复草稿引用异常", 503)
            entries = await self.items.find({"version_id": identifier, "plan_id": str(plan["_id"])} , session=session).sort("position", 1).to_list(length=201)
            draft = {"id": identifier, "revision": version["draft_revision"], "version_no": version["version_no"],
                     "content": public_content(version["snapshot"]), "items": [public_item(item) for item in entries]}
        published = None
        if plan.get("published_version_id") and plan.get("status") not in {"cancelled", "canceled", "archived"}:
            published = self._patient_projection(plan, await self._published(plan, session))
        return {"plan_id": str(plan["_id"]), "draft": draft, "published": published,
                "published_version_id": plan.get("published_version_id"),
                "publication_revision": plan.get("publication_revision", 0),
                "has_publication_history": plan.get("has_publication_history") is True}

    async def draft(self, plan_id, actor):
        async def read(session):
            plan = await self._plan(plan_id, session)
            if actor.role == "patient":
                raise error("REHAB_CLINICIAN_REQUIRED", "患者不能读取医护草稿", 403)
            await self._authorize(plan, actor, session)
            return await self._draft_response(plan, session)
        return await run_rehab_transaction(self.db, read)

    async def save_draft(self, plan_id, actor, payload):
        self._clinical_writer(actor)
        await self.ensure_storage()
        key, fingerprint = self._operation(plan_id, actor, "save_draft", payload)
        async def save(session):
            plan = await self._plan(plan_id, session)
            await self._authorize(plan, actor, session, write=True, fence=True)
            if await self._prior(key, fingerprint, session):
                return await self._draft_response(plan, session)
            identifier = plan.get("active_draft_version_id")
            if identifier != payload.expected_draft_id:
                raise error("REHAB_DRAFT_CONFLICT", "康复草稿已变化，请重新读取")
            existing = None
            if identifier:
                existing = await self.versions.find_one({"_id": ObjectId(identifier), "plan_id": plan_id,
                    "workflow": WORKFLOW, "status": "draft", "draft_revision": payload.expected_draft_revision}, session=session)
                if not existing:
                    raise error("REHAB_DRAFT_CONFLICT", "康复草稿已变化，请重新读取")
            previous_items = await self.items.find({"version_id": identifier, "plan_id": plan_id}, session=session).to_list(length=201) if identifier else []
            if not identifier and plan.get("published_version_id"):
                # A new draft is an explicit edit of the current immutable
                # publication. Stable item IDs may cross versions, but only
                # items in that current publication can be carried forward.
                published = await self._published(plan, session)
                previous_items = published["items_snapshot"]
            known = {row["item_id"] for row in previous_items}
            if any(item.item_id and item.item_id not in known for item in payload.items):
                raise error("REHAB_ITEM_MISMATCH", "处方项不属于当前草稿", 422)
            stamp = now_utc()
            if existing:
                revision = existing["draft_revision"] + 1
                await self.versions.update_one({"_id": existing["_id"]}, {"$set": {
                    "snapshot": payload.content.model_dump(), "draft_revision": revision, "updated_at": stamp}}, session=session)
            else:
                last = await self.versions.find_one({"plan_id": plan_id}, sort=[("version_no", -1)], session=session)
                number = last.get("version_no", 0) + 1 if last else 1
                identifier = str(ObjectId())
                revision = 0
                await self.versions.insert_one({"_id": ObjectId(identifier), "plan_id": plan_id,
                    "patient_id": str(plan["patient_id"]), "workflow": WORKFLOW, "status": "draft",
                    "version_no": number, "draft_revision": revision, "snapshot": payload.content.model_dump(),
                    "created_by": str(actor.id), "created_at": stamp, "updated_at": stamp}, session=session)
            await self.items.delete_many({"plan_id": plan_id, "version_id": identifier}, session=session)
            docs = []
            for position, item in enumerate(payload.items):
                entry = item.model_dump(exclude_none=True)
                entry["item_id"] = item.item_id or str(ObjectId())
                docs.append({**entry, "plan_id": plan_id, "version_id": identifier,
                    "patient_id": str(plan["patient_id"]), "position": position,
                    "created_by": str(actor.id), "created_at": stamp})
            if docs:
                await self.items.insert_many(docs, session=session)
            await self.versions.update_one({"_id": ObjectId(identifier)}, {"$set": {"item_ids": [row["item_id"] for row in docs]}}, session=session)
            await self._touch_plan(plan, session, changes={"active_draft_version_id": identifier})
            plan["active_draft_version_id"] = identifier
            result = await self._draft_response(plan, session)
            await self._record_operation(key, fingerprint, "save_draft", plan_id, actor,
                                         {"draft_id": identifier, "revision": revision}, session)
            return result
        return await self._run(save)

    def _patient_projection(self, plan, version):
        return {"id": str(plan["_id"]), "version_id": str(version["_id"]),
                "publication_revision": version["publication_revision"],
                "published_at": utc_iso(version["published_at"]),
                "content": public_content(version["snapshot"]),
                "items": [public_item(item) for item in version["items_snapshot"]]}

    async def _published(self, plan, session):
        if plan.get("status") in {"cancelled", "canceled", "archived"}:
            raise error("REHAB_PUBLICATION_NOT_FOUND", "该康复方案已停止展示", 404)
        identifier = plan.get("published_version_id")
        if not identifier or not ObjectId.is_valid(identifier):
            raise error("REHAB_PUBLICATION_NOT_FOUND", "尚无可查看的已发布康复方案", 404)
        version = await self.versions.find_one({"_id": ObjectId(identifier), "plan_id": str(plan["_id"]),
            "patient_id": str(plan["patient_id"]), "workflow": WORKFLOW, "status": "published"}, session=session)
        if not version:
            raise error("REHAB_PUBLICATION_NOT_FOUND", "已发布康复方案不可用", 404)
        return version

    async def patient_detail(self, plan_id, actor):
        async def read(session):
            plan = await self._plan(plan_id, session)
            await self._authorize(plan, actor, session)
            return self._patient_projection(plan, await self._published(plan, session))
        return await run_rehab_transaction(self.db, read)

    async def patient_list(self, actor, *, skip=0, limit=20):
        async def read(session):
            if actor.role != "patient":
                raise error("REHAB_PATIENT_REQUIRED", "需要患者本人账号", 403)
            await self._authorize({"patient_id": str(actor.id)}, actor, session)
            query = {"patient_id": str(actor.id), "published_version_id": {"$type": "string"},
                     "status": {"$nin": ["cancelled", "canceled", "archived"]}}
            rows = await self.plans.find(query, session=session).sort([("published_at", -1), ("_id", -1)]).skip(skip).limit(limit).to_list(length=limit)
            values = [self._patient_projection(row, await self._published(row, session)) for row in rows]
            return {"items": values, "total": await self.plans.count_documents(query, session=session), "skip": skip, "limit": limit}
        return await run_rehab_transaction(self.db, read)

    async def publish(self, plan_id, actor, payload):
        self._clinical_writer(actor)
        await self.ensure_storage()
        key, fingerprint = self._operation(plan_id, actor, "publish", payload)
        async def publish(session):
            plan = await self._plan(plan_id, session)
            await self._authorize(plan, actor, session, write=True, fence=True)
            if plan.get("status") in {"cancelled", "canceled", "archived"}:
                raise error("REHAB_PUBLICATION_STOPPED", "已取消或归档的方案不能发布", 409)
            prior = await self._prior(key, fingerprint, session)
            if prior:
                version = await self.versions.find_one({"_id": ObjectId(prior["result"]["version_id"]), "plan_id": plan_id}, session=session)
                return self._patient_projection(plan, version)
            if plan.get("published_version_id") != payload.expected_publication_id or plan.get("active_draft_version_id") != payload.draft_id:
                raise error("REHAB_PUBLICATION_CONFLICT", "草稿或已发布版本已变化，请重新读取")
            version = await self.versions.find_one({"_id": ObjectId(payload.draft_id), "plan_id": plan_id,
                "workflow": WORKFLOW, "status": "draft", "draft_revision": payload.expected_draft_revision}, session=session)
            if not version:
                raise error("REHAB_DRAFT_CONFLICT", "康复草稿已变化，请重新读取")
            entries = await self.items.find({"version_id": payload.draft_id, "plan_id": plan_id}, session=session).sort("position", 1).to_list(length=201)
            if not entries or len(entries) > 200:
                raise error("REHAB_ITEMS_REQUIRED", "发布前请明确填写至少一项干预内容", 422)
            snapshot_items = [public_item(item) for item in entries]
            stamp = now_utc()
            revision = plan.get("publication_revision", 0)
            if type(revision) is not int or revision < 0:
                raise error("REHAB_PUBLICATION_INVALID", "发布修订号异常", 503)
            revision += 1
            await self.versions.update_one({"_id": version["_id"]}, {"$set": {
                "status": "published", "items_snapshot": snapshot_items,
                "published_by": str(actor.id), "published_at": stamp, "publication_revision": revision,
                "confirmation_note": payload.confirmation_note, "updated_at": stamp}}, session=session)
            await self._touch_plan(plan, session, changes={"published_version_id": payload.draft_id,
                "active_draft_version_id": None, "has_publication_history": True,
                "publication_revision": revision, "published_at": stamp})
            version.update(status="published", items_snapshot=snapshot_items, published_at=stamp, publication_revision=revision)
            await self._record_operation(key, fingerprint, "publish", plan_id, actor,
                                         {"version_id": payload.draft_id}, session)
            return self._patient_projection(plan, version)
        return await self._run(publish)

    async def withdraw(self, plan_id, actor, payload):
        self._clinical_writer(actor)
        await self.ensure_storage()
        key, fingerprint = self._operation(plan_id, actor, "withdraw", payload)
        async def withdraw(session):
            plan = await self._plan(plan_id, session)
            await self._authorize(plan, actor, session, write=True, fence=True)
            prior = await self._prior(key, fingerprint, session)
            if prior:
                return prior["result"]
            if plan.get("published_version_id") != payload.expected_publication_id:
                raise error("REHAB_PUBLICATION_CONFLICT", "已发布版本已变化，请重新读取")
            version = await self._published(plan, session)
            stamp = now_utc()
            await self.versions.update_one({"_id": version["_id"]}, {"$set": {
                "status": "withdrawn", "withdrawn_by": str(actor.id), "withdrawn_at": stamp,
                "withdrawal_reason": payload.reason, "withdrawal_action": payload.action}}, session=session)
            changes = {"published_version_id": None,
                "publication_revision": plan.get("publication_revision", 0) + 1}
            if payload.action != "withdraw":
                changes["status"] = "cancelled" if payload.action == "cancel" else "archived"
            await self._touch_plan(plan, session, changes=changes)
            result = {"plan_id": plan_id, "withdrawn_version_id": str(version["_id"]),
                      "status": "withdrawn", "action": payload.action}
            await self._record_operation(key, fingerprint, "withdraw", plan_id, actor, result, session)
            return result
        return await self._run(withdraw)
