"""Explicit offline migration into the clinical-patient domain.

This library never stops an application or restores/deletes business data.
Apply requires an independently implemented maintenance guard, a matching
inspection manifest and a private legacy snapshot. Mongo snapshot transactions
do not lock read-only users against an unknown external writer: operational
write exclusion is an explicit precondition, not proved by a CLI boolean.
"""
import hashlib
import inspect
import json
import os
import stat
from pathlib import Path
from datetime import datetime, timezone

from bson import BSON, ObjectId, json_util
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern
from pydantic import ValidationError

from .repository import (PATIENTS, ACCOUNT_LINKS, STATE, STATE_ID, SCHEMA_VERSION,
                         PatientDomainError, create_patient_indexes)
from .schemas import patient_response

PROFILE = "clinical-patients-v1-offline"
PATIENT_FIELDS = ("name", "medical_info", "demographic_info", "emergency_contact",
                  "practitioners", "health_managers", "rehabilitation_plans", "devices",
                  "age", "gender", "diagnosis", "height", "weight", "blood_type", "allergies")


def fingerprint(value):
    return hashlib.sha256(json_util.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _private_directory(path):
    path = Path(path)
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise PatientDomainError("MIGRATION_PRIVATE_PATH_REQUIRED")
    parent_info = path.parent.stat()
    if parent_info.st_uid != os.geteuid() or stat.S_IMODE(parent_info.st_mode) & 0o077:
        raise PatientDomainError("MIGRATION_PRIVATE_PATH_REQUIRED")
    path.mkdir(mode=0o700, parents=False, exist_ok=False)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return path


def _write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def project_legacy_patient(document):
    """Preserve clinical IDs/data without projecting account credentials."""
    identifier = document.get("_id")
    if document.get("role") != "patient" or not isinstance(identifier, (str, ObjectId)) or not str(identifier):
        raise PatientDomainError("INVALID_LEGACY_PATIENT")
    if "is_active" in document and type(document["is_active"]) is not bool:
        raise PatientDomainError("INVALID_LEGACY_PATIENT_STATUS")
    for key in ("practitioners", "health_managers", "rehabilitation_plans", "devices"):
        if key in document and (not isinstance(document[key], list)
                or any(not isinstance(item, (str, ObjectId)) or not str(item) for item in document[key])):
            raise PatientDomainError("INVALID_LEGACY_PATIENT_RELATION")
    for key in ("medical_info", "demographic_info", "emergency_contact"):
        if key in document and document[key] is not None and not isinstance(document[key], dict):
            raise PatientDomainError("INVALID_LEGACY_PATIENT_DATA")
    patient_id = str(identifier)
    result = {"_id": identifier, "patient_id": patient_id, "legacy_user_id": patient_id,
              "schema_version": SCHEMA_VERSION,
              "status": "inactive" if document.get("is_active") is False else "active"}
    result.update({key: document[key] for key in PATIENT_FIELDS if key in document})
    for key in ("practitioners", "health_managers", "rehabilitation_plans", "devices"):
        result.setdefault(key, [])
    for key in ("medical_info", "demographic_info", "emergency_contact"):
        result[key] = result.get(key) or {}
    for key, legacy in (("created_at", "createdAt"), ("updated_at", "updatedAt")):
        value = document.get(key, document.get(legacy))
        if value is not None and not isinstance(value, datetime):
            raise PatientDomainError("INVALID_LEGACY_PATIENT_TIME")
        if value is not None:
            result[key] = value
    return result


async def _source_documents(db, session=None):
    return await db.users.find({"role": "patient"}, session=session).sort("_id", 1).to_list(length=None)


def _projections(documents):
    result = [project_legacy_patient(item) for item in documents]
    if len({item["patient_id"] for item in result}) != len(result):
        raise PatientDomainError("AMBIGUOUS_LEGACY_PATIENT_ID")
    for document in result:
        try:
            patient_response(document)  # validate the chosen clinical DTO before any write
        except ValidationError:
            raise PatientDomainError("INVALID_LEGACY_PATIENT_PROJECTION") from None
    return result


def _legacy_links(documents, *, reviewer=None, evidence_reference=None, at=None):
    """Materialize only the intrinsic relation within one patient document."""
    links = []
    for document in documents:
        project_legacy_patient(document)
        identifier = str(document["_id"])
        link = {"_id": "legacy:" + identifier, "account_id": identifier,
                "account_document_id": document["_id"], "patient_id": identifier,
                "source": "legacy_same_document", "schema_version": SCHEMA_VERSION,
                "status": "disabled" if document.get("is_active") is False else "verified"}
        if at is not None:
            link["audit"] = {"reviewer": reviewer, "evidence_reference": evidence_reference,
                             "at": at, "operation": "legacy_same_document_migration"}
        links.append(link)
    return links


def _backup_identity(path):
    information = path.lstat()
    if (not stat.S_ISREG(information.st_mode) or information.st_uid != os.geteuid()
            or stat.S_IMODE(information.st_mode) != 0o600):
        raise PatientDomainError("PATIENT_MIGRATION_BACKUP_CHANGED")
    return information.st_dev, information.st_ino


def _verify_backup(path, identity, expected_sha):
    if _backup_identity(path) != identity:
        raise PatientDomainError("PATIENT_MIGRATION_BACKUP_CHANGED")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        information = os.fstat(descriptor)
        if (information.st_dev, information.st_ino) != identity:
            raise PatientDomainError("PATIENT_MIGRATION_BACKUP_CHANGED")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            actual = hashlib.sha256(stream.read()).hexdigest()
        if actual != expected_sha or _backup_identity(path) != identity:
            raise PatientDomainError("PATIENT_MIGRATION_BACKUP_CHANGED")
    finally:
        os.close(descriptor)


async def inspect_migration(db):
    """Read-only; exposes hashes/counts rather than patient/account material."""
    hello = await db.command("hello")
    state = await db[STATE].find_one({"_id": STATE_ID})
    if state is not None and (state.get("mode") != "canonical"
                              or state.get("schema_version") != SCHEMA_VERSION):
        raise PatientDomainError("PATIENT_DOMAIN_STATE_CONFLICT")
    count = await db[PATIENTS].count_documents({})
    if state is None and count:
        raise PatientDomainError("UNEXPLAINED_CLINICAL_PATIENT_DATA")
    link_count = await db[ACCOUNT_LINKS].count_documents({})
    if state is None and link_count:
        raise PatientDomainError("UNEXPLAINED_PATIENT_ACCOUNT_LINK_DATA")
    source = await _source_documents(db)
    projected = _projections(source)
    return {"profile": PROFILE, "database": db.name,
            "replica_set": hello.get("setName"), "server_hosts": sorted(hello.get("hosts", [])),
            "mode": "canonical" if state else "not_migrated",
            "legacy_count": len(source), "legacy_sha256": fingerprint(source),
            "projection_sha256": fingerprint(projected), "clinical_count": count,
            "legacy_link_count": len(source), "existing_account_link_count": link_count,
            "legacy_links_sha256": fingerprint(_legacy_links(source)), "unknown_external_writers_excluded_by_tool": False}


async def _guard(callback):
    if callback is None or not callable(callback):
        raise PatientDomainError("INDEPENDENT_MAINTENANCE_GUARD_REQUIRED")
    receipt = callback()
    if inspect.isawaitable(receipt):
        receipt = await receipt
    if (not isinstance(receipt, dict) or receipt.get("application_stopped") is not True
            or not receipt.get("guard_reference")):
        raise PatientDomainError("MAINTENANCE_NOT_VERIFIED")
    return receipt


async def migrate_legacy_patients(db, *, expected_manifest, backup_directory, reviewer,
                                  evidence_reference, maintenance_guard, fail_at=None):
    """Apply only after reviewed write exclusion; failure never restores data.

    users are read-only. Only their intrinsic same-document patient account
    relation is materialized as an audited link; no new role or assignment. A full
    database backup/recovery rehearsal remains a deployment responsibility.
    """
    if not reviewer or not evidence_reference:
        raise PatientDomainError("PATIENT_REVIEW_REQUIRED")
    await _guard(maintenance_guard)
    before = await inspect_migration(db)
    if before["mode"] == "canonical":
        return {"verified_noop": True, "mode": "canonical", "users_modified": False}
    if not before["replica_set"]:
        raise PatientDomainError("PATIENT_MIGRATION_REQUIRES_REPLICA_SET")
    if before != expected_manifest:
        raise PatientDomainError("PATIENT_MIGRATION_BASELINE_CHANGED")
    source = await _source_documents(db)
    if fingerprint(source) != before["legacy_sha256"]:
        raise PatientDomainError("PATIENT_MIGRATION_BASELINE_CHANGED")
    private = _private_directory(backup_directory)
    snapshot = b"".join(BSON.encode(item) for item in source)
    _write_private(private / "legacy-patient-accounts.bson", snapshot)
    _write_private(private / "manifest.json", json.dumps(before, sort_keys=True, indent=2).encode())
    backup_sha = hashlib.sha256(snapshot).hexdigest()
    backup_identity = _backup_identity(private / "legacy-patient-accounts.bson")
    journal = {"profile": PROFILE, "database": db.name, "outcome": "prepared",
               "legacy_sha256": before["legacy_sha256"], "backup_sha256": backup_sha,
               "commit_attempted": False, "committed": False, "users_modified": False,
               "database_restore_supported": False}
    # Journal revisions are immutable files; no old outcome is overwritten.
    _write_private(private / "00-prepared.json", json.dumps(journal, sort_keys=True).encode())
    await create_patient_indexes(db)
    if fail_at == "before_transaction":
        raise RuntimeError("synthetic failure before transaction")
    async with await db.client.start_session() as session:
        async with session.start_transaction(read_concern=ReadConcern("snapshot"),
                                             write_concern=WriteConcern("majority")):
            await _guard(maintenance_guard)
            if await db[STATE].find_one({"_id": STATE_ID}, session=session) is not None:
                raise PatientDomainError("PATIENT_DOMAIN_STATE_CONFLICT")
            if await db[PATIENTS].count_documents({}, session=session):
                raise PatientDomainError("UNEXPLAINED_CLINICAL_PATIENT_DATA")
            if await db[ACCOUNT_LINKS].count_documents({}, session=session):
                raise PatientDomainError("UNEXPLAINED_PATIENT_ACCOUNT_LINK_DATA")
            current = await _source_documents(db, session)
            if fingerprint(current) != before["legacy_sha256"]:
                raise PatientDomainError("PATIENT_MIGRATION_BASELINE_CHANGED")
            projected = _projections(current)
            now = datetime.now(timezone.utc)
            now = now.replace(microsecond=(now.microsecond // 1000) * 1000)
            links = _legacy_links(current, reviewer=reviewer, evidence_reference=evidence_reference, at=now)
            await db[STATE].insert_one({"_id": STATE_ID, "mode": "migrating",
                                        "schema_version": SCHEMA_VERSION}, session=session)
            if projected:
                await db[PATIENTS].insert_many(projected, ordered=True, session=session)
            if links:
                await db[ACCOUNT_LINKS].insert_many(links, ordered=True, session=session)
            if fail_at == "after_insert":
                raise RuntimeError("synthetic failure after clinical insert")
            actual = await db[PATIENTS].find({}, session=session).sort("_id", 1).to_list(length=None)
            if fingerprint(actual) != before["projection_sha256"]:
                raise PatientDomainError("CLINICAL_PATIENT_PROJECTION_MISMATCH")
            actual_links = await db[ACCOUNT_LINKS].find({}, session=session).sort("_id", 1).to_list(length=None)
            if fingerprint(actual_links) != fingerprint(sorted(links, key=lambda item: item["_id"])):
                raise PatientDomainError("PATIENT_ACCOUNT_LINK_PROJECTION_MISMATCH")
            if fingerprint(await _source_documents(db, session)) != before["legacy_sha256"]:
                raise PatientDomainError("LEGACY_PATIENT_ACCOUNTS_CHANGED")
            await db[STATE].update_one({"_id": STATE_ID, "mode": "migrating"}, {"$set": {
                "mode": "canonical", "migrated_at": now, "migrated_count": len(projected),
                "legacy_sha256": before["legacy_sha256"], "projection_sha256": before["projection_sha256"],
                "account_links_created": len(links), "legacy_links_sha256": before["legacy_links_sha256"],
                "reviewer": reviewer, "evidence_reference": evidence_reference}}, session=session)
            if fail_at == "before_commit":
                raise RuntimeError("synthetic failure before commit")
            await _guard(maintenance_guard)
            _verify_backup(private / "legacy-patient-accounts.bson", backup_identity, backup_sha)
            journal.update(commit_attempted=True, committed=None, outcome="commit_outcome_unknown")
            _write_private(private / "01-commit-attempted.json", json.dumps(journal, sort_keys=True).encode())
    journal.update(committed=True, outcome="canonical", migrated_count=len(projected),
                   account_links_created=len(links), legacy_links_sha256=before["legacy_links_sha256"])
    _write_private(private / "02-committed.json", json.dumps(journal, sort_keys=True).encode())
    return {"verified_noop": False, "mode": "canonical", "migrated_count": len(projected),
            "legacy_sha256": before["legacy_sha256"], "users_modified": False,
            "account_links_created": len(links), "backup_directory": str(private)}
