"""Authorization tests for the scoped communication contact directory."""
import unittest
from unittest.mock import AsyncMock, patch

from bson import ObjectId

from app.core.exceptions import AppBaseException
from app.services.communication_service import CommunicationService


class Cursor:
    def __init__(self, documents):
        self.documents = documents

    async def to_list(self, length=None):
        return list(self.documents if length is None else self.documents[:length])


class Collection:
    def __init__(self, documents=()):
        self.documents = list(documents)

    @staticmethod
    def _same_identifier(left, right):
        return str(left) == str(right)

    def find(self, query, projection=None, session=None):
        values = query.get("_id", {}).get("$in", [])
        documents = [doc for doc in self.documents
                     if any(self._same_identifier(doc["_id"], value) for value in values)]
        return Cursor(documents)

    async def find_one(self, query, session=None):
        identifier = query.get("_id")
        if identifier is not None:
            return next((doc for doc in self.documents
                         if self._same_identifier(doc["_id"], identifier)), None)
        alternatives = query.get("$or", [])
        for document in self.documents:
            if query.get("type") and document.get("type") != query["type"]:
                continue
            if any(all(document.get(key) == value for key, value in clause.items())
                   for clause in alternatives):
                return document
        return None

    async def insert_one(self, document, session=None):
        self.documents.append(document)


class Database:
    def __init__(self, users=(), conversations=()):
        self.users = Collection(users)
        self.conversations = Collection(conversations)
        self.clinical_patients = Collection()

    def __getitem__(self, name):
        return getattr(self, name)


class CommunicationContactTests(unittest.IsolatedAsyncioTestCase):
    async def test_patient_directory_uses_only_assigned_active_role_accounts(self):
        patient_id = ObjectId()
        doctor_id = ObjectId()
        manager_id = ObjectId()
        inactive_id = ObjectId()
        wrong_role_id = ObjectId()
        db = Database([
            {"_id": patient_id, "role": "patient", "is_active": True},
            {"_id": doctor_id, "role": "doctor", "is_active": True, "name": "医生"},
            {"_id": manager_id, "role": "health_manager", "is_active": True, "name": "管理师"},
            {"_id": inactive_id, "role": "doctor", "is_active": False, "name": "停用医生"},
            {"_id": wrong_role_id, "role": "patient", "is_active": True, "name": "错误角色"},
        ])
        patient = {"_id": patient_id, "practitioners": [str(doctor_id), str(inactive_id), str(wrong_role_id)],
                   "health_managers": [str(manager_id)]}
        with patch("app.services.communication_service.ensure_self_patient_access",
                   new=AsyncMock(return_value=str(patient_id))), \
             patch("app.services.communication_service.load_patient_doc",
                   new=AsyncMock(return_value=patient)):
            contacts = await CommunicationService.get_care_contacts(db, str(patient_id), "patient")

        self.assertEqual({(item["id"], item["role"]) for item in contacts}, {
            (str(doctor_id), "doctor"), (str(manager_id), "health_manager")})
        self.assertTrue(all(set(item) == {"id", "name", "role"} for item in contacts))

    async def test_ambiguous_patient_contact_fails_closed(self):
        patient_id, doctor_id = ObjectId(), ObjectId()
        db = Database([
            {"_id": patient_id, "role": "patient", "is_active": True},
            {"_id": doctor_id, "role": "doctor", "is_active": True, "name": "医生1"},
            {"_id": str(doctor_id), "role": "doctor", "is_active": True, "name": "医生2"},
        ])
        patient = {"_id": patient_id, "practitioners": [str(doctor_id)], "health_managers": []}
        with patch("app.services.communication_service.ensure_self_patient_access",
                   new=AsyncMock(return_value=str(patient_id))), \
             patch("app.services.communication_service.load_patient_doc",
                   new=AsyncMock(return_value=patient)):
            with self.assertRaises(AppBaseException) as raised:
                await CommunicationService.get_care_contacts(db, str(patient_id), "patient")
        self.assertEqual(raised.exception.error_code, "COMMUNICATION_CONTACT_AMBIGUOUS")

    async def test_canonical_staff_directory_requires_verified_reverse_checked_account_link(self):
        staff_id = str(ObjectId())
        patient_id = "clinical-patient-7"
        account_id = str(ObjectId())
        db = Database([
            {"_id": ObjectId(staff_id), "role": "doctor", "is_active": True},
            {"_id": ObjectId(account_id), "role": "patient", "is_active": True, "name": "已绑定"},
        ])
        with patch("app.services.communication_service.assigned_scope_ids",
                   new=AsyncMock(return_value=[patient_id])), \
             patch("app.services.communication_service.patient_domain_mode",
                   new=AsyncMock(return_value="canonical")), \
             patch("app.services.communication_service.linked_account_id",
                   new=AsyncMock(return_value=account_id)), \
             patch("app.services.communication_service.ClinicalPatientRepository.resolve_self",
                   new=AsyncMock(return_value={"patient_id": patient_id})):
            contacts = await CommunicationService.get_care_contacts(db, staff_id, "doctor")
        self.assertEqual(contacts, [{"id": account_id, "name": "已绑定", "role": "patient"}])

    async def test_authorized_creation_reuses_existing_and_rejects_out_of_scope_target(self):
        actor_id, target_id = str(ObjectId()), str(ObjectId())
        db = Database(conversations=[])
        transaction_sessions = []

        async def transaction_runner(database, callback, **kwargs):
            session = object()
            transaction_sessions.append(session)
            return await callback(session)

        with patch.object(CommunicationService, "get_care_contacts",
                          new=AsyncMock(return_value=[{"id": target_id, "name": "患者", "role": "patient"}])), \
             patch("app.services.communication_service.run_transaction", new=transaction_runner), \
             patch("app.services.communication_service.ConversationPolicy._authorize_patient_staff_pair", \
                   new=AsyncMock(return_value=True)), \
             patch("app.services.communication_service.NotificationService.create_notification",
                   new=AsyncMock()):
            first = await CommunicationService.create_authorized_conversation(
                db, actor_id, "doctor", target_id)
            second = await CommunicationService.create_authorized_conversation(
                db, actor_id, "doctor", target_id)
            self.assertEqual(first, second)
            self.assertEqual(len(db.conversations.documents), 1)
            with self.assertRaises(AppBaseException) as raised:
                await CommunicationService.create_authorized_conversation(
                    db, actor_id, "doctor", str(ObjectId()))

        self.assertEqual(raised.exception.error_code, "COMMUNICATION_CONTACT_FORBIDDEN")
        self.assertEqual(len(transaction_sessions), 3)


if __name__ == "__main__":
    unittest.main()
