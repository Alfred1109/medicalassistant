"""Canonical patient storage with a durable, fail-closed cutover boundary.

Self access resolves only an explicitly audited account link, through one of
two origins: the migrated `legacy_same_document` relation (ID-aligned) or a
reviewed `explicit_binding` created by `bind_account` (independent IDs; see
bind_account for the reject-only mutual-exclusion rules). Callers must apply
their authenticated object policy. Do not add users fallback after canonical
cutover: an absent or inactive clinical record must never revive a legacy
relationship.
"""
import hashlib
import json
import re
from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError

from .schemas import SourcePatientIdentity, patient_response

PATIENTS = "clinical_patients"
ACCOUNT_LINKS = "patient_account_links"
STATE = "patient_domain_state"
STATE_ID = "clinical-patients-v1"
SCHEMA_VERSION = 1
# 链接 origin 载体：legacy_same_document 由迁移工具写入（同文档内在关系）；
# explicit_binding 由人工核实后的管理端点写入（T64 显式绑定工作流）。
LEGACY_SAME_DOCUMENT = "legacy_same_document"
EXPLICIT_BINDING = "explicit_binding"


class PatientDomainError(RuntimeError):
    def __init__(self, code, message=None):
        self.code = code
        super().__init__(message or code)


async def require_canonical(db, *, session=None):
    state = await db[STATE].find_one({"_id": STATE_ID}, session=session)
    if not state or state.get("mode") != "canonical" or state.get("schema_version") != SCHEMA_VERSION:
        raise PatientDomainError("PATIENT_DOMAIN_NOT_MIGRATED")
    return state


async def domain_mode(db, *, session=None):
    """Read the durable domain switch; an unknown observed state fails closed.

    No state document means the legacy users-backed domain is still the active
    default. An explicit `{mode: "legacy", schema_version: SCHEMA_VERSION}`
    state is the audited rollback carrier required by the cutover SOP: it
    resolves to the same legacy domain with identical business behavior — the
    only difference is that the switch stays observable, auditable and
    reversible without deleting the document (deleting it would silently
    degrade and leave no failure signal). Canonical repository access
    (`require_canonical`) keeps refusing under an explicit legacy state, so a
    rollback never produces a half-migrated write path.

    Any other observed state (migrating, a different schema version or
    an unrecognized mode) is rejected: callers must never guess a domain, and
    transport-level read failures must surface to the caller instead of being
    mistaken for a legacy deployment.

    Attribute access is equivalent to `db[STATE]` on a real Mongo database and
    always yields a collection proxy there; only in-memory test doubles that do
    not model the switch at all yield None, and those stay legacy by definition.
    """
    state_collection = getattr(db, STATE, None)
    if state_collection is None:
        return "legacy"
    if session is None:
        state = await state_collection.find_one({"_id": STATE_ID})
    else:
        state = await state_collection.find_one({"_id": STATE_ID}, session=session)
    if state is None:
        return "legacy"
    if state.get("schema_version") != SCHEMA_VERSION:
        raise PatientDomainError("PATIENT_DOMAIN_STATE_UNAVAILABLE")
    if state.get("mode") == "canonical":
        return "canonical"
    if state.get("mode") == "legacy":
        return "legacy"
    raise PatientDomainError("PATIENT_DOMAIN_STATE_UNAVAILABLE")


