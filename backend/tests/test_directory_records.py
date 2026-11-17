"""Tags and consent documents persist instead of returning an empty stub."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bson import ObjectId
from fastapi import HTTPException

from app.directory.records import create_tag, issue_consent, list_consents, read_consent, sign_consent


class Result:
    def __init__(self, count):
        self.deleted_count = count
        self.matched_count = count


class Collection:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, **kwargs):
        for doc in self.docs:
            if all((doc.get(key) in value["$in"] if isinstance(value, dict) and "$in" in value else doc.get(key) == value) for key, value in query.items()):
                return doc
        return None

    async def insert_one(self, document):
        self.docs.append(document)

    async def update_one(self, query, update, **kwargs):
        for doc in self.docs:
            if doc.get("_id") == query.get("_id") and all(doc.get(key) == value for key, value in query.items() if key != "_id"):
                doc.update(update.get("$set", {}))
                for key, amount in update.get("$inc", {}).items():
                    doc[key] = doc.get(key, 0) + amount
                return Result(1)
        return Result(0)

    async def find_one_and_update(self, query, update, **kwargs):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                for key, amount in update.get("$inc", {}).items():
                    doc[key] = doc.get(key, 0) + amount
                doc.update(update.get("$set", {}))
                return doc
        return None

    def find(self, query, projection=None, **kwargs):
        return _Cursor([doc for doc in self.docs if all((doc.get(key) in value["$in"] if isinstance(value, dict) and "$in" in value else doc.get(key) == value) for key, value in query.items())])


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self._index = 0

    async def to_list(self, length=None):
        return list(self.rows if length is None else self.rows[:length])

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self.rows):
            raise StopAsyncIteration
        row = self.rows[self._index]
        self._index += 1
        return row


class Database:
    def __init__(self):
        self.tags = Collection()
        self.users = Collection()
        self.consent_templates = Collection()
        self.consent_documents = RacingCollection()
        self.patient_account_links = Collection()
        self.clinical_patients = Collection()

    def __getitem__(self, name):
        return getattr(self, name)


class CanonicalPatientContext:
    is_canonical = True

    def __init__(self, patient_id):
        self.patient_id = patient_id

    async def ensure_self_patient_access(self, actor, patient_id=None):
        if patient_id is not None and str(patient_id) != self.patient_id:
            raise HTTPException(403, detail={"code": "PATIENT_NOT_ASSIGNED"})
        return self.patient_id

    async def ensure_patient_access(self, patient_id, operator_id, operator_role):
        return {"patient_id": self.patient_id, "_id": "storage-object-id", "name": "甲"}

    async def load_patient_doc(self, patient_id):
        return {"patient_id": self.patient_id, "_id": "storage-object-id", "name": "甲"}

    def entity_id(self, patient):
        return str(patient["patient_id"])


class RacingCollection(Collection):
    def __init__(self):
        super().__init__()
        self.race_to_status = None
        self.force_no_match = False

    async def update_one(self, query, update, **kwargs):
        if self.race_to_status:
            document = next((row for row in self.docs if row.get("_id") == query.get("_id")), None)
            if document:
                document["status"] = self.race_to_status
                document["signed_name"] = "并发签署者"
                self.race_to_status = None
            return Result(0)
        if self.force_no_match:
            return Result(0)
        return await super().update_one(query, update)


async def in_memory_transaction(db, callback, **kwargs):
    return await callback(None)


class DirectoryRecordTests(unittest.IsolatedAsyncioTestCase):
    async def test_tag_is_unique_and_patient_signature_is_stored(self):
        db = Database()
        created = await create_tag(db, "康复", "宣教", "")
        with self.assertRaises(HTTPException):
            await create_tag(db, "康复", "宣教", "")
        self.assertEqual(created["name"], "康复")
        patient_id = ObjectId()
        doctor_id = ObjectId()
        db.users.docs.append({"_id": patient_id, "role": "patient", "name": "甲", "practitioners": [str(doctor_id)]})
        doctor = SimpleNamespace(id=doctor_id, role="doctor")
        template = await __import__("app.directory.records", fromlist=["create_template"]).create_template(
            db, doctor, "步行说明", "我已阅读正文。")
        issued = await issue_consent(db, doctor, template["id"], str(patient_id))
        with patch("app.directory.records.run_transaction", new=in_memory_transaction):
            signed = await sign_consent(db, SimpleNamespace(id=patient_id, role="patient"), issued["id"], "甲", True)
        self.assertEqual(signed["status"], "signed")
        self.assertEqual(signed["signed_name"], "甲")

    async def test_patient_consent_list_and_detail_resolve_canonical_entity(self):
        db = Database()
        account_id = ObjectId()
        db.consent_documents.docs.extend([
            {"_id": ObjectId(), "patient_id": "clinical-patient-1", "title": "本人同意书", "body": "正文", "status": "pending"},
            {"_id": ObjectId(), "patient_id": str(account_id), "title": "非本人", "body": "正文", "status": "pending"},
        ])
        actor = SimpleNamespace(id=account_id, role="patient")
        context = CanonicalPatientContext("clinical-patient-1")
        with patch("app.directory.records.patient_domain_context", new=AsyncMock(return_value=context)):
            listed = await list_consents(db, actor)
            self.assertEqual([row["title"] for row in listed], ["本人同意书"])
            detail = await read_consent(db, actor, listed[0]["id"])
            self.assertEqual(detail["patient_id"], "clinical-patient-1")

    async def test_doctor_consent_list_and_detail_use_patient_domain_context(self):
        db = Database()
        document_id = ObjectId()
        db.consent_documents.docs.append({"_id": document_id, "patient_id": "clinical-patient-1",
                                          "created_by": "other-doctor", "title": "知情同意",
                                          "body": "正文", "status": "pending"})
        context = CanonicalPatientContext("clinical-patient-1")
        actor = SimpleNamespace(id="doctor-1", role="doctor")
        with patch("app.directory.records.patient_domain_context", new=AsyncMock(return_value=context)):
            listed = await list_consents(db, actor, "clinical-patient-1")
            detail = await read_consent(db, actor, str(document_id))
        self.assertEqual(len(listed), 1)
        self.assertEqual(detail["patient_id"], "clinical-patient-1")

    async def test_patient_consent_issue_stores_canonical_patient_id(self):
        db = Database()
        db.consent_templates.docs.append({"_id": ObjectId(), "title": "知情同意", "body": "正文", "active": True})
        context = CanonicalPatientContext("clinical-patient-1")
        with patch("app.directory.records.patient_domain_context", new=AsyncMock(return_value=context)):
            document = await issue_consent(db, SimpleNamespace(id="doctor-1", role="doctor"),
                                           str(db.consent_templates.docs[0]["_id"]), "clinical-patient-1")
        self.assertEqual(document["patient_id"], "clinical-patient-1")

    async def test_canonical_signature_serializes_link_account_and_patient_access(self):
        db = Database()
        account_id = ObjectId()
        document_id = ObjectId()
        db.users.docs.append({"_id": account_id, "role": "patient", "is_active": True})
        db.patient_account_links.docs.append({"_id": "binding-1", "account_id": str(account_id),
                                               "patient_id": "patient-1", "status": "verified"})
        db.clinical_patients.docs.append({"_id": "patient-storage-1", "patient_id": "patient-1", "status": "active"})
        db.consent_documents.docs.append({"_id": document_id, "patient_id": "patient-1", "title": "知情同意",
                                           "body": "正文", "status": "pending"})
        context = CanonicalPatientContext("patient-1")
        with patch("app.directory.records.patient_domain_context", new=AsyncMock(return_value=context)), \
             patch("app.directory.records.run_transaction", new=in_memory_transaction):
            result = await sign_consent(db, SimpleNamespace(id=account_id, role="patient"), str(document_id), "甲", True)
        self.assertEqual(result["status"], "signed")
        self.assertEqual(db.patient_account_links.docs[0]["_consent_access_fence"], 1)
        self.assertEqual(db.clinical_patients.docs[0]["_fence_consent"], 1)
        self.assertEqual(db.users.docs[0]["_access_fence"], 1)

    async def test_patient_can_record_declined_decision(self):
        db = Database()
        account_id = ObjectId()
        document_id = ObjectId()
        db.users.docs.append({"_id": account_id, "role": "patient", "is_active": True})
        db.patient_account_links.docs.append({"_id": "binding-1", "account_id": str(account_id),
                                               "patient_id": "patient-1", "status": "verified"})
        db.clinical_patients.docs.append({"_id": "patient-storage-1", "patient_id": "patient-1", "status": "active"})
        db.consent_documents.docs.append({"_id": document_id, "patient_id": "patient-1", "title": "知情同意",
                                           "body": "正文", "status": "pending"})
        context = CanonicalPatientContext("patient-1")
        with patch("app.directory.records.patient_domain_context", new=AsyncMock(return_value=context)), \
             patch("app.directory.records.run_transaction", new=in_memory_transaction):
            result = await sign_consent(db, SimpleNamespace(id=account_id, role="patient"), str(document_id), "", False)
        self.assertEqual(result["status"], "declined")
        self.assertEqual(result["signed_name"], "")

    async def test_consent_signature_race_returns_conflict_and_current_state(self):
        db = Database()
        db.consent_documents = RacingCollection()
        document_id = ObjectId()
        db.consent_documents.docs.append({"_id": document_id, "patient_id": "patient-1", "title": "知情同意",
                                          "body": "正文", "status": "pending"})
        account_id = ObjectId()
        db.users.docs.append({"_id": account_id, "role": "patient", "is_active": True})
        db.patient_account_links.docs.append({"_id": "binding-1", "account_id": str(account_id),
                                               "patient_id": "patient-1", "status": "verified"})
        db.clinical_patients.docs.append({"_id": "patient-storage-1", "patient_id": "patient-1", "status": "active"})
        db.consent_documents.race_to_status = "declined"
        context = CanonicalPatientContext("patient-1")
        with patch("app.directory.records.patient_domain_context", new=AsyncMock(return_value=context)), \
             patch("app.directory.records.run_transaction", new=in_memory_transaction):
            with self.assertRaises(HTTPException) as raised:
                await sign_consent(db, SimpleNamespace(id=account_id, role="patient"), str(document_id), "甲", True)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["current_status"], "declined")
        self.assertEqual(db.consent_documents.docs[0]["signed_name"], "并发签署者")

    async def test_consent_signature_conflict_does_not_claim_success(self):
        db = Database()
        db.consent_documents = RacingCollection()
        document_id = ObjectId()
        db.consent_documents.docs.append({"_id": document_id, "patient_id": "patient-1", "title": "知情同意",
                                          "body": "正文", "status": "pending"})
        account_id = ObjectId()
        db.users.docs.append({"_id": account_id, "role": "patient", "is_active": True})
        db.patient_account_links.docs.append({"_id": "binding-1", "account_id": str(account_id),
                                               "patient_id": "patient-1", "status": "verified"})
        db.clinical_patients.docs.append({"_id": "patient-storage-1", "patient_id": "patient-1", "status": "active"})
        db.consent_documents.force_no_match = True
        context = CanonicalPatientContext("patient-1")
        with patch("app.directory.records.patient_domain_context", new=AsyncMock(return_value=context)), \
             patch("app.directory.records.run_transaction", new=in_memory_transaction):
            with self.assertRaises(HTTPException) as raised:
                await sign_consent(db, SimpleNamespace(id=account_id, role="patient"), str(document_id), "甲", True)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["code"], "CONSENT_CONCURRENT_UPDATE")
        self.assertEqual(raised.exception.detail["current_status"], "pending")


if __name__ == "__main__":
    unittest.main()
