"""Portrait, education, reports and voice use stored records and do not invent results."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from bson import ObjectId
from fastapi import HTTPException

from app.clinical.workspace import (
    acknowledge_material, add_finding, add_report, add_voice, assign_material, create_material, guide_material,
    portrait, request_share, review_report, withdraw_share,
)
from app.integrations.forms.sync_runs import list_runs, load_failed_import, record_run, summarize_runs


class Collection:
    def __init__(self):
        self.docs = []

    async def insert_one(self, document):
        self.docs.append(document)

    async def find_one(self, query):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return doc
        return None

    async def update_one(self, query, update):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(update.get("$set") or {})

    def find(self, query):
        rows = [doc for doc in self.docs if all(doc.get(key) == value for key, value in query.items())]
        return _Cursor(rows)


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, key, direction=1):
        self.rows.sort(key=lambda doc: doc.get(key) or "", reverse=direction < 0)
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
        self.users = Collection()
        self.followup_records = Collection()
        self.rehab_plans = Collection()
        self.education_materials = Collection()
        self.education_assignments = Collection()
        self.clinical_reports = Collection()
        self.voice_notes = Collection()
        self.voice_events = Collection()
        self.share_requests = Collection()
        self.integration_runs = Collection()


class ClinicalWorkspaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_portrait_keeps_missing_time_and_void_plans_visible(self):
        db = Database()
        patient_id = ObjectId()
        doctor_id = ObjectId()
        db.users.docs.append({"_id": patient_id, "role": "patient", "name": "甲", "source_project_id": 7,
                              "practitioners": [str(doctor_id)]})
        db.users.docs.append({"_id": doctor_id, "role": "doctor", "source_project_id": 7})
        db.followup_records.docs.append({"_id": ObjectId(), "patient_id": str(patient_id), "status": "completed",
                                         "scheduled_date": None, "actual_date": None})
        db.followup_records.docs.append({"_id": ObjectId(), "patient_id": str(patient_id), "status": "scheduled",
                                         "scheduled_date": datetime(2020, 1, 1, tzinfo=timezone.utc), "actual_date": None})
        db.followup_records.docs.append({"_id": ObjectId(), "patient_id": str(patient_id), "status": "canceled",
                                         "scheduled_date": datetime.now(timezone.utc), "actual_date": None})
        db.rehab_plans.docs.append({"_id": ObjectId(), "patient_id": str(patient_id), "status": "archived",
                                    "published_version_id": "old"})
        result = await portrait(db, SimpleNamespace(id=doctor_id, role="doctor"), str(patient_id))
        self.assertEqual(result["followups"][0]["actual_time"], "missing")
        self.assertEqual(result["missing_followup_time"], 1)
        self.assertEqual(result["followups"][1]["display_state"], "overdue")
        self.assertEqual(result["overdue_followups"], 1)
        self.assertTrue(result["followups"][2]["void"])
        self.assertTrue(result["plans"][0]["void"])
        self.assertFalse(result["plans"][0]["published"])

    async def test_different_source_project_is_rejected(self):
        db = Database()
        patient_id = ObjectId()
        doctor_id = ObjectId()
        db.users.docs.extend([
            {"_id": patient_id, "role": "patient", "source_project_id": 1, "practitioners": [str(doctor_id)]},
            {"_id": doctor_id, "role": "doctor", "source_project_id": 2},
        ])
        with self.assertRaises(HTTPException) as caught:
            await portrait(db, SimpleNamespace(id=doctor_id, role="doctor"), str(patient_id))
        self.assertEqual(caught.exception.detail["code"], "DIFFERENT_PROJECT")

    async def test_education_feedback_and_unparsed_report_and_voice(self):
        db = Database()
        patient_id = ObjectId()
        doctor_id = ObjectId()
        db.users.docs.extend([
            {"_id": patient_id, "role": "patient", "practitioners": [str(doctor_id)]},
            {"_id": doctor_id, "role": "doctor"},
        ])
        doctor = SimpleNamespace(id=doctor_id, role="doctor")
        patient = SimpleNamespace(id=patient_id, role="patient")
        material = await create_material(db, doctor, "今日步行说明", "按已发布方案中的步行时间执行。")
        assignment = await assign_material(db, doctor, material["id"], str(patient_id))
        read = await acknowledge_material(db, patient, assignment["id"], "已阅读")
        guidance = await guide_material(db, doctor, assignment["id"], "按原文执行，不要自行加量。")
        self.assertEqual(read["status"], "read")
        self.assertEqual(guidance["guidance"], "按原文执行，不要自行加量。")
        with self.assertRaises(HTTPException):
            await add_report(db, doctor, str(patient_id), filename="a.pdf", content_type="application/pdf",
                             content=b"%PDF", report_date="2026-11-10", stated_patient_id="other")
        report = await add_report(db, doctor, str(patient_id), filename="a.pdf", content_type="application/pdf",
                                  content=b"%PDF", report_date="2026-11-10", stated_patient_id=str(patient_id))
        self.assertEqual(report["parse_status"], "not_parsed")
        self.assertEqual(report["extracted_values"], [])
        reviewed = await review_report(db, doctor, report["id"], accepted=True, note="人工核对原件，未自动提取指标。")
        finding = await add_finding(db, doctor, report["id"], "收缩压", "120", "mmHg")
        self.assertEqual(reviewed["review_status"], "reviewed")
        self.assertEqual(finding["parse_status"], "not_parsed")
        self.assertEqual(finding["findings"][0]["source"], "人工阅读原件")
        voice = await add_voice(db, patient, str(patient_id), content_type="audio/webm;codecs=opus", content=b"abc", consent=True)
        self.assertIsNone(voice["transcript"])
        self.assertEqual(voice["transcription_status"], "not_transcribed")

    async def test_failed_import_can_be_selected_for_retry(self):
        db = Database()
        started = datetime.now(timezone.utc)
        failed = await record_run(db, kind="people_import", project_id=3, actor_id="admin", status="failed",
                                  started_at=started, error_code="SOURCE_ROSTER_TOO_LARGE")
        done = await record_run(db, kind="people_import", project_id=3, actor_id="admin", status="succeeded",
                                started_at=started, created=1, existing=0)
        self.assertEqual(len(await list_runs(db)), 2)
        summary = await summarize_runs(db)
        self.assertEqual(summary[0]["attempts"], 2)
        self.assertIsNotNone(summary[0]["last_failure"])
        self.assertEqual((await load_failed_import(db, failed["id"]))["project_id"], 3)
        with self.assertRaises(HTTPException):
            await load_failed_import(db, done["id"])

    async def test_share_request_does_not_grant_access(self):
        db = Database()
        patient_id = ObjectId()
        doctor_id = ObjectId()
        db.users.docs.extend([
            {"_id": patient_id, "role": "patient", "source_project_id": 4, "practitioners": [str(doctor_id)]},
            {"_id": doctor_id, "role": "doctor", "source_project_id": 4},
        ])
        doctor = SimpleNamespace(id=doctor_id, role="doctor")
        created = await request_share(db, doctor, str(patient_id), 9, "会诊需要看随访")
        self.assertFalse(created["access_granted"])
        self.assertEqual(created["status"], "pending_source_authorization")
        withdrawn = await withdraw_share(db, doctor, created["id"])
        self.assertEqual(withdrawn["status"], "withdrawn")
        self.assertFalse(withdrawn["access_granted"])


if __name__ == "__main__":
    unittest.main()
