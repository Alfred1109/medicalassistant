"""Canonical patient storage with a durable, fail-closed cutover boundary.

Self access resolves only an explicit legacy account link. Callers must apply their
authenticated object policy. Do not add users fallback after canonical cutover:
an absent or inactive clinical record must never revive a legacy relationship.
"""
import hashlib
import json
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


class PatientDomainError(RuntimeError):
    def __init__(self, code, message=None):
        self.code = code
        super().__init__(message or code)


async def require_canonical(db, *, session=None):
    state = await db[STATE].find_one({"_id": STATE_ID}, session=session)
    if not state or state.get("mode") != "canonical" or state.get("schema_version") != SCHEMA_VERSION:
        raise PatientDomainError("PATIENT_DOMAIN_NOT_MIGRATED")
    return state


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
        """Resolve only an explicit migrated same-document account relation.

        The caller supplies its authenticated local account ID. Other binding
        origins require a separately reviewed binding workflow.
        """
        await require_canonical(self.db, session=session)
        identifier = str(account_id)
        link = await self.db[ACCOUNT_LINKS].find_one({"account_id": identifier,
            "status": "verified", "source": "legacy_same_document"}, session=session)
        audit = link.get("audit") if link else None
        if (not link or not isinstance(audit, dict)
                or link.get("schema_version") != SCHEMA_VERSION
                or link.get("patient_id") != identifier
                or str(link.get("account_document_id")) != identifier
                or not audit.get("reviewer") or not audit.get("evidence_reference")
                or audit.get("operation") != "legacy_same_document_migration"
                or not isinstance(audit.get("at"), datetime)):
            return None
        ids = [identifier]
        if ObjectId.is_valid(identifier):
            ids.append(ObjectId(identifier))
        accounts = await self.db.users.find({"_id": {"$in": ids}}, session=session).to_list(length=2)
        if (len(accounts) != 1 or accounts[0]["_id"] != link["account_document_id"]
                or accounts[0].get("role") != "patient"
                or accounts[0].get("is_active", True) is not True):
            return None
        patient = await self.get(identifier, active_only=True, session=session)
        if patient and patient.get("legacy_user_id") == identifier and patient["_id"] == accounts[0]["_id"]:
            return patient
        return None

    async def get_response(self, patient_id, *, active_only=False):
        document = await self.get(patient_id, active_only=active_only)
        return patient_response(document) if document else None

    async def list_assigned(self, operator_id, role, *, skip=0, limit=100):
        await require_canonical(self.db)
        if skip < 0 or not 1 <= limit <= 200:
            raise PatientDomainError("INVALID_PATIENT_PAGINATION")
        cursor = self.collection.find(assigned_query(operator_id, role)).sort("patient_id", ASCENDING)
        return await cursor.skip(skip).limit(limit).to_list(length=limit)

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