async def create_patient_indexes(db):
    """Explicit maintenance writes only; not a read-time schema repair."""
    await db[ACCOUNT_LINKS].create_index("account_id", unique=True, name="patient_account_unique")
    await db[ACCOUNT_LINKS].create_index("patient_id", unique=True, name="patient_self_link_unique")
    await db[PATIENTS].create_index("patient_id", unique=True, name="clinical_patient_id_unique")
    await db[PATIENTS].create_index(
        "source_key", unique=True, name="clinical_source_patient_unique",
        partialFilterExpression={"source_key": {"$type": "string"}})
    await db[PATIENTS].create_index(
        [("status", ASCENDING), ("practitioners", ASCENDING)], name="clinical_practitioner_scope")
    await db[PATIENTS].create_index(
        [("status", ASCENDING), ("health_managers", ASCENDING)], name="clinical_health_manager_scope")
    # 姓名搜索辅助索引（普通非唯一索引）：支撑大小写不敏感的 name 查询，
    # 与 create_from_source 的唯一索引校验无关，缺失不会阻断该索引校验。
    # 单一属主：clinical_patient_name_query 此前在 db/indexes.py 的
    # PATIENT_SCOPE_INDEXES 有第二份声明，已收敛到此处（2026-11-15 冗余审查
    # 批次 1）；db/indexes.py 侧不再重复声明。
    await db[PATIENTS].create_index("name", name="clinical_patient_name_query")


def source_key(identity):
    if not isinstance(identity, SourcePatientIdentity):
        identity = SourcePatientIdentity.model_validate(identity)
    if identity.environment == "production" and not identity.origin.startswith("https://"):
        raise PatientDomainError("INVALID_SOURCE_IDENTITY")
    payload = identity.model_dump()
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def assigned_query(operator_id, role):
    fields = {"doctor": "practitioners", "health_manager": "health_managers"}
    if role not in fields:
        raise PatientDomainError("INVALID_PATIENT_ASSIGNMENT_ROLE")
    identifiers = [str(operator_id)]
    if ObjectId.is_valid(str(operator_id)):
        identifiers.append(ObjectId(str(operator_id)))
    return {"status": "active", fields[role]: {"$in": identifiers}}


