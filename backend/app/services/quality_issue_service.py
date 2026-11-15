"""Manual process quality issue workflow with current patient authorization.

Human entries record a reviewable concern; this service computes no clinical
abnormality. Every mutation and its idempotency receipt commit together.
"""
import hashlib
from datetime import datetime, timezone

from bson import ObjectId, json_util
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.exceptions import AppBaseException
from app.core.fences import AccountFenceStore, PatientFenceStore, dual_bump, legacy_document_fence
from app.db.transactions import run_transaction
from app.core.patient_access import (PatientAccessError, is_domain_state_unavailable,
                                     patient_assignment_field, patient_domain_context)
from app.core.patient_identity import identity_key, load_identity_groups, resolve_unique_account
from app.patients.legacy import LegacyPatientIdentityError
from app.services.followup_service import FollowupService
from app.services.rehabilitation_service import RehabilitationService

ISSUES = "quality_issues"
OPERATIONS = "quality_issue_operations"
CLINICAL_ROLES = {"doctor", "health_manager"}
READ_ROLES = CLINICAL_ROLES | {"admin"}
# 质控问题文档 patient_id 引用语义（T63 波次 2）：沿用迁移「保留主键、值不变」
# 约定——clinical_patients.patient_id = str(legacy users._id)，因此存量质控文档
# 的 patient_id 字符串在 canonical 模式下与 clinical_patients 主键一一对应，
# 切换无需改写历史文档；canonical 下新建质控同样引用当前域的患者 ID
# （新建档患者为 create_from_source 生成的 ObjectId 字符串）。
# 栅栏载体名（波次 2；T67 缺陷 1 域化命名）：canonical 账号跳落
# account_fences（复合键含 fence_name）、患者跳落 clinical_patients 的
# _fence_quality_access 字段（core/fences.py 命名约定）。不与康复发布等域
# 共用泛化名 "access"——同名栅栏会让同一账号/同一患者文档的跨域计数互相
# 污染 CAS 复核，命名直指质控域。
QUALITY_ACCESS_FENCE = "quality_access"


def fail(code, message, status=409):
    return AppBaseException(message, status_code=status, error_code=code)


