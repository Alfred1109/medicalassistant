"""Tags and consent documents persist instead of returning an empty stub."""
import unittest
from types import SimpleNamespace

from bson import ObjectId
from fastapi import HTTPException

from app.directory.records import create_tag, issue_consent, sign_consent


class Result:
    def __init__(self, count):
        self.deleted_count = count
        self.matched_count = count


class Collection:
    def __init__(self):
        self.docs = []

    async def find_one(self, query):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return doc
        return None

    async def insert_one(self, document):
        self.docs.append(document)

    async def update_one(self, query, update):
        for doc in self.docs:
            if doc.get("_id") == query.get("_id") and all(doc.get(key) == value for key, value in query.items() if key != "_id"):
                doc.update(update["$set"])
                return Result(1)
        return Result(0)

    def find(self, query):
        return _Cursor([doc for doc in self.docs if all(doc.get(key) == value for key, value in query.items())])


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self._index = 0

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
        self.consent_documents = Collection()


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
        signed = await sign_consent(db, SimpleNamespace(id=patient_id, role="patient"), issued["id"], "甲", True)
        self.assertEqual(signed["status"], "signed")
        self.assertEqual(signed["signed_name"], "甲")


if __name__ == "__main__":
    unittest.main()