class ClinicalPatientRepository:
    def __init__(self, db):
        self.db = db
        self.collection = db[PATIENTS]

    async def get(self, patient_id, *, active_only=False, session=None):
        await require_canonical(self.db, session=session)
        query = {"patient_id": str(patient_id)}
        if active_only:
            query["status"] = "active"
        return await self.collection.find_one(query, session=session)

    async def resolve_self(self, account_id, *, session=None):
        """Resolve a verified account relation through its audited link origin.

        The caller supplies its authenticated local account ID. Two origins are
        supported, both requiring reviewer + evidence audit and a live reverse
        check (active local patient account, active canonical clinical record):

        - `legacy_same_document`: the migrated intrinsic same-document relation.
          Requires ID alignment (account ID == patient ID == legacy_user_id);
          that alignment is specific to this origin, never a general rule.
        - `explicit_binding`: a separately reviewed binding created through
          `bind_account` for patients without a same-document history. The
          clinical patient is resolved by the link's own patient_id; no
          legacy_user_id or ID alignment is required.
        """
        await require_canonical(self.db, session=session)
        identifier = str(account_id)
        link = await self.db[ACCOUNT_LINKS].find_one({"account_id": identifier,
            "status": "verified", "source": LEGACY_SAME_DOCUMENT}, session=session)
        audit = link.get("audit") if link else None
        if (link and isinstance(audit, dict)
                and link.get("schema_version") == SCHEMA_VERSION
                and link.get("patient_id") == identifier
                and str(link.get("account_document_id")) == identifier
                and audit.get("reviewer") and audit.get("evidence_reference")
                and audit.get("operation") == "legacy_same_document_migration"
                and isinstance(audit.get("at"), datetime)):
            ids = [identifier]
            if ObjectId.is_valid(identifier):
                ids.append(ObjectId(identifier))
            accounts = await self.db.users.find({"_id": {"$in": ids}}, session=session).to_list(length=2)
            if (len(accounts) == 1 and accounts[0]["_id"] == link["account_document_id"]
                    and accounts[0].get("role") == "patient"
                    and accounts[0].get("is_active", True) is True):
                patient = await self.get(identifier, active_only=True, session=session)
                if patient and patient.get("legacy_user_id") == identifier and patient["_id"] == accounts[0]["_id"]:
                    return patient
        # legacy 载体未命中或校验失败时才探测显式绑定；account_id 全局唯一
        # 索引保证同一账号不可能同时存在两种 origin 的链接，互斥由库承担。
        return await self._resolve_explicit_binding(identifier, session=session)

    async def _resolve_explicit_binding(self, identifier, *, session=None):
        """Reverse-check an explicit binding link without same-document rules."""
        link = await self.db[ACCOUNT_LINKS].find_one({"account_id": identifier,
            "status": "verified", "source": EXPLICIT_BINDING}, session=session)
        audit = link.get("audit") if link else None
        # 显式绑定的审计是追加式 list：首条为绑定（explicit_binding），停用追加
        # explicit_binding_disable。任何条目缺凭证/时间/操作即整体 fail-closed。
        if (not link or not isinstance(audit, list) or not audit
                or not all(isinstance(entry, dict) and entry.get("reviewer")
                           and entry.get("evidence_reference")
                           and entry.get("operation")
                           and isinstance(entry.get("at"), datetime)
                           for entry in audit)
                or audit[0].get("operation") != "explicit_binding"
                or link.get("schema_version") != SCHEMA_VERSION
                or not ObjectId.is_valid(identifier)
                or str(link.get("account_document_id")) != identifier
                or not isinstance(link.get("patient_id"), str)):
            return None
        account = await self.db.users.find_one({"_id": ObjectId(identifier)}, session=session)
        if (not account or str(account["_id"]) != identifier
                or account.get("role") != "patient"
                or account.get("is_active", True) is not True):
            return None
        return await self.get(link["patient_id"], active_only=True, session=session)

    async def get_response(self, patient_id, *, active_only=False):
        document = await self.get(patient_id, active_only=active_only)
        return patient_response(document) if document else None

    async def list_assigned(self, operator_id, role, *, skip=0, limit=100):
        await require_canonical(self.db)
        if skip < 0 or not 1 <= limit <= 200:
            raise PatientDomainError("INVALID_PATIENT_PAGINATION")
        cursor = self.collection.find(assigned_query(operator_id, role)).sort("patient_id", ASCENDING)
        return await cursor.skip(skip).limit(limit).to_list(length=limit)

    async def matching_name_ids(self, name, *, patient_ids=None, operator_id=None,
                                operator_role=None, session=None):
        """Case-insensitive name search aligned with the legacy adapter semantics.

        Returns clinical `patient_id` strings. Without a scope argument every
        active-domain patient whose name matches is returned; `operator_id` with
        `operator_role` restricts the search to one assignment range (already
        status=active), and `patient_ids` restricts it to explicitly supplied
        identifiers. Canonical patient IDs are unique, so the legacy adapter's
        dual-literal ambiguity guard has no canonical counterpart.
        """
        await require_canonical(self.db, session=session)
        if not isinstance(name, str):
            raise PatientDomainError("INVALID_PATIENT_NAME_QUERY")
        query = {"name": {"$regex": re.escape(name), "$options": "i"}}
        if operator_role is not None:
            query.update(assigned_query(operator_id, operator_role))
        if patient_ids is not None:
            query["patient_id"] = {"$in": [str(item) for item in patient_ids]}
        documents = await self.collection.find(query, {"patient_id": 1},
                                               session=session).to_list(length=None)
        return {document["patient_id"] for document in documents}

    async def create_from_source(self, identity, *, reviewer, evidence_reference, name=None, session=None):
        """Store a previously verified source identity; never infer an account.

        The caller must obtain the source reference through its authorized
        source API and verify identity before calling. This storage primitive
        cannot itself attest remote authorization or human review.
        """
        await require_canonical(self.db, session=session)
        if not isinstance(reviewer, str) or not reviewer.strip() or not isinstance(evidence_reference, str) or not evidence_reference.strip():
            raise PatientDomainError("PATIENT_REVIEW_REQUIRED")
        if name is not None and (not isinstance(name, str) or not name.strip() or len(name) > 200):
            raise PatientDomainError("INVALID_PATIENT_NAME")
        identity = SourcePatientIdentity.model_validate(identity)
        key = source_key(identity)
        # Missing required unique indexes is an operational error, never an
        # invitation to make an unprotected best-effort write.
        try:
            # MongoDB forbids listIndexes inside transactions. Verify the full
            # definition outside, then require those exact names via hints in
            # the caller's transaction. Deployment must prohibit concurrent DDL.
            metadata_session = None if session is not None and session.in_transaction else session
            indexes = await self.collection.index_information(session=metadata_session)
            for index, field, partial in (
                    ("clinical_patient_id_unique", "patient_id", None),
                    ("clinical_source_patient_unique", "source_key", {"source_key": {"$type": "string"}})):
                spec = indexes.get(index, {})
                if (not spec.get("unique") or spec.get("key") != [(field, 1)]
                        or spec.get("partialFilterExpression") != partial
                        or spec.get("sparse") or spec.get("collation") or spec.get("hidden")):
                    raise PatientDomainError("PATIENT_DOMAIN_INDEX_MISSING")
                if session is not None and session.in_transaction:
                    value = key if field == "source_key" else "__index_presence_probe__"
                    await self.collection.find_one({field: value}, {"_id": 1},
                                                   hint=index, session=session)
        except PyMongoError:
            raise PatientDomainError("PATIENT_DOMAIN_INDEX_CHECK_FAILED") from None
        now = datetime.now(timezone.utc)
        identifier = ObjectId()
        document = {"_id": identifier, "patient_id": str(identifier), "schema_version": SCHEMA_VERSION,
                    "status": "active", "name": name.strip() if name else None,
                    "source": identity.model_dump(), "source_key": key,
                    "practitioners": [], "health_managers": [],
                    "medical_info": {}, "demographic_info": {}, "emergency_contact": {},
                    "created_at": now, "updated_at": now,
                    "review": {"reviewer": reviewer.strip(), "evidence_reference": evidence_reference.strip(), "at": now}}
        try:
            await self.collection.insert_one(document, session=session)
        except DuplicateKeyError:
            # Inactive existing records are conflicts too; never reactivate.
            raise PatientDomainError("SOURCE_PATIENT_ALREADY_EXISTS") from None
        return document

    @staticmethod
    def _binding_review(reviewer, evidence_reference):
        """Shared human-review validation for the explicit binding workflow."""
        if (not isinstance(reviewer, str) or not reviewer.strip()
                or not isinstance(evidence_reference, str) or not evidence_reference.strip()):
            raise PatientDomainError("PATIENT_REVIEW_REQUIRED")
        reviewer = reviewer.strip()
        evidence_reference = evidence_reference.strip()
        if len(reviewer) > 200 or len(evidence_reference) > 1024:
            raise PatientDomainError("INVALID_PATIENT_REVIEW_REFERENCE")
        return reviewer, evidence_reference

    async def bind_account(self, patient_id, *, account_id, reviewer,
                           evidence_reference, session=None):
        """Create an explicitly reviewed verified account↔patient link.

        Human review is a precondition, not something this primitive can attest:
        the caller must verify that the local account really belongs to this
        clinical patient before invoking. The link carries an independent
        `explicit_binding` origin with reviewer/evidence/time audit and the
        bound account document ID.

        Mutual exclusion is reject-only, never an implicit replace: the
        existing unique indexes (`patient_account_unique`, `patient_self_link_unique`)
        admit at most one link document per account and per patient across all
        origins, verified or disabled. A patient or account with any existing
        link (including a disabled `legacy_same_document` artifact, which is
        part of the migration baseline coverage and must not be rewritten) is
        rejected with `PATIENT_ACCOUNT_LINK_CONFLICT`; `DuplicateKeyError` on
        the insert closes concurrent races to the same error. Disabled links
        are terminal documents that keep occupying their unique slots —
        rebinding requires the reviewed manual reconciliation described in the
        module README, never an automatic revive.

        The clinical patient must exist and be active, and the account must be
        exactly one active local `role: "patient"` document addressed by its
        ObjectId; account activity is re-checked on every `resolve_self`, so a
        later deactivation takes effect without touching the link.
        """
        await require_canonical(self.db, session=session)
        reviewer, evidence_reference = self._binding_review(reviewer, evidence_reference)
        if not isinstance(account_id, str) or not ObjectId.is_valid(account_id):
            raise PatientDomainError("INVALID_PATIENT_ACCOUNT")
        identifier = str(patient_id)
        if not identifier:
            raise PatientDomainError("PATIENT_NOT_FOUND")
        patient = await self.get(identifier, active_only=True, session=session)
        if patient is None:
            raise PatientDomainError("PATIENT_NOT_FOUND")
        account_oid = ObjectId(account_id)
        account = await self.db.users.find_one({"_id": account_oid}, session=session)
        if (not account or account.get("role") != "patient"
                or account.get("is_active", True) is not True):
            raise PatientDomainError("INVALID_PATIENT_ACCOUNT")
        existing = await self.db[ACCOUNT_LINKS].find_one(
            {"$or": [{"patient_id": identifier}, {"account_id": account_id}]},
            session=session)
        if existing is not None:
            raise PatientDomainError("PATIENT_ACCOUNT_LINK_CONFLICT")
        now = datetime.now(timezone.utc)
        link = {"_id": f"explicit:{identifier}", "account_id": account_id,
                "account_document_id": account_oid, "patient_id": identifier,
                "source": EXPLICIT_BINDING, "schema_version": SCHEMA_VERSION,
                "status": "verified", "bound_at": now,
                # 追加式审计 list（与 legacy_same_document 的单条 dict 不同）：
                # 绑定首条 + 后续状态变更逐条追加，停用经 $push 原子写入。
                "audit": [{"reviewer": reviewer, "evidence_reference": evidence_reference,
                           "operation": "explicit_binding", "at": now}]}
        try:
            await self.db[ACCOUNT_LINKS].insert_one(link, session=session)
        except DuplicateKeyError:
            raise PatientDomainError("PATIENT_ACCOUNT_LINK_CONFLICT") from None
        return link

    async def disable_account_link(self, patient_id, *, reviewer,
                                   evidence_reference, session=None):
        """Disable the explicit verified link; reuse the verified→disabled state machine.

        Atomic conditional update: only a currently verified `explicit_binding`
        link for this patient transitions, with the disable audit appended to
        the same document. The link document is never deleted and never revived.
        `legacy_same_document` links are migration artifacts and stay outside
        this workflow (`PATIENT_ACCOUNT_LINK_CONFLICT`); an absent link is
        `PATIENT_ACCOUNT_LINK_NOT_FOUND`.
        """
        await require_canonical(self.db, session=session)
        reviewer, evidence_reference = self._binding_review(reviewer, evidence_reference)
        identifier = str(patient_id)
        now = datetime.now(timezone.utc)
        updated = await self.db[ACCOUNT_LINKS].update_one(
            {"patient_id": identifier, "source": EXPLICIT_BINDING, "status": "verified"},
            {"$set": {"status": "disabled", "disabled_at": now},
             "$push": {"audit": {"operation": "explicit_binding_disable",
                                 "reviewer": reviewer,
                                 "evidence_reference": evidence_reference, "at": now}}},
            session=session)
        if updated.modified_count == 1:
            return await self.db[ACCOUNT_LINKS].find_one(
                {"patient_id": identifier, "source": EXPLICIT_BINDING}, session=session)
        existing = await self.db[ACCOUNT_LINKS].find_one(
            {"patient_id": identifier}, session=session)
        if existing is None:
            raise PatientDomainError("PATIENT_ACCOUNT_LINK_NOT_FOUND")
        raise PatientDomainError("PATIENT_ACCOUNT_LINK_CONFLICT")