def stamp():
    value = datetime.now(timezone.utc).replace(tzinfo=None)
    return value.replace(microsecond=value.microsecond // 1000 * 1000)


def iso(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.astimezone(timezone.utc).isoformat()


async def transaction(db, callback):
    return await run_transaction(db, callback,
        error_code="QUALITY_TRANSACTION_UNAVAILABLE",
        error_message="质控事务未能确认提交，请使用相同请求重试")


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
        # 账号身份批量读取两域同源：canonical 只迁患者实体，医护/患者账号
        # （含质控 actor 与被指派责任人的账号域）仍以 users 为载体。
        # （R1-A3 收敛：唯一账号解析迁 core/patient_identity.resolve_unique_account
        # ——identity_key 归组口径与原实现逐字一致，同键多文档返回 None 由
        # 调用方 QUALITY_*_UNAVAILABLE 防护兜住。）
        return await resolve_unique_account(self.db, identifier, session=session)

    async def _fence(self, document, session):
        # legacy 载体（行为不变）：账号与患者实体同文档，users 上一次 $inc
        # 同时覆盖"账号态"与"患者归属"两种语义。canonical 的双载体栅栏
        # （account_fences + clinical_patients._fence_quality_access）在
        # _patient/_assignee 的栅栏跳里按域分派，不经过本方法。
        # （R1-A2 收敛：骨架迁 fences.legacy_document_fence——本调用点无 CAS
        # 复核，账号文档由 _account/_actor 在同事务内核实，行为逐字不变。）
        await legacy_document_fence(self.db.users, document, "_access_fence",
            session=session, error_code="QUALITY_ACCESS_FENCE_INVALID",
            error_message="账号并发状态异常")

    async def _actor(self, actor, session=None, *, write=False):
        if actor.role not in (CLINICAL_ROLES if write else READ_ROLES):
            raise fail("QUALITY_CLINICAL_ROLE_REQUIRED", "需要当前医护权限", 403)
        # 账号复核不依赖患者域开关：canonical 下账号域仍在 users（T63 波次 2
        # 门闩移除，患者域分派由 _patient/load_patient_doc 承担）。
        account = await self._account(actor.id, session)
        if not account or account.get("role") != actor.role or account.get("is_active") is not True:
            raise fail("QUALITY_ACCOUNT_UNAVAILABLE", "当前账号不可用", 403)
        return account

    async def _patient(self, patient_id, actor, session=None, *, write=False, fence=False, context=None):
        account = await self._actor(actor, session, write=write)
        # 域分派一次读取：患者实体读取与栅栏载体分派复用同一上下文。
        if context is None:
            context = await patient_domain_context(self.db, session=session)
        # 患者存在性与身份歧义消解按域分派（内核 load_patient_doc）：
        # legacy 走 legacy 适配器——可见 ID 冲突以适配器的
        # LegacyPatientIdentityError（503）呈现而非 404；canonical 走
        # clinical_patients——患者主键唯一，无歧义防护对应物，status != active
        # 视同不存在。canonical 绝不回读 users（无账号患者也必须可质控），
        # 内核统一的 404 在此映射回本域既有语义码；域状态不可用 503 原样透传。
        try:
            patient = await context.load_patient_doc(patient_id)
        except PatientAccessError as error:
            if is_domain_state_unavailable(error):
                raise
            raise fail("QUALITY_PATIENT_UNAVAILABLE", "患者档案不可用", 404) from None
        # 患者实体可用性策略仍由本域执行：canonical 文档恒带 status，inactive
        # 已由内核统一 404（文档存在即 active）；legacy 文档无 status 字段，
        # is_active 精化校验逐字保留（内核 legacy 分支不代查）。
        if not patient or ("status" not in patient and patient.get("is_active") is not True):
            raise fail("QUALITY_PATIENT_UNAVAILABLE", "患者档案不可用", 404)
        # 归属校验两域同构：clinical_patients 迁移保留原归属列表与账号 ID
        # 字面量，字段名与比较逻辑无需分派。
        if actor.role != "admin":
            values = patient.get(patient_assignment_field(actor.role))
            if not isinstance(values, list) or str(account["_id"]) not in {str(value) for value in values}:
                raise fail("QUALITY_PATIENT_NOT_ASSIGNED", "当前未分配管理该患者", 403)
        if fence:
            # DOMAIN-BRANCH: 栅栏载体按域分派（T63 波次 2；T67 命名域化）——
            # canonical 全量后 legacy 双跳分支可整体删除。legacy 双跳仍写
            # users 载体（行为不变）；canonical 切换双载体——账号跳
            # account_fences、患者跳 clinical_patients._fence_quality_access，
            # 同一事务内经 dual_bump 先后复核，任一跳失败由外层事务整体回滚。
            # domain-dispatch: 迁移完成后可删
            if context.is_canonical:
                await dual_bump(
                    (AccountFenceStore(self.db), str(account["_id"]), QUALITY_ACCESS_FENCE),
                    (PatientFenceStore(self.db), str(patient["patient_id"]), QUALITY_ACCESS_FENCE),
                    session=session)
            else:
                # LEGACY-SHAPE: legacy 载体——账号与患者实体同文档。
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

    async def _assignee(self, identifier, patient, session, *, context=None):
        account = await self._account(identifier, session)
        if not account or account.get("role") not in CLINICAL_ROLES or account.get("is_active") is not True:
            raise fail("QUALITY_ASSIGNEE_UNAVAILABLE", "责任医护账号不可用", 422)
        assigned = patient.get(patient_assignment_field(account["role"]))
        if not isinstance(assigned, list) or str(account["_id"]) not in {str(item) for item in assigned}:
            raise fail("QUALITY_ASSIGNEE_NOT_ASSIGNED", "责任医护当前未分配管理该患者", 422)
        if context is None:
            context = await patient_domain_context(self.db, session=session)
        # DOMAIN-BRANCH: 栅栏只有账号跳（无患者侧写入），载体随域分派：
        # canonical 落 account_fences（QUALITY_ACCESS_FENCE），不写 users
        # （保持其 canonical 只读约定）；canonical 全量后 legacy 分支可整体删除。
        # domain-dispatch: 迁移完成后可删
        if context.is_canonical:
            await AccountFenceStore(self.db).bump(str(account["_id"]), QUALITY_ACCESS_FENCE, session=session)
        else:
            # LEGACY-SHAPE: legacy 载体——账号与患者实体同文档。
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

    async def _all_patient_ids(self):
        """admin 全量患者枚举按域分派；legacy 分支保留歧义防护语义。"""
        # domain-dispatch: 迁移完成后可删
        if await patient_domain_mode(self.db) == "canonical":
            # canonical：clinical_patients 全部 active 患者 ID（主键唯一，
            # 无 legacy 双形态歧义防护对应物）。
            cursor = ClinicalPatientRepository(self.db).collection.find(
                {"status": "active"}, {"patient_id": 1})
            return [document["patient_id"] async for document in cursor]
        return await LegacyPatientRepository(self.db).assigned_ids(
            {"role": "patient", "is_active": True})

    async def list(self, actor, *, patient_id=None, status=None, assignee_id=None, skip=0, limit=20):
        await self._actor(actor)
        if skip < 0 or not 1 <= limit <= 100:
            raise fail("QUALITY_PAGINATION_INVALID", "分页参数无效", 422)
        query = {}
        if patient_id:
            await self._patient(patient_id, actor)
            query["patient_id"] = patient_id
        else:
            # Scope, role/assignment filtering and same-visible-value identity
            # disambiguation all live in the legacy patient adapter: one
            # candidate read plus one identity batch, never an N+1 patient loop.
            # T50 缺陷 1 同型迁移：构造+执行改走内核 assigned_scope_ids（legacy
            # 落 users 且 is_active 精化语义逐字保留）；canonical 执行于
            # clinical_patients（T63 门闩移除后可达）。admin 无归属角色字段，
            # 经 _all_patient_ids 按域分派保持原全量分支。
            try:
                identifiers = (
                    await assigned_scope_ids(self.db, str(actor.id), actor.role,
                                             extra_query={"is_active": True})
                    if actor.role != "admin" else
                    await self._all_patient_ids())
            except LegacyPatientIdentityError:
                raise fail("QUALITY_PATIENT_IDENTITY_AMBIGUOUS", "患者身份无法唯一核实，请联系管理员核查", 503) from None
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
        # 归属候选两域同构：clinical_patients 迁移保留原归属列表与账号 ID
        # 字面量，账号域仍在 users，身份批量读取无需域分派。
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
