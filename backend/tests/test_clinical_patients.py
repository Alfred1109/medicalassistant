"""Clinical identities without invented login accounts; real Mongo tests are opt-in."""
import asyncio
import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from pymongo.errors import OperationFailure

from bson import BSON, ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import ValidationError

from app.patients.migration import inspect_migration, migrate_legacy_patients, project_legacy_patient
from app.patients.repository import (ClinicalPatientRepository, PatientDomainError,
                                     PATIENTS, STATE, STATE_ID, assigned_query, source_key)
from app.patients.schemas import SourcePatientIdentity, patient_response


class PatientProjectionTests(unittest.TestCase):
    def test_projection_keeps_id_and_existing_relations_but_never_credentials(self):
        identifier, doctor = ObjectId(), ObjectId()
        legacy = {"_id": identifier, "role": "patient", "email": "private@example.com",
                  "password_hash": "private-hash", "refresh_tokens": ["private-token"],
                  "permissions": ["admin"], "is_active": False, "name": "synthetic",
                  "practitioners": [doctor], "medical_info": {"diagnosis": "synthetic"}}
        original = deepcopy(legacy)
        projected = project_legacy_patient(legacy)
        self.assertEqual(legacy, original)
        self.assertEqual(projected["_id"], identifier)
        self.assertEqual(projected["patient_id"], str(identifier))
        self.assertEqual(projected["practitioners"], [doctor])
        self.assertEqual(projected["status"], "inactive")
        self.assertFalse(set(projected) & {"role", "email", "password_hash", "refresh_tokens", "permissions"})
        dto = patient_response(projected).model_dump()
        self.assertEqual(dto["practitioners"], [str(doctor)])
        self.assertFalse(set(dto) & {"role", "email", "password_hash", "refresh_tokens", "permissions"})

    def test_invalid_legacy_shape_is_rejected_without_guessing(self):
        baseline = {"_id": ObjectId(), "role": "patient"}
        for invalid in ({"is_active": "false"}, {"practitioners": "doctor"},
                        {"health_managers": [None]}, {"medical_info": "unknown"},
                        {"created_at": "yesterday"}, {"role": "doctor"}):
            with self.subTest(invalid=invalid), self.assertRaises(PatientDomainError):
                project_legacy_patient({**baseline, **invalid})

    def test_source_identity_is_environment_and_origin_bound(self):
        base = {"origin": "https://source.example", "system": "form-platform-11344",
                "environment": "production", "patient_id": 1}
        self.assertNotEqual(source_key(base), source_key({**base, "environment": "pilot"}))
        self.assertNotEqual(source_key(base), source_key({**base, "origin": "https://other.example"}))
        self.assertEqual(source_key(base), source_key({**base, "origin": "https://SOURCE.example:443"}))
        with self.assertRaises(ValidationError):
            source_key({**base, "origin": "http://127.0.0.1:1"})
        for invalid in ({"patient_id": True}, {"patient_id": "1"},
                        {"origin": "https://source.example/path"},
                        {"origin": "https://source.example:wrong"},
                        {"origin": "https://user:secret@source.example"}, {"email": "invented@example.com"}):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                SourcePatientIdentity.model_validate({**base, **invalid})

    def test_assignment_fields_remain_role_specific(self):
        actor = str(ObjectId())
        self.assertEqual(set(assigned_query(actor, "doctor")), {"status", "practitioners"})
        self.assertEqual(set(assigned_query(actor, "health_manager")), {"status", "health_managers"})
        for role in ("patient", "admin", "unknown"):
            with self.assertRaises(PatientDomainError):
                assigned_query(actor, role)


URI = os.environ.get("REHAB_TEST_CLINICAL_PATIENT_URI")


