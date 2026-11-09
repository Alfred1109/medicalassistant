"""Manual process quality issue workflow with current patient authorization.

Human entries record a reviewable concern; this service computes no clinical
abnormality. Every mutation and its idempotency receipt commit together.
"""
import hashlib
from datetime import datetime, timezone

from bson import ObjectId, json_util
from pymongo.errors import DuplicateKeyError, PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from app.core.exceptions import AppBaseException
from app.core.patient_access import assigned_patient_query, patient_assignment_field
from app.core.patient_identity import identity_key, load_identity_groups
from app.services.followup_service import FollowupService
from app.services.rehabilitation_service import RehabilitationService

ISSUES = "quality_issues"
OPERATIONS = "quality_issue_operations"
CLINICAL_ROLES = {"doctor", "health_manager"}
READ_ROLES = CLINICAL_ROLES | {"admin"}


def fail(code, message, status=409):
    return AppBaseException(message, status_code=status, error_code=code)


def stamp():
    value = datetime.now(timezone.utc).replace(tzinfo=None)
    return value.replace(microsecond=value.microsecond // 1000 * 1000)


def iso(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.astimezone(timezone.utc).isoformat()


async def transaction(db, callback):
    try:
        async with await db.client.start_session() as session:
            return await session.with_transaction(callback, read_concern=ReadConcern("snapshot"),
                                                   write_concern=WriteConcern("majority"))
    except AppBaseException:
        raise
    except PyMongoError as exc:
        raise fail("QUALITY_TRANSACTION_UNAVAILABLE", "质控事务未能确认提交，请使用相同请求重试", 503) from exc


def issue_view(document, *, detail=True):
    keys = ("patient_id", "source_type", "source_id", "title", "description", "status", "version",
            "assignee_id", "created_by")
    result = {key: document.get(key) for key in keys}
    result.update(id=str(document["_id"]), created_at=iso(document["created_at"]), updated_at=iso(document["updated_at"]))
    if detail:
        result.update(evidence_refs=document.get("evidence_refs", []), resolution=document.get("resolution"),
                      timeline=[{**entry, "at": iso(entry["at"])} for entry in document.get("timeline", [])])
    return result


class QualityIssueService:
    def __init__(self, db):
        self.db = db
        self.issues = db[ISSUES]
        self.operations = db[OPERATIONS]

    async def ensure_storage(self):
        try:
            hello = await self.db.client.admin.command("hello")
            if not hello.get("setName"):
                raise fail("QUALITY_TRANSACTIONS_REQUIRED", "人工质控处置需要 MongoDB 副本集事务", 503)
            await self.issues.create_index([("patient_id", 1), ("status", 1), ("updated_at", -1)], name="quality_patient_status")
        except AppBaseException:
            raise
        except PyMongoError as exc:
            raise fail("QUALITY_STORAGE_UNAVAILABLE", "质控存储暂不可用", 503) from exc

    async def _account(self, identifier, session=None):
        groups = await load_identity_groups(self.db, [identifier], session=session)
        documents = groups.get(identity_key(identifier), [])
        return documents[0] if len(documents) == 1 else None

    async def _fence(self, document, session):
        value = document.get("_access_fence", 0)
        if type(value) is not int or value < 0:
            raise fail("QUALITY_ACCESS_FENCE_INVALID", "账号并发状态异常", 503)
        await self.db.users.update_one({"_id": document["_id"]}, {"$inc": {"_access_fence": 1}}, session=session)

    async def _actor(self, actor, session=None, *, write=False):
        if actor.role not in (CLINICAL_ROLES if write else READ_ROLES):
            raise fail("QUALITY_CLINICAL_ROLE_REQUIRED", "需要当前医护权限", 403)
        account = await self._account(actor.id, session)
        if not account or account.get("role") != actor.role or account.get("is_active") is not True:
            raise fail("QUALITY_ACCOUNT_UNAVAILABLE", "当前账号不可用", 403)
        if await self.db.patient_domain_state.find_one({"_id": "clinical-patients-v1"}, session=session):
            raise fail("QUALITY_PATIENT_DOMAIN_UNSUPPORTED", "当前患者档案尚未接入质控授权", 503)
        return account

    async def _patient(self, patient_id, actor, session=None, *, write=False, fence=False):
        account = await self._actor(actor, session, write=write)
        patient = await self._account(patient_id, session)
        if not patient or patient.get("role") != "patient" or patient.get("is_active") is not True:
            raise fail("QUALITY_PATIENT_UNAVAILABLE", "患者档案不可用", 404)
        if actor.role != "admin":
            values = patient.get(patient_assignment_field(actor.role))
            if not isinstance(values, list) or str(account["_id"]) not in {str(value) for value in values}:
                raise fail("QUALITY_PATIENT_NOT_ASSIGNED", "当前未分配管理该患者", 403)
        if fence:
            await self._fence(account, session)
            await self._fence(patient, session)
        return patient

    async def _source(self, patient_id, source_type, source_id, session):
        service = FollowupService(self.db) if source_type == "followup" else RehabilitationService(self.db)
        document = await service.quality_source(source_id, session=session)
        if not document or document.get("deleted") or str(document.get("patient_id")) != patient_id:
            raise fail("QUALITY_SOURCE_MISMATCH", "关联来源不存在或不属于该患者", 404)
        await service.fence_quality_source(document, session)

    async def _document(self, identifier, session=None):
        if not ObjectId.is_valid(str(identifier)):
            raise fail("QUALITY_ISSUE_NOT_FOUND", "质控问题不存在", 404)
        document = await self.issues.find_one({"_id": ObjectId(identifier)}, session=session)
        if not document:
            raise fail("QUALITY_ISSUE_NOT_FOUND", "质控问题不存在", 404)
        return document

    def _operation(self, actor, kind, payload, issue_id=None):
        identity = [str(actor.id), issue_id or "create", payload.request_id]
        key = hashlib.sha256(json_util.dumps(identity).encode()).hexdigest()
        fingerprint = hashlib.sha256(json_util.dumps([kind, payload.model_dump(mode="json")], sort_keys=True).encode()).hexdigest()
        return key, fingerprint

    async def _receipt(self, key, fingerprint, session):
        previous = await self.operations.find_one({"_id": key}, session=session)
        if previous and previous.get("fingerprint") != fingerprint:
            raise fail("QUALITY_IDEMPOTENCY_CONFLICT", "相同请求标识不能用于不同内容")
        return previous

    async def _write_receipt(self, key, fingerprint, issue, actor, kind, session):
        await self.operations.insert_one({"_id": key, "fingerprint": fingerprint, "issue_id": str(issue["_id"]),
            "actor_id": str(actor.id), "kind": kind, "at": stamp()}, session=session)

    async def _run(self, callback):
        for attempt in range(3):
            try:
                return await transaction(self.db, callback)
            except AppBaseException as exc:
                if not isinstance(exc.__cause__, DuplicateKeyError) or attempt == 2:
                    raise

    async def create(self, payload, actor):
        await self.ensure_storage()
        key, fingerprint = self._operation(actor, "create", payload)
        async def create(session):
            await self._patient(payload.patient_id, actor, session, write=True, fence=True)
            previous = await self._receipt(key, fingerprint, session)
            if previous:
                return issue_view(await self._document(previous["issue_id"], session)), False
            await self._source(payload.patient_id, payload.source_type, payload.source_id, session)
            now = stamp()
            document = {"_id": ObjectId(), **payload.model_dump(exclude={"request_id"}),
                "status": "open", "version": 0, "assignee_id": None, "created_by": str(actor.id),
                "created_at": now, "updated_at": now, "resolution": None,
                "timeline": [{"action": "create", "actor_id": str(actor.id), "at": now,
                    "note": payload.description, "evidence_refs": payload.evidence_refs,
                    "from_status": None, "to_status": "open", "version": 0}]}
            await self.issues.insert_one(document, session=session)
            await self._write_receipt(key, fingerprint, document, actor, "create", session)
            return issue_view(document), True
        return await self._run(create)

    async def _assignee(self, identifier, patient, session):
        account = await self._account(identifier, session)
        if not account or account.get("role") not in CLINICAL_ROLES or account.get("is_active") is not True:
            raise fail("QUALITY_ASSIGNEE_UNAVAILABLE", "责任医护账号不可用", 422)
        assigned = patient.get(patient_assignment_field(account["role"]))
        if not isinstance(assigned, list) or str(account["_id"]) not in {str(item) for item in assigned}:
            raise fail("QUALITY_ASSIGNEE_NOT_ASSIGNED", "责任医护当前未分配管理该患者", 422)
        await self._fence(account, session)
        return str(account["_id"])

    async def mutate(self, issue_id, kind, payload, actor):
        await self.ensure_storage()
        key, fingerprint = self._operation(actor, kind, payload, issue_id)
        async def mutate(session):
            document = await self._document(issue_id, session)
            patient = await self._patient(document["patient_id"], actor, session, write=True, fence=True)
            if await self._receipt(key, fingerprint, session):
                return issue_view(document)
            if document["version"] != payload.expected_version:
                raise fail("QUALITY_VERSION_CONFLICT", "质控问题已变化，请刷新后操作")
            before = document["status"]
            changes = {}
            event = {"action": kind, "actor_id": str(actor.id), "at": stamp(), "from_status": before,
                     "version": document["version"] + 1}
            if kind == "assign":
                if before not in {"open", "in_progress"}:
                    raise fail("QUALITY_STATE_CONFLICT", "当前状态不能重新分配")
                changes.update(assignee_id=await self._assignee(payload.assignee_id, patient, session), status="open")
                event.update(note=payload.note, assignee_id=changes["assignee_id"])
            elif kind in {"confirm", "resolve"}:
                if document.get("assignee_id") != str(actor.id):
                    raise fail("QUALITY_ASSIGNEE_REQUIRED", "仅当前责任医护可以执行此操作", 403)
                if kind == "confirm":
                    if before != "open":
                        raise fail("QUALITY_STATE_CONFLICT", "仅待确认问题可以确认")
                    changes["status"] = "in_progress"
                    event["note"] = payload.note
                else:
                    if before != "in_progress":
                        raise fail("QUALITY_STATE_CONFLICT", "仅处理中问题可以提交处置")
                    changes.update(status="pending_review", resolution=payload.resolution)
                    event.update(note=payload.resolution, evidence_refs=payload.evidence_refs)
            elif kind == "review":
                if before != "pending_review":
                    raise fail("QUALITY_STATE_CONFLICT", "仅待复核问题可以复核")
                changes["status"] = "closed" if payload.decision == "approve" else "in_progress"
                event.update(note=payload.note, evidence_refs=payload.evidence_refs, decision=payload.decision)
            else:
                raise fail("QUALITY_ACTION_INVALID", "质控操作无效", 422)
            event["to_status"] = changes["status"]
            result = await self.issues.update_one({"_id": document["_id"], "version": payload.expected_version},
                {"$set": {**changes, "updated_at": event["at"]}, "$inc": {"version": 1}, "$push": {"timeline": event}}, session=session)
            if result.matched_count != 1:
                raise fail("QUALITY_VERSION_CONFLICT", "质控问题已变化，请刷新后操作")
            document.update(changes, version=document["version"] + 1, updated_at=event["at"])
            document["timeline"].append(event)
            await self._write_receipt(key, fingerprint, document, actor, kind, session)
            return issue_view(document)
        return await self._run(mutate)

    async def detail(self, issue_id, actor):
        document = await self._document(issue_id)
        await self._patient(document["patient_id"], actor)
        return issue_view(document)

    async def list(self, actor, *, patient_id=None, status=None, assignee_id=None, skip=0, limit=20):
        await self._actor(actor)
        if skip < 0 or not 1 <= limit <= 100:
            raise fail("QUALITY_PAGINATION_INVALID", "分页参数无效", 422)
        query = {}
        if patient_id:
            await self._patient(patient_id, actor)
            query["patient_id"] = patient_id
        else:
            patient_scope = ({"role": "patient"} if actor.role == "admin" else
                             assigned_patient_query(str(actor.id), actor.role))
            patients = await self.db.users.find({**patient_scope, "is_active": True}, {"_id": 1}).to_list(length=None)
            candidate_ids = {str(item["_id"]) for item in patients}
            groups = await load_identity_groups(self.db, candidate_ids,
                projection={"role": 1, "is_active": 1, "practitioners": 1, "health_managers": 1})
            identifiers = []
            for identifier in candidate_ids:
                # ObjectId and string account keys can have the same visible
                # value. Resolve them in one batch, never an N+1 patient loop.
                matches = groups.get(identity_key(identifier), [])
                if len(matches) != 1:
                    raise fail("QUALITY_PATIENT_IDENTITY_AMBIGUOUS", "患者身份无法唯一核实，请联系管理员核查", 503)
                patient = matches[0]
                if patient.get("role") != "patient" or patient.get("is_active") is not True:
                    continue
                if actor.role != "admin":
                    assignments = patient.get(patient_assignment_field(actor.role))
                    if not isinstance(assignments, list) or str(actor.id) not in {str(value) for value in assignments}:
                        continue
                identifiers.append(identifier)
            query["patient_id"] = {"$in": identifiers}
        if status:
            query["status"] = status
        if assignee_id:
            query["assignee_id"] = assignee_id
        result = await self.issues.aggregate([{"$match": query}, {"$sort": {"updated_at": -1, "_id": -1}},
            {"$facet": {"items": [{"$skip": skip}, {"$limit": limit}], "count": [{"$count": "total"}]}}]).to_list(length=1)
        page = result[0] if result else {"items": [], "count": []}
        return {"items": [issue_view(item, detail=False) for item in page["items"]],
                "total": page["count"][0]["total"] if page["count"] else 0, "skip": skip, "limit": limit}

    async def assignees(self, patient_id, actor):
        patient = await self._patient(patient_id, actor)
        identifiers = list({str(item) for field in ("practitioners", "health_managers") for item in (patient.get(field) or [])})
        groups = await load_identity_groups(self.db, identifiers,
            projection={"name": 1, "role": 1, "is_active": 1})
        output = []
        for key in {identity_key(identifier) for identifier in identifiers}:
            documents = groups.get(key, [])
            account = documents[0] if len(documents) == 1 else None
            if account and account.get("is_active") is True and account.get("role") in CLINICAL_ROLES:
                field = patient_assignment_field(account["role"])
                if str(account["_id"]) in {str(item) for item in (patient.get(field) or [])}:
                    output.append({"id": str(account["_id"]), "name": account.get("name") or str(account["_id"]), "role": account["role"]})
        return {"items": sorted(output, key=lambda item: (item["name"], item["id"]))}
