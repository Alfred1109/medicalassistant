"""A verified questionnaire login can request access; an admin binds an existing local person."""
import unittest
from types import SimpleNamespace

from bson import ObjectId
from fastapi import HTTPException

from app.integrations.identity.applications import decide_application, submit_application


class Collection:
    def __init__(self):
        self.docs = []

    async def create_index(self, *args, **kwargs):
        return "index"

    async def find_one(self, query, sort=None):
        rows = [doc for doc in self.docs if all(doc.get(key) == value for key, value in query.items())]
        if sort:
            rows.sort(key=lambda doc: doc.get(sort[0][0]) or "", reverse=sort[0][1] < 0)
        return rows[0] if rows else None

    async def insert_one(self, document):
        if any(doc.get("issuer") == document.get("issuer") and doc.get("subject") == document.get("subject")
               and doc.get("status") == "pending" and document.get("status") == "pending" for doc in self.docs):
            raise type("DuplicateKeyError", (Exception,), {})("duplicate")
        self.docs.append(document)

    async def update_one(self, query, update):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(update["$set"])
                return

    def find(self, query):
        return _Cursor([doc for doc in self.docs if all(doc.get(key) == value for key, value in query.items())])


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *args):
        return self

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        if self._index >= len(self.rows):
            raise StopAsyncIteration
        row = self.rows[self._index]
        self._index += 1
        return row


class Database:
    def __init__(self):
        self.access_applications = Collection()
        self.users = Collection()
        self.oidc_principal_bindings = Collection()


class AccessApplicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_pending_login_can_apply_once_and_admin_binds_matching_role(self):
        db = Database()
        actor_id = ObjectId()
        db.users.docs.append({"_id": actor_id, "role": "patient", "is_active": True})
        session = {"authenticated": True, "identity_state": "pending_binding",
                   "issuer": "https://forms.example.test", "subject": "subject-1"}
        first = await submit_application(db, session, "patient", "申请查看康复记录")
        second = await submit_application(db, session, "patient", "再次提交")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["status"], "pending")
        admin = SimpleNamespace(id=ObjectId(), role="admin")
        approved = await decide_application(
            db, admin, first["id"], approved=True, local_user_id=str(actor_id),
            evidence_reference="核实记录 2026-11-10", reason="")
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(db.oidc_principal_bindings.docs[0]["approved_role"], "patient")

    async def test_bound_login_cannot_apply(self):
        with self.assertRaises(HTTPException) as caught:
            await submit_application(Database(), {"authenticated": True, "identity_state": "bound"}, "patient", "")
        self.assertEqual(caught.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