@unittest.skipUnless(URI, "set REHAB_TEST_CLINICAL_PATIENT_URI to an isolated local replica set")
class ClinicalPatientMongoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if not URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")):
            self.fail("only an explicit local test URI is accepted")
        self.client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.client["rehab_clinical_patient_test_" + uuid4().hex]
        self.patient_id, self.doctor_id, self.manager_id = ObjectId(), ObjectId(), ObjectId()
        self.legacy = {"_id": self.patient_id, "role": "patient", "name": "synthetic-patient",
                       "email": "synthetic@example.com", "password_hash": "do-not-project",
                       "refresh_tokens": ["synthetic-token"], "is_active": True,
                       "practitioners": [self.doctor_id], "health_managers": [str(self.manager_id)],
                       "medical_info": {"diagnosis": "synthetic"}}
        await self.db.users.insert_many([deepcopy(self.legacy),
            {"_id": self.doctor_id, "role": "doctor", "is_active": True},
            {"_id": self.manager_id, "role": "health_manager", "is_active": True}])
        self.repo = ClinicalPatientRepository(self.db)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = {"origin": "https://source.example", "system": "form-platform-11344",
                       "environment": "production", "patient_id": 99}

    async def asyncTearDown(self):
        await self.client.drop_database(self.db.name)
        self.client.close()
        self.temp.cleanup()

    @staticmethod
    def stopped():
        return {"application_stopped": True, "guard_reference": "isolated-synthetic-fixture"}

    async def migrate(self, **overrides):
        options = dict(expected_manifest=await inspect_migration(self.db),
                       backup_directory=self.root / uuid4().hex, reviewer="synthetic-reviewer",
                       evidence_reference="synthetic-verified-reference", maintenance_guard=self.stopped)
        options.update(overrides)
        return await migrate_legacy_patients(self.db, **options)

    async def test_read_only_inspection_does_not_initialize_or_allow_users_fallback(self):
        result = await inspect_migration(self.db)
        self.assertEqual(result["legacy_count"], 1)
        self.assertFalse(result["unknown_external_writers_excluded_by_tool"])
        self.assertEqual(set(await self.db.list_collection_names()), {"users"})
        with self.assertRaises(PatientDomainError) as rejected:
            await self.repo.get(str(self.patient_id))
        self.assertEqual(rejected.exception.code, "PATIENT_DOMAIN_NOT_MIGRATED")

    async def test_migration_keeps_ids_users_and_business_references_with_explicit_legacy_self_link(self):
        await self.db.followup_records.insert_one({"patient_id": str(self.patient_id), "notes": "preserved"})
        before = await self.db.users.find({}).sort("_id", 1).to_list(None)
        result = await self.migrate()
        self.assertEqual(result["migrated_count"], 1)
        self.assertEqual(await self.db.users.find({}).sort("_id", 1).to_list(None), before)
        clinical = await self.repo.get(str(self.patient_id))
        self.assertEqual(clinical["_id"], self.patient_id)
        self.assertEqual(clinical["practitioners"], [self.doctor_id])
        self.assertNotIn("password_hash", clinical)
        self.assertNotIn("email", clinical)
        self.assertNotIn("role", clinical)
        self.assertEqual((await self.db.followup_records.find_one({}))["patient_id"], str(self.patient_id))
        self.assertEqual(await self.db.patient_account_links.count_documents({}), 1)
        link = await self.db.patient_account_links.find_one({})
        self.assertEqual(link["source"], "legacy_same_document")
        self.assertEqual(link["account_id"], str(self.patient_id))
        self.assertEqual(link["patient_id"], str(self.patient_id))
        self.assertEqual(link["audit"]["reviewer"], "synthetic-reviewer")
        self.assertEqual((await self.repo.resolve_self(str(self.patient_id)))["_id"], self.patient_id)
        self.assertIsNone(await self.repo.resolve_self(str(self.doctor_id)))
        self.assertEqual(await self.db.oidc_principal_bindings.count_documents({}), 0)
        backup = Path(result["backup_directory"])
        self.assertEqual((backup / "legacy-patient-accounts.bson").stat().st_mode & 0o777, 0o600)
        self.assertEqual(BSON((backup / "legacy-patient-accounts.bson").read_bytes()).decode(), self.legacy)
        self.assertEqual(json.loads((backup / "02-committed.json").read_text())["committed"], True)

    async def test_external_patient_has_no_account_or_automatic_assignment(self):
        await self.migrate()
        original_users = await self.db.users.find({}).sort("_id", 1).to_list(None)
        patient = await self.repo.create_from_source(self.source, reviewer="admin-reference", evidence_reference="review-42")
        self.assertIsNone(patient["name"])
        self.assertEqual(patient["practitioners"], [])
        self.assertEqual(patient["health_managers"], [])
        self.assertNotIn("legacy_user_id", patient)
        self.assertEqual(await self.db.users.find({}).sort("_id", 1).to_list(None), original_users)
        assigned = await self.repo.list_assigned(str(self.doctor_id), "doctor")
        self.assertEqual([item["patient_id"] for item in assigned], [str(self.patient_id)])
        self.assertEqual((await self.repo.get_response(patient["patient_id"])).source.patient_id, 99)

    async def test_missing_or_inactive_canonical_record_never_revives_legacy_user(self):
        await self.migrate()
        await self.db[PATIENTS].update_one({"_id": self.patient_id}, {"$set": {"status": "inactive"}})
        self.assertIsNone(await self.repo.get(str(self.patient_id), active_only=True))
        self.assertEqual(await self.repo.list_assigned(str(self.doctor_id), "doctor"), [])
        self.assertTrue((await self.db.users.find_one({"_id": self.patient_id}))["is_active"])
        await self.db[PATIENTS].delete_one({"_id": self.patient_id})
        self.assertIsNone(await self.repo.get(str(self.patient_id)))
        result = await self.migrate()
        self.assertTrue(result["verified_noop"])
        self.assertEqual(await self.db[PATIENTS].count_documents({}), 0)

    async def test_inactive_external_source_cannot_be_implicitly_reactivated(self):
        await self.migrate()
        document = await self.repo.create_from_source(self.source, reviewer="admin", evidence_reference="evidence")
        await self.db[PATIENTS].update_one({"_id": document["_id"]}, {"$set": {"status": "inactive"}})
        with self.assertRaises(PatientDomainError) as duplicate:
            await self.repo.create_from_source(self.source, reviewer="admin", evidence_reference="evidence")
        self.assertEqual(duplicate.exception.code, "SOURCE_PATIENT_ALREADY_EXISTS")
        self.assertEqual((await self.repo.get(document["patient_id"]))["status"], "inactive")

    async def test_concurrent_source_creation_has_only_one_patient_and_no_account(self):
        await self.migrate()
        results = await asyncio.gather(*[
            self.repo.create_from_source(self.source, reviewer="admin", evidence_reference="evidence")
            for _ in range(8)], return_exceptions=True)
        self.assertEqual(sum(isinstance(item, dict) for item in results), 1)
        self.assertEqual(await self.db.users.count_documents({}), 3)
        self.assertEqual(await self.db[PATIENTS].count_documents({"source.patient_id": 99}), 1)

    async def test_failure_rolls_back_patient_and_state_without_changing_users(self):
        for phase in ("after_insert", "before_commit"):
            with self.subTest(phase=phase), self.assertRaises(RuntimeError):
                await self.migrate(fail_at=phase)
            self.assertEqual(await self.db.patient_account_links.count_documents({}), 0)
            self.assertEqual(await self.db[PATIENTS].count_documents({}), 0)
            self.assertIsNone(await self.db[STATE].find_one({"_id": STATE_ID}))
            self.assertEqual(await self.db.users.find_one({"_id": self.patient_id}), self.legacy)
        self.assertEqual((await self.migrate())["migrated_count"], 1)

    async def test_changed_baseline_and_missing_guard_are_rejected_before_migration(self):
        expected = await inspect_migration(self.db)
        await self.db.users.update_one({"_id": self.patient_id}, {"$set": {"name": "changed"}})
        with self.assertRaises(PatientDomainError) as changed:
            await self.migrate(expected_manifest=expected)
        self.assertEqual(changed.exception.code, "PATIENT_MIGRATION_BASELINE_CHANGED")
        with self.assertRaises(PatientDomainError) as missing:
            await self.migrate(maintenance_guard=None)
        self.assertEqual(missing.exception.code, "INDEPENDENT_MAINTENANCE_GUARD_REQUIRED")

    async def test_guard_change_inside_transaction_rolls_back(self):
        calls = 0
        def guard():
            nonlocal calls
            calls += 1
            return {"application_stopped": calls < 3, "guard_reference": "synthetic-fixture"}
        with self.assertRaises(PatientDomainError):
            await self.migrate(maintenance_guard=guard)
        self.assertEqual(await self.db[PATIENTS].count_documents({}), 0)
        self.assertIsNone(await self.db[STATE].find_one({"_id": STATE_ID}))

    async def test_unexplained_clinical_data_is_never_absorbed(self):
        await self.db[PATIENTS].insert_one({"patient_id": "unknown", "status": "active"})
        with self.assertRaises(PatientDomainError) as conflict:
            await inspect_migration(self.db)
        self.assertEqual(conflict.exception.code, "UNEXPLAINED_CLINICAL_PATIENT_DATA")

    async def test_missing_or_changed_mode_refuses_reads(self):
        await self.migrate()
        await self.db[STATE].update_one({"_id": STATE_ID}, {"$set": {"mode": "legacy"}})
        with self.assertRaises(PatientDomainError):
            await self.repo.get(str(self.patient_id))
        await self.db[STATE].delete_one({"_id": STATE_ID})
        with self.assertRaises(PatientDomainError):
            await self.repo.list_assigned(str(self.doctor_id), "doctor")
        with self.assertRaises(PatientDomainError):
            await self.migrate()

    async def test_source_write_refuses_missing_unique_index(self):
        await self.migrate()
        await self.db[PATIENTS].drop_index("clinical_source_patient_unique")
        with self.assertRaises(PatientDomainError) as rejected:
            await self.repo.create_from_source(self.source, reviewer="admin", evidence_reference="evidence")
        self.assertEqual(rejected.exception.code, "PATIENT_DOMAIN_INDEX_MISSING")

    async def test_backup_replacement_or_tamper_rolls_back_before_commit(self):
        for replacement in (False, True):
            backup = self.root / uuid4().hex
            calls = 0
            def guard():
                nonlocal calls
                calls += 1
                if calls == 3:
                    path = backup / "legacy-patient-accounts.bson"
                    if replacement:
                        same_bytes = path.read_bytes()
                        other = backup / "replacement.bson"
                        other.write_bytes(same_bytes)
                        other.chmod(0o600)
                        other.replace(path)
                    else:
                        with path.open("ab") as stream:
                            stream.write(b"tampered")
                return self.stopped()
            with self.subTest(replacement=replacement), self.assertRaises(PatientDomainError) as rejected:
                await self.migrate(backup_directory=backup, maintenance_guard=guard)
            self.assertEqual(rejected.exception.code, "PATIENT_MIGRATION_BACKUP_CHANGED")
            self.assertEqual(await self.db.patient_account_links.count_documents({}), 0)
            self.assertEqual(await self.db[PATIENTS].count_documents({}), 0)
            self.assertIsNone(await self.db[STATE].find_one({"_id": STATE_ID}))

    async def test_empty_legacy_database_can_enable_source_only_patients(self):
        await self.db.users.delete_many({"role": "patient"})
        result = await self.migrate()
        self.assertEqual(result["migrated_count"], 0)
        document = await self.repo.create_from_source(self.source, reviewer="admin", evidence_reference="review")
        self.assertEqual((await self.repo.get_response(document["patient_id"])).status, "active")
        self.assertEqual(await self.db.users.count_documents({}), 2)

    async def test_concurrent_migrations_do_not_overwrite_or_duplicate_patients(self):
        expected = await inspect_migration(self.db)
        outcomes = await asyncio.gather(*[self.migrate(expected_manifest=expected)
                                         for _ in range(2)], return_exceptions=True)
        self.assertTrue(any(isinstance(outcome, dict) for outcome in outcomes))
        self.assertEqual(await self.db[PATIENTS].count_documents({}), 1)
        self.assertEqual(await self.db.patient_account_links.count_documents({}), 1)
        self.assertEqual(await self.db.users.find_one({"_id": self.patient_id}), self.legacy)
        self.assertEqual((await self.db[STATE].find_one({"_id": STATE_ID}))["mode"], "canonical")

    async def test_duplicate_normalized_legacy_ids_fail_before_writes(self):
        await self.db.users.insert_one({"_id": str(self.patient_id), "role": "patient"})
        with self.assertRaises(PatientDomainError) as ambiguous:
            await self.migrate()
        self.assertEqual(ambiguous.exception.code, "AMBIGUOUS_LEGACY_PATIENT_ID")
        self.assertEqual(await self.db[PATIENTS].count_documents({}), 0)

    async def test_self_access_requires_live_explicit_relation_and_never_recreates_it(self):
        await self.migrate()
        for collection, query, update, restore in (
            ("users", {"_id": self.patient_id}, {"is_active": False}, {"is_active": True}),
            ("users", {"_id": self.patient_id}, {"role": "doctor"}, {"role": "patient"}),
            (PATIENTS, {"_id": self.patient_id}, {"status": "inactive"}, {"status": "active"}),
            ("patient_account_links", {}, {"status": "disabled"}, {"status": "verified"}),
            ("patient_account_links", {}, {"patient_id": str(self.doctor_id)}, {"patient_id": str(self.patient_id)}),
        ):
            await self.db[collection].update_one(query, {"$set": update})
            self.assertIsNone(await self.repo.resolve_self(str(self.patient_id)))
            await self.migrate()  # idempotence cannot repair disabled or tampered links
            self.assertIsNone(await self.repo.resolve_self(str(self.patient_id)))
            await self.db[collection].update_one(query, {"$set": restore})
        await self.db.patient_account_links.delete_many({})
        await self.migrate()
        self.assertIsNone(await self.repo.resolve_self(str(self.patient_id)))
        self.assertEqual(await self.db.patient_account_links.count_documents({}), 0)

    async def test_inactive_legacy_accounts_stay_disabled_even_if_account_later_enabled(self):
        await self.db.users.update_one({"_id": self.patient_id}, {"$set": {"is_active": False}})
        await self.migrate()
        self.assertEqual((await self.db.patient_account_links.find_one({}))["status"], "disabled")
        await self.db.users.update_one({"_id": self.patient_id}, {"$set": {"is_active": True}})
        self.assertIsNone(await self.repo.resolve_self(str(self.patient_id)))

    async def test_unexplained_account_links_refuse_migration(self):
        await self.db.patient_account_links.insert_one({"account_id": "unknown", "patient_id": "unknown"})
        with self.assertRaises(PatientDomainError) as rejected:
            await self.migrate()
        self.assertEqual(rejected.exception.code, "UNEXPLAINED_PATIENT_ACCOUNT_LINK_DATA")
        self.assertEqual(await self.db[PATIENTS].count_documents({}), 0)

    async def test_ambiguous_account_document_does_not_gain_self_access(self):
        await self.migrate()
        await self.db.users.insert_one({"_id": str(self.patient_id), "role": "doctor", "is_active": True})
        self.assertIsNone(await self.repo.resolve_self(str(self.patient_id)))

    async def test_source_creation_and_external_link_share_transaction_and_rollback(self):
        await self.migrate()
        for fail in (True, False):
            try:
                async with await self.client.start_session() as session:
                    async with session.start_transaction():
                        document = await self.repo.create_from_source(self.source, reviewer="admin",
                            evidence_reference="review", session=session)
                        await self.db.synthetic_external_links.insert_one({"patient_id": document["patient_id"]}, session=session)
                        await self.db.synthetic_audit.insert_one({"patient_id": document["patient_id"]}, session=session)
                        if fail:
                            raise RuntimeError("synthetic upper-layer failure")
            except RuntimeError:
                if not fail:
                    raise
            self.assertEqual(await self.db[PATIENTS].count_documents({"source.patient_id": 99}), int(not fail))
            self.assertEqual(await self.db.synthetic_external_links.count_documents({}), int(not fail))
            self.assertEqual(await self.db.synthetic_audit.count_documents({}), int(not fail))
        self.assertIsNone(await self.repo.resolve_self(document["patient_id"]))
        self.assertEqual(await self.db.patient_account_links.count_documents({}), 1)
        self.assertEqual(await self.db.users.count_documents({}), 3)

    async def test_concurrent_source_transactions_commit_one_complete_bundle(self):
        await self.migrate()
        async def attempt():
            async with await self.client.start_session() as session:
                async with session.start_transaction():
                    document = await self.repo.create_from_source(self.source, reviewer="admin",
                        evidence_reference="review", session=session)
                    await self.db.synthetic_external_links.insert_one({"patient_id": document["patient_id"]}, session=session)
                    await self.db.synthetic_audit.insert_one({"patient_id": document["patient_id"]}, session=session)
                    return document
        results = await asyncio.gather(*[attempt() for _ in range(4)], return_exceptions=True)
        self.assertEqual(sum(isinstance(item, dict) for item in results), 1)
        self.assertEqual(await self.db[PATIENTS].count_documents({"source.patient_id": 99}), 1)
        self.assertEqual(await self.db.synthetic_external_links.count_documents({}), 1)
        self.assertEqual(await self.db.synthetic_audit.count_documents({}), 1)

    async def test_transaction_refuses_malformed_or_removed_index(self):
        await self.migrate()
        await self.db[PATIENTS].drop_index("clinical_source_patient_unique")
        await self.db[PATIENTS].create_index("source_key", name="clinical_source_patient_unique")
        async with await self.client.start_session() as session:
            with self.assertRaises(PatientDomainError) as rejected:
                async with session.start_transaction():
                    await self.repo.create_from_source(self.source, reviewer="admin", evidence_reference="review", session=session)
            self.assertEqual(rejected.exception.code, "PATIENT_DOMAIN_INDEX_MISSING")
        await self.db[PATIENTS].drop_index("clinical_source_patient_unique")
        await self.db[PATIENTS].create_index("source_key", unique=True, name="clinical_source_patient_unique",
                                           partialFilterExpression={"source_key": {"$type": "string"}})
        real_metadata = self.repo.collection.index_information
        async def ddl_after_metadata(**kwargs):
            metadata = await real_metadata(**kwargs)
            await self.db[PATIENTS].drop_index("clinical_source_patient_unique")
            return metadata
        with patch.object(self.repo.collection, "index_information", side_effect=ddl_after_metadata):
            async with await self.client.start_session() as session:
                with self.assertRaises((PatientDomainError, OperationFailure)) as removed:
                    async with session.start_transaction():
                        await self.repo.create_from_source(self.source, reviewer="admin", evidence_reference="review", session=session)
                self.assertIn(removed.exception.code, ("PATIENT_DOMAIN_INDEX_CHECK_FAILED", 112))
        self.assertEqual(await self.db[PATIENTS].count_documents({"source.patient_id": 99}), 0)

    async def test_index_metadata_operation_failure_is_closed(self):
        await self.migrate()
        with patch.object(self.repo.collection, "index_information", side_effect=OperationFailure("synthetic")):
            with self.assertRaises(PatientDomainError) as rejected:
                await self.repo.create_from_source(self.source, reviewer="admin", evidence_reference="review")
            self.assertEqual(rejected.exception.code, "PATIENT_DOMAIN_INDEX_CHECK_FAILED")
        self.assertEqual(await self.db[PATIENTS].count_documents({"source.patient_id": 99}), 0)
