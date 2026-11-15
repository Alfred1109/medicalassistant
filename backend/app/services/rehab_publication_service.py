"""Structured clinical drafts and immutable patient-visible versions.

The existing version/item collections own prescription content. Legacy raw
plans and exercises are never silently promoted into patient instructions.
"""
import hashlib
from copy import deepcopy
from datetime import datetime, timezone

from bson import ObjectId, json_util
from pymongo.errors import DuplicateKeyError
from pydantic import ValidationError

from app.core.exceptions import AppBaseException
from app.core.fences import AccountFenceStore, PatientFenceStore, dual_bump, legacy_document_fence
from app.core.patient_access import (PatientAccessError, is_domain_state_unavailable,
                                     patient_assignment_field, patient_domain_context)
from app.core.patient_identity import resolve_unique_account

# 栅栏名域化（T67 缺陷 1）：康复发布域的并发授权栅栏不与质控等域共用泛化名
# "access"——同名栅栏会让同一账号（account_fences 复合键）与同一患者文档
# （clinical_patients._fence_{name} 字段）的跨域计数互相污染 CAS 复核。
# 取 "rehab_publish"：该栅栏守护的是发布域的草稿/发布/撤回写授权（账号态 +
# 患者归属态两次复核），命名直指被守护的写域。
REHAB_PUBLISH_FENCE = "rehab_publish"
from app.db.transactions import run_transaction
from app.schemas.rehab_publication import PublicationContent, PublicationItem
from app.services.rehab_clinical_config import load_contraindication_rules, load_signature_declaration
from app.services.rehab_contraindication_service import (
    build_patient_context, evaluate_contraindications, findings_summary, split_findings,
)

WORKFLOW = "patient_publication"
OPERATIONS = "rehab_publication_operations"


def error(code, message, status=409, details=None):
    return AppBaseException(message, status_code=status, error_code=code, details=details)


