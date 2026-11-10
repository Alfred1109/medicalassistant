"""Project roster import assigns subjects as patients and leaves members unspecified."""
import unittest
from types import SimpleNamespace

from bson import ObjectId

from app.integrations.forms.people_import import assign_imported_role, import_project_people, set_imported_care


class Users:
    def __init__(self):
        self.docs = []

    async def create_index(self, *args, **kwargs):
        return "unique_source_person"

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            matched = True
            for key, value in query.items():
                if isinstance(value, dict) and value.get("$type") == "string":
                    matched = isinstance(doc.get(key), str)
                elif doc.get(key) != value:
                    matched = False
                if not matched:
                    break
            if matched:
                return doc
        return None

    async def insert_one(self, document):
        self.docs.append(document)

    def find(self, query):
        rows = [doc for doc in self.docs if all(doc.get(key) == value for key, value in query.items())]
        return _Cursor(sorted(rows, key=lambda doc: doc.get("name") or ""))

    async def update_many(self, query, update):
        uid = query["$or"][0]["practitioners"]
        for doc in self.docs:
            if uid in doc.get("practitioners", []) or uid in doc.get("health_managers", []):
                doc["practitioners"] = [item for item in doc.get("practitioners", []) if item != uid]
                doc["health_managers"] = [item for item in doc.get("health_managers", []) if item != uid]

    async def update_one(self, query, update):
        for doc in self.docs:
            if doc["_id"] == query["_id"]:
                doc.update(update.get("$set") or {})
                for key, value in (update.get("$push") or {}).items():
                    doc.setdefault(key, []).append(value)


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
        self.users = Users()


class Source:
    source_origin = "https://forms.example.test"

    def __init__(self, pages):
        self.pages = pages

    async def list_people(self, project_id, *, limit=50, cursor=None):
        assert project_id == 4
        return self.pages[cursor]


def person(kind, number, name):
    prefix = "patient" if kind == "subject" else "user"
    return {
        "person_key": f"{prefix}:{number}", "kind": kind, "display_name": name, "project_id": 4,
        "source": {"system": "form-platform-11344", "environment": "production"},
        "subject_id": number if kind == "subject" else None,
        "center_id": 8, "subject_code": "S1" if kind == "subject" else None,
        "subject_status": "enrolled" if kind == "subject" else None,
        "source_patient_id": number if kind == "subject" else None,
        "source_user_id": None if kind == "subject" else number,
        "oidc_subject": None, "source_roles": [] if kind == "subject" else ["crc"],
    }


class ProjectPeopleImport(unittest.IsolatedAsyncioTestCase):
    async def test_subjects_become_patients_and_members_stay_unassigned(self):
        page = {"data": [person("subject", 15, "受试者甲"), person("member", 9, "协调员乙")],
                "page": {"limit": 100, "has_more": False, "next_cursor": None}}
        db = Database()
        actor = SimpleNamespace(id="admin-1", role="admin")
        result = await import_project_people(db, Source({None: page}), actor, 4)
        self.assertEqual((result["created"], result["existing"]), (2, 0))
        roles = {row["name"]: row["role"] for row in db.users.docs}
        self.assertEqual(roles, {"受试者甲": "patient", "协调员乙": "unassigned"})
        again = await import_project_people(db, Source({None: page}), actor, 4)
        self.assertEqual((again["created"], again["existing"], len(db.users.docs)), (0, 2, 2))

    async def test_role_change_clears_previous_patient_assignment(self):
        page = {"data": [person("member", 9, "协调员乙")],
                "page": {"limit": 100, "has_more": False, "next_cursor": None}}
        db = Database()
        actor = SimpleNamespace(id="admin-1")
        await import_project_people(db, Source({None: page}), actor, 4)
        member = db.users.docs[0]
        member["role"] = "doctor"
        patient = {"_id": ObjectId(), "role": "patient", "practitioners": [str(member["_id"])],
                   "health_managers": [], "source_person_key": None}
        db.users.docs.append(patient)
        updated = await assign_imported_role(db, actor, str(member["_id"]), "health_manager", "复核-1")
        self.assertEqual(updated["role"], "health_manager")
        self.assertEqual(patient["practitioners"], [])
        self.assertEqual(member["patients"], [])
        self.assertEqual(member["role_reviews"][0]["previous_role"], "doctor")

    async def test_care_assignment_stays_inside_one_project_and_current_roles(self):
        page = {"data": [person("subject", 15, "受试者甲"), person("member", 9, "协调员乙"), person("member", 10, "未定丙")],
                "page": {"limit": 100, "has_more": False, "next_cursor": None}}
        db = Database()
        actor = SimpleNamespace(id="admin-1")
        await import_project_people(db, Source({None: page}), actor, 4)
        patient = next(doc for doc in db.users.docs if doc["name"] == "受试者甲")
        doctor = next(doc for doc in db.users.docs if doc["name"] == "协调员乙")
        pending = next(doc for doc in db.users.docs if doc["name"] == "未定丙")
        doctor["role"] = "doctor"
        assigned = await set_imported_care(db, actor, str(patient["_id"]), str(doctor["_id"]),
                                           assigned=True, evidence_reference="责任-1")
        self.assertEqual(assigned["practitioners"], [str(doctor["_id"])])
        self.assertEqual(doctor["patients"], [str(patient["_id"])])
        removed = await set_imported_care(db, actor, str(patient["_id"]), str(doctor["_id"]),
                                          assigned=False, evidence_reference="责任-2")
        self.assertEqual(removed["practitioners"], [])
        self.assertEqual(doctor["patients"], [])
        with self.assertRaises(Exception) as pending_error:
            await set_imported_care(db, actor, str(patient["_id"]), str(pending["_id"]),
                                    assigned=True, evidence_reference="责任-3")
        self.assertEqual(pending_error.exception.detail["code"], "CARE_ROLE_MISMATCH")
