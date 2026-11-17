"""Real transaction, canonical identity, and consent revocation races.

Run only against an explicitly configured loopback replica set:
REHAB_TEST_CONSENT_URI='mongodb://127.0.0.1:37027/?directConnection=true'
"""
import asyncio
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.patient_access import PatientAccessError, patient_domain_context
from app.directory import records
from app.patients.repository import ClinicalPatientRepository

URI = os.environ.get("REHAB_TEST_CONSENT_URI")
STATE = "patient_domain_state"
STATE_ID = "clinical-patients-v1"


@unittest.skipUnless(URI, "set REHAB_TEST_CONSENT_URI to an isolated local replica set")
class ConsentReplicaSetTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if not URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")):
            self.fail("only an explicit loopback test URI is accepted")
        self.client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=5000)
        self.db = self.client["consent_records_" + uuid4().hex]
        self.rival = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=5000)
        self.rival_db = self.rival[self.db.name]
        self.account_id = ObjectId()
        self.patient_id = str(ObjectId())
        self.document_id = ObjectId()
        await self.db[STATE].insert_one({"_id": STATE_ID, "mode": "canonical", "schema_version": 1})
        await self.db.users.insert_one({"_id": self.account_id, "role": "patient", "is_active": True})
        await self.db.clinical_patients.insert_one({
            "_id": ObjectId(), "patient_id": self.patient_id, "status": "active",
            "practitioners": [], "health_managers": [],
        })
        await self.db.patient_account_links.insert_one({
            "_id": "explicit:" + self.patient_id,
            "account_id": str(self.account_id), "account_document_id": self.account_id,
            "patient_id": self.patient_id, "source": "explicit_binding",
            "schema_version": 1, "status": "verified",
            "bound_at": records._now(),
            "audit": [{"reviewer": "test reviewer", "evidence_reference": "test://verified-binding",
                       "operation": "explicit_binding", "at": records._now()}],
        })
        await self.db.consent_documents.insert_one({
            "_id": self.document_id, "patient_id": self.patient_id,
            "title": "隔离副本集测试同意书", "body": "测试正文", "status": "pending",
        })
        self.actor = type("Actor", (), {"id": self.account_id, "role": "patient"})()

    async def asyncTearDown(self):
        await self.client.drop_database(self.db.name)
        self.client.close()
        self.rival.close()

    async def test_canonical_account_maps_to_clinical_patient_and_signature_commits(self):
        listed = await records.list_consents(self.db, self.actor)
        self.assertEqual([row["patient_id"] for row in listed], [self.patient_id])
        detail = await records.read_consent(self.db, self.actor, str(self.document_id))
        self.assertEqual(detail["patient_id"], self.patient_id)

        signed = await records.sign_consent(self.db, self.actor, str(self.document_id), "测试患者", True)
        stored = await self.db.consent_documents.find_one({"_id": self.document_id})
        link = await self.db.patient_account_links.find_one({"account_id": str(self.account_id)})
        patient = await self.db.clinical_patients.find_one({"patient_id": self.patient_id})
        account = await self.db.users.find_one({"_id": self.account_id})
        self.assertEqual(signed["status"], "signed")
        self.assertEqual(stored["status"], "signed")
        self.assertEqual(stored["signed_name"], "测试患者")
        self.assertGreater(link.get("_consent_access_fence", 0), 0)
        self.assertGreater(patient.get("_fence_consent", 0), 0)
        self.assertGreater(account.get("_access_fence", 0), 0)

    async def test_concurrent_accept_and_decline_have_one_winner_and_one_conflict(self):
        arrived = 0
        both_arrived = asyncio.Event()
        original_context = patient_domain_context

        async def context_barrier(db, *, session=None):
            nonlocal arrived
            context = await original_context(db, session=session)
            if arrived < 2:
                arrived += 1
                if arrived == 2:
                    both_arrived.set()
                await asyncio.wait_for(both_arrived.wait(), timeout=10)
            return context

        with patch("app.directory.records.patient_domain_context", new=context_barrier):
            outcomes = await asyncio.gather(
                records.sign_consent(self.db, self.actor, str(self.document_id), "测试患者", True),
                records.sign_consent(self.db, self.actor, str(self.document_id), "", False),
                return_exceptions=True,
            )
        success = [item for item in outcomes if isinstance(item, dict)]
        conflicts = [item for item in outcomes if isinstance(item, HTTPException)]
        stored = await self.db.consent_documents.find_one({"_id": self.document_id})
        self.assertEqual(len(success), 1, outcomes)
        self.assertEqual(len(conflicts), 1, outcomes)
        self.assertEqual(conflicts[0].status_code, 409)
        self.assertEqual(stored["status"], success[0]["status"])
        self.assertIn(stored["status"], {"signed", "declined"})

    async def test_binding_revocation_wins_before_concurrent_signature_commit(self):
        authorization_checked = asyncio.Event()
        revocation_committed = asyncio.Event()
        original_context = patient_domain_context
        first_check = True

        class GatedContext:
            def __init__(self, context):
                self._context = context
                self.is_canonical = context.is_canonical

            async def ensure_self_patient_access(self, actor, patient_id=None):
                nonlocal first_check
                result = await self._context.ensure_self_patient_access(actor, patient_id)
                if first_check:
                    first_check = False
                    authorization_checked.set()
                    await asyncio.wait_for(revocation_committed.wait(), timeout=10)
                return result

            def __getattr__(self, name):
                return getattr(self._context, name)

        async def context_gate(db, *, session=None):
            return GatedContext(await original_context(db, session=session))

        async def signature_attempt():
            return await records.sign_consent(self.db, self.actor, str(self.document_id), "测试患者", True)

        with patch("app.directory.records.patient_domain_context", new=context_gate):
            signature = asyncio.create_task(signature_attempt())
            await asyncio.wait_for(authorization_checked.wait(), timeout=10)
            await ClinicalPatientRepository(self.rival_db).disable_account_link(
                self.patient_id, reviewer="test reviewer", evidence_reference="test://revocation")
            revocation_committed.set()
            with self.assertRaises(PatientAccessError):
                await asyncio.wait_for(signature, timeout=15)

        stored = await self.db.consent_documents.find_one({"_id": self.document_id})
        link = await self.db.patient_account_links.find_one({"patient_id": self.patient_id})
        self.assertEqual(stored["status"], "pending")
        self.assertEqual(link["status"], "disabled")

    async def test_failure_after_authorization_writes_rolls_back_all_fences(self):
        with patch("app.directory.records._now", side_effect=RuntimeError("forced transaction failure")):
            with self.assertRaisesRegex(RuntimeError, "forced transaction failure"):
                await records.sign_consent(self.db, self.actor, str(self.document_id), "测试患者", True)
        stored = await self.db.consent_documents.find_one({"_id": self.document_id})
        account = await self.db.users.find_one({"_id": self.account_id})
        link = await self.db.patient_account_links.find_one({"patient_id": self.patient_id})
        patient = await self.db.clinical_patients.find_one({"patient_id": self.patient_id})
        self.assertEqual(stored["status"], "pending")
        self.assertNotIn("_access_fence", account)
        self.assertNotIn("_consent_access_fence", link)
        self.assertNotIn("_fence_consent", patient)


if __name__ == "__main__":
    unittest.main()