async def run_rehab_transaction(db, callback):
    return await run_transaction(db, callback,
        error_code="REHAB_TRANSACTION_UNAVAILABLE",
        error_message="康复事务未能确认提交，请使用相同请求重试")


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

    async def _account(self, identifier, session):
        # 账号层（两种域模式下账号均仍在 users 集合）按字面读取认证主体自身；
        # 患者实体校验不经过此处（见 _authorize 域分派）：legacy 账号与患者
        # 实体同文档，canonical 二者拆分（临床实体在 clinical_patients，
        # 账号↔实体关系由 patient_account_links 显式承载）。
        # （R1-A3 收敛：唯一账号解析迁 core/patient_identity.resolve_unique_account
        # ——统一为 identity_key 归组口径。原 raw 双字面 $in 实现对 canonical
        # ObjectId 字符串的候选集与归组口径结果一致；理论差异仅在非 canonical
        # 形态的合法 ObjectId 字符串（如大写 hex）下归组口径多出一个 canonical
        # 字符串候选，见报告行为变化清单。同键多文档返回 None 由调用方
        # REHAB_ACCOUNT_UNAVAILABLE 防护兜住。）
        return await resolve_unique_account(self.db, identifier, session=session)

    async def _access_fence(self, document, session):
        # LEGACY-SHAPE: legacy 载体——users 账号文档 _access_fence 计数（账号与
        # 患者实体同文档，一次 $inc 同时覆盖两种语义）。canonical 分支已拆分为
        # 双载体（见 _fence_writes 的 dual_bump）。
        # 迁移窗口约束（cutover plan §3.3）：切换时存量栅栏计数不迁移（仅 CAS
        # 复核用，无业务含义），canonical 双载体从当前值重新起算；但切换窗口内
        # 本旧载体必须停止递增，否则回拨 legacy 后旧计数失效。
        # （R1-A2 收敛：骨架迁 fences.legacy_document_fence——本调用点无 CAS
        # 复核，账号文档由 _account 在同事务内核实，行为逐字不变。）
        await legacy_document_fence(self.db.users, document, "_access_fence",
            session=session, error_code="REHAB_ACCESS_FENCE_INVALID",
            error_message="账号并发状态异常")

    async def _patient_document(self, context, plan):
        """患者实体读取下沉内核（域分派）；本域只保留错误码映射与可用性精化。

        内核负责域载体选择（legacy: users / canonical: clinical_patients）、
        ObjectId/string 双字面兼容、身份歧义 503 防护与 canonical 的
        status=active 判定；本域把「患者不存在」映射为本域错误码
        REHAB_PATIENT_UNAVAILABLE（404），域状态不可用（503）原样透传。
        """
        try:
            patient = await context.load_patient_doc(str(plan.get("patient_id", "")))
        except PatientAccessError as failure:
            if is_domain_state_unavailable(failure):
                raise
            raise error("REHAB_PATIENT_UNAVAILABLE", "患者档案不可用", 404) from None
        # LEGACY-SHAPE: legacy 用户文档的可用性载体是 is_active（canonical
        # 文档无该字段，其可用性已由内核按 status=active 统一判定）。
        # domain-dispatch: 迁移完成后可删
        if not context.is_canonical and patient.get("is_active") is not True:
            raise error("REHAB_PATIENT_UNAVAILABLE", "患者档案不可用", 404)
        return patient

    async def _authorize(self, plan, actor, session, *, write=False, fence=False, context=None):
        # 域分派下沉内核（core/patient_access.patient_domain_context）：域模式
        # 一次读取，患者实体读取与本人身份核验复用同一上下文；服务层只保留
        # 本域业务差异（角色归属策略、栅栏载体、错误码族）。
        # 状态读取失败/未知状态时内核自然传播 503 fail-closed。
        if context is None:
            context = await patient_domain_context(self.db, session=session)
        account = await self._account(str(actor.id), session)
        if not account or account.get("is_active") is not True or account.get("role") != actor.role:
            raise error("REHAB_ACCOUNT_UNAVAILABLE", "当前账号不可用", 403)
        patient = await self._patient_document(context, plan)
        if actor.role == "patient":
            # 本人核验下沉内核：legacy 同文档身份 / canonical verified 链接解析
            # （无链接患者无法访问，属预期形态，绝不回退同 ID 假设）。
            try:
                await context.resolve_self_patient_entity(actor, context.entity_id(patient))
            except PatientAccessError as failure:
                if is_domain_state_unavailable(failure):
                    raise
                raise error("REHAB_PATIENT_FORBIDDEN", "无权访问该患者的康复方案", 403) from None
            if write:
                raise error("REHAB_PATIENT_FORBIDDEN", "无权访问该患者的康复方案", 403)
        elif actor.role in {"doctor", "health_manager"}:
            # 归属字段与 legacy 同构（迁移保留原归属列表与 ID 字面量）；
            # canonical 可用性语义已由内核的 status=active 判定内建。
            assigned = patient.get(patient_assignment_field(actor.role))
            if not isinstance(assigned, list) or str(account["_id"]) not in {str(value) for value in assigned}:
                raise error("REHAB_PATIENT_NOT_ASSIGNED", "当前未分配管理该患者", 403)
        elif actor.role != "admin" or write:
            raise error("REHAB_CLINICIAN_REQUIRED", "需要医护确认权限", 403)
        if fence:
            await self._fence_writes(context, account, patient, session)
        return patient

    async def _fence_writes(self, context, account, patient, session):
        # DOMAIN-BRANCH: 栅栏载体按域分派（迁移完成、canonical 全量后，
        # legacy 双跳载体分支可整体删除）。
        # domain-dispatch: 迁移完成后可删
        if context.is_canonical:
            # canonical 双载体（cutover plan §3.2/3.3）：账号态 → account_fences
            # 独立集合计数；患者归属态 → clinical_patients 文档
            # _fence_rehab_publish 字段（栅栏名域化，T67 缺陷 1：不与质控等
            # 域共用泛化名，避免同账号/同患者文档跨域计数互相污染 CAS 复核）。
            # 迁移窗口约束：存量计数不迁移（仅 CAS 复核用），双载体从
            # 空白起算，且旧载体（users._access_fence）在切换窗口内停止递增。
            # 两次复核必须在同一事务内（session 透传），任一跳失败整体
            # 回滚；并发归属撤写与患者载体 $inc 写冲突触发事务重试，重试后
            # 重新读取授权快照即拒绝。账号侧载体与 users 文档分离（§3.2
            # 「账号撤权写入与栅栏递增互不干扰」）：users 停用不与本次事务
            # 写集冲突，进行中的快照授权写照常提交，停用对其后续写入立即
            # 生效；撤权路径参与账号载体计数后可进一步对账关闭该窗口。
            await dual_bump(
                (AccountFenceStore(self.db), str(account["_id"]), REHAB_PUBLISH_FENCE),
                (PatientFenceStore(self.db), context.entity_id(patient), REHAB_PUBLISH_FENCE),
                session=session)
            return
        # LEGACY-SHAPE: legacy 载体——账号与患者实体同文档，一次 $inc 同时覆盖
        # 两种语义；账号与患者同文档时只递增一次（去重是 legacy 形态约束）。
        await self._access_fence(account, session)
        if account["_id"] != patient["_id"]:
            await self._access_fence(patient, session)

    async def _plan(self, plan_id, session):
        if not ObjectId.is_valid(plan_id):
            raise error("REHAB_PLAN_NOT_FOUND", "康复方案不存在", 404)
        plan = await self.plans.find_one({"_id": ObjectId(plan_id)}, session=session)
        if not plan or not plan.get("patient_id"):
            raise error("REHAB_PLAN_NOT_FOUND", "康复方案不存在", 404)
        return plan

    async def _touch_plan(self, plan, session, *, changes=None, extra_query=None,
                          conflict_code="REHAB_PLAN_CONFLICT",
                          conflict_message="康复方案已变化，请重新读取"):
        """_publication_fence 载体函数（R1-A2 收敛：发布域唯一实现，原
        rehab_feedback.submit 的内联 guard+find_one_and_update 复用本载体）。

        extra_query：调用方的并发防护条件折入定位查询（患者反馈提交路径以
        published_version_id/status/deleted 锚定「读取时的发布快照仍有效」），
        CAS 语义不变：matched != 1 即方案已变化，拒绝写。conflict_code/
        conflict_message 参数化：反馈域保留自己的 409 码
        （REHAB_FEEDBACK_VERSION_CHANGED），503 栅栏形态码统一为
        REHAB_PUBLICATION_INVALID（前端未消费旧 REHAB_FEEDBACK_INVALID_FENCE，
        见报告行为变化清单）。
        """
        guard = plan.get("_publication_fence", 0)
        if type(guard) is not int or guard < 0:
            raise error("REHAB_PUBLICATION_INVALID", "康复方案并发状态异常", 503)
        update = {"$inc": {"_publication_fence": 1}}
        if changes:
            update["$set"] = changes
        query = {"_id": plan["_id"]}
        if extra_query:
            query.update(extra_query)
        result = await self.plans.update_one(query, update, session=session)
        if result.matched_count != 1:
            raise error(conflict_code, conflict_message)

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
                     "content": public_content(version["snapshot"]), "items": [public_item(item) for item in entries],
                     "contraindication_findings": version.get("contraindication_findings")}
        published = None
        signature = None
        if plan.get("published_version_id") and plan.get("status") not in {"cancelled", "canceled", "archived"}:
            version = await self._published(plan, session)
            published = self._patient_projection(plan, version)
            signature = self._signature_projection(version)
        return {"plan_id": str(plan["_id"]), "draft": draft, "published": published,
                "published_version_id": plan.get("published_version_id"),
                "signature": signature,
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

    async def _contraindication_findings(self, patient, items):
        """对处方项执行禁忌规则引擎（规则口径可被 rehab_clinical_rules 覆盖）。"""
        context = build_patient_context(patient)
        rules = await load_contraindication_rules(self.db)
        return evaluate_contraindications(context, items, rules)

    async def save_draft(self, plan_id, actor, payload):
        self._clinical_writer(actor)
        await self.ensure_storage()
        key, fingerprint = self._operation(plan_id, actor, "save_draft", payload)
        async def save(session):
            plan = await self._plan(plan_id, session)
            patient = await self._authorize(plan, actor, session, write=True, fence=True)
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
            # 禁忌规则预检（T72）：草稿阶段只做提示预览，block 不阻断草稿保存，
            # 阻断在发布事务内执行（见 publish）。findings 随草稿版本落库，
            # 医护每次读取草稿都能看到当前口径下的命中结果。
            findings = split_findings(await self._contraindication_findings(
                patient, [item.model_dump(exclude_none=True) for item in payload.items]))
            findings["checked_at"] = stamp
            if existing:
                revision = existing["draft_revision"] + 1
                await self.versions.update_one({"_id": existing["_id"]}, {"$set": {
                    "snapshot": payload.content.model_dump(), "draft_revision": revision,
                    "contraindication_findings": findings, "updated_at": stamp}}, session=session)
            else:
                last = await self.versions.find_one({"plan_id": plan_id}, sort=[("version_no", -1)], session=session)
                number = last.get("version_no", 0) + 1 if last else 1
                identifier = str(ObjectId())
                revision = 0
                await self.versions.insert_one({"_id": ObjectId(identifier), "plan_id": plan_id,
                    "patient_id": str(plan["patient_id"]), "workflow": WORKFLOW, "status": "draft",
                    "version_no": number, "draft_revision": revision, "snapshot": payload.content.model_dump(),
                    "contraindication_findings": findings,
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

    def _signature_projection(self, version):
        """医护侧签署记录投影（患者投影不含签署内容，患者读取语义不变）。"""
        signature = version.get("signature")
        if not isinstance(signature, dict):
            return None
        projected = {key: signature[key] for key in ("signed_by", "signed_by_role", "declaration",
            "declaration_status", "confirmation_note", "snapshot_hash") if key in signature}
        if signature.get("signed_at") is not None:
            projected["signed_at"] = utc_iso(signature["signed_at"])
        return projected or None

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
            # 域分派下沉内核：本人实体解析一次读取域模式（canonical 经
            # resolve_self 的 verified 链接解析，legacy 保持同文档身份），
            # 随后的授权复核复用同一上下文（同一请求内只读一次域状态）。
            context = await patient_domain_context(self.db, session=session)
            try:
                patient_id = await context.resolve_self_patient_entity(actor)
            except PatientAccessError as failure:
                if is_domain_state_unavailable(failure):
                    raise
                raise error("REHAB_PATIENT_FORBIDDEN", "无权访问该患者的康复方案", 403) from None
            await self._authorize({"patient_id": patient_id}, actor, session, context=context)
            query = {"patient_id": patient_id, "published_version_id": {"$type": "string"},
                     "status": {"$nin": ["cancelled", "canceled", "archived"]}}
            rows = await self.plans.find(query, session=session).sort([("published_at", -1), ("_id", -1)]).skip(skip).limit(limit).to_list(length=limit)
            values = [self._patient_projection(row, await self._published(row, session)) for row in rows]
            status_counts = {
                status: await self.plans.count_documents({**query, "status": status}, session=session)
                for status in ("active", "completed")
            }
            return {"items": values, "total": await self.plans.count_documents(query, session=session),
                    "status_counts": status_counts, "skip": skip, "limit": limit}
        return await run_rehab_transaction(self.db, read)

    def _signature(self, actor, stamp, snapshot, items, payload, declaration):
        """签署记录：签署人、时间、签署声明、所签版本的内容快照哈希。

        快照哈希覆盖版本 snapshot 与 items_snapshot，绑定「签署的内容版本」；
        声明文案来自可配置口径（rehab_clinical_config），第一版签署行为由
        publish 请求自带的 confirmed/confirmation_note（与可选的
        declaration_acknowledged）承载。
        """
        digest = hashlib.sha256(json_util.dumps({"snapshot": snapshot, "items": items},
            sort_keys=True).encode()).hexdigest()
        return {"signed_by": str(actor.id), "signed_by_role": actor.role, "signed_at": stamp,
                "declaration": declaration["declaration"], "declaration_status": declaration["status"],
                "declaration_acknowledged": payload.declaration_acknowledged is True,
                "confirmation_note": payload.confirmation_note, "snapshot_hash": digest}

    async def publish(self, plan_id, actor, payload):
        self._clinical_writer(actor)
        await self.ensure_storage()
        key, fingerprint = self._operation(plan_id, actor, "publish", payload)
        async def publish(session):
            plan = await self._plan(plan_id, session)
            patient = await self._authorize(plan, actor, session, write=True, fence=True)
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
            # 禁忌规则阻断（T72）：发布事务内按当前生效规则口径对快照项复检；
            # block 命中即阻断发布（第一版不做覆盖，覆盖流程建议见任务报告）。
            findings = split_findings(await self._contraindication_findings(patient, snapshot_items))
            if findings["blocks"]:
                raise error("REHAB_CONTRAINDICATION_BLOCK", "存在禁忌阻断项，发布被拒绝：" +
                    findings_summary(findings["blocks"]), 422,
                    details={"findings": findings["blocks"], "warnings": findings["warnings"]})
            stamp = now_utc()
            revision = plan.get("publication_revision", 0)
            if type(revision) is not int or revision < 0:
                raise error("REHAB_PUBLICATION_INVALID", "发布修订号异常", 503)
            revision += 1
            declaration = await load_signature_declaration(self.db)
            signature = self._signature(actor, stamp, version["snapshot"], snapshot_items, payload, declaration)
            findings["checked_at"] = stamp
            await self.versions.update_one({"_id": version["_id"]}, {"$set": {
                "status": "published", "items_snapshot": snapshot_items,
                "published_by": str(actor.id), "published_at": stamp, "publication_revision": revision,
                "confirmation_note": payload.confirmation_note, "signature": signature,
                "contraindication_findings": findings, "updated_at": stamp}}, session=session)
            await self._touch_plan(plan, session, changes={"published_version_id": payload.draft_id,
                "active_draft_version_id": None, "has_publication_history": True,
                "publication_revision": revision, "published_at": stamp})
            version.update(status="published", items_snapshot=snapshot_items, published_at=stamp, publication_revision=revision)
            await self._record_operation(key, fingerprint, "publish", plan_id, actor,
                                         {"version_id": payload.draft_id, "signature": signature,
                                          "contraindication_findings": findings}, session)
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

    async def signature_declaration(self, actor):
        """发布签署声明文案（医护只读；口径可配置，默认文案待临床确认）。"""
        self._clinical_writer(actor)
        return await load_signature_declaration(self.db)

    async def contraindication_rules(self, actor):
        """生效中的禁忌规则元数据（医护只读，不含患者数据）。"""
        self._clinical_writer(actor)
        rules = await load_contraindication_rules(self.db)
        return [{"rule_id": rule.get("rule_id"), "level": rule.get("level"), "scope": rule.get("scope"),
                 "description": rule.get("description"), "status": rule.get("status"),
                 "source": rule.get("source")} for rule in rules]
