"""Portrait, education, reports and voice use stored records and do not invent results."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from bson import ObjectId
from fastapi import HTTPException

from unittest.mock import AsyncMock, patch

from app.clinical.workspace import (
    acknowledge_material, add_finding, add_report, add_voice, assign_material, create_indicator, create_material,
    evaluate_indicators, extract_measurements, guide_material, list_shares, portrait, recorded_plan_sources,
    request_share, retire_indicator, review_report, withdraw_share,
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
        self.clinical_indicator_rules = Collection()


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

    async def test_share_access_follows_the_source_decision(self):
        db = Database()
        patient_id = ObjectId()
        doctor_id = ObjectId()
        db.users.docs.extend([
            {"_id": patient_id, "role": "patient", "source_project_id": 4, "source_center_id": 2,
             "source_subject_id": 8, "practitioners": [str(doctor_id)]},
            {"_id": doctor_id, "role": "doctor", "source_project_id": 4},
        ])
        doctor = SimpleNamespace(id=doctor_id, role="doctor")
        state = {"status": "pending"}

        async def contact(action, payload):
            if action == "create":
                self.assertEqual(payload["subject_id"], 8)
                self.assertNotIn("access_granted", payload)
                return {"id": 15, "status": "pending", "access_granted": False}
            if action == "read":
                return {"id": 15, "status": state["status"], "access_granted": state["status"] == "approved"}
            state["status"] = "withdrawn"
            return {"id": 15, "status": "withdrawn", "access_granted": False}

        with patch("app.clinical.workspace._form_platform_ready", return_value=True), \
                patch("app.clinical.workspace._contact_source", new=contact):
            created = await request_share(db, doctor, str(patient_id), 9, "会诊需要看随访")
            self.assertFalse(created["access_granted"])
            self.assertEqual(created["remote_share_id"], 15)
            state["status"] = "approved"
            listed = await list_shares(db, doctor, str(patient_id))
            self.assertEqual(listed[0]["status"], "source_approved")
            self.assertTrue(listed[0]["access_granted"])

    def test_measurements_come_only_from_written_numbers(self):
        found = extract_measurements("收缩压 120 mmHg\n第 1 页\n空腹血糖：5.6 mmol/L")
        self.assertEqual([(item["label"], item["value"], item["unit"]) for item in found],
                         [("收缩压", "120", "mmHg"), ("空腹血糖", "5.6", "mmol/L")])

    async def test_report_excerpt_keeps_measurements_unconfirmed(self):
        db, doctor, patient_id = self._pair()
        with patch("app.clinical.workspace._report_excerpt", new=AsyncMock(return_value=("收缩压 120 mmHg", "PDF文字层，待人工审核"))):
            report = await add_report(db, doctor, str(patient_id), filename="a.pdf", content_type="application/pdf",
                                      content=b"%PDF", report_date="2026-11-10", stated_patient_id=str(patient_id))
        self.assertEqual(report["parse_status"], "model_suggested")
        self.assertEqual(report["extracted_values"][0]["value"], "120")
        self.assertEqual(report["extracted_values"][0]["source"], "报告原文，待人工审核")

    async def test_browser_transcript_stays_unconfirmed_until_saved(self):
        db, doctor, patient_id = self._pair()
        patient = SimpleNamespace(id=patient_id, role="patient")
        voice = await add_voice(db, patient, str(patient_id), content_type="audio/webm", content=b"abc",
                                consent=True, browser_transcript="走路有点喘")
        self.assertEqual(voice["transcription_status"], "browser_suggested")
        self.assertEqual(voice["transcript"], "走路有点喘")

    async def test_indicator_dictionary_compares_only_reviewed_findings(self):
        db, doctor, patient_id = self._pair()
        rule = await create_indicator(db, doctor, label="收缩压", source_label="收缩压", unit="mmHg",
                                     low=90, high=140, icf_code="b420")
        report = await add_report(db, doctor, str(patient_id), filename="a.pdf", content_type="application/pdf",
                                  content=b"%PDF", report_date="2026-11-10", stated_patient_id=str(patient_id))
        await review_report(db, doctor, report["id"], accepted=True, note="已核对原件")
        await add_finding(db, doctor, report["id"], "收缩压", "150", "mmHg")
        result = await evaluate_indicators(db, doctor, str(patient_id))
        self.assertEqual(result["indicators"][0]["state"], "outside")
        self.assertEqual(result["indicators"][0]["icf_code"], "b420")
        self.assertIsNone(result["indicators"][0].get("score"))
        self.assertIn("不计算 ICF 评分", result["message"])
        await retire_indicator(db, doctor, rule["id"])
        empty = await evaluate_indicators(db, doctor, str(patient_id))
        self.assertFalse(empty["configured"])

    async def test_recorded_plan_leaves_missing_topics_blank(self):
        db, doctor, patient_id = self._pair()
        db.users.docs[0]["medical_info"] = {"diagnosis": "慢性肾病"}
        db.users.docs[0]["lifestyle"] = {"exercise": "每日步行 20 分钟"}
        suggestion = await recorded_plan_sources(db, doctor, str(patient_id))
        self.assertFalse(suggestion["published"])
        self.assertEqual(suggestion["missing"], ["基因"])
        self.assertEqual(suggestion["items"], [{
            "intervention_type": "exercise", "name": "已记录的运动", "description": "每日步行 20 分钟",
            "source": "患者档案中已保存的文字"}])
        self.assertIn("慢性肾病", suggestion["description"])
        self.assertIn("每日步行 20 分钟", suggestion["description"])
        self.assertNotIn("基因记录", suggestion["description"])

    def _pair(self):
        db = Database()
        patient_id = ObjectId()
        doctor_id = ObjectId()
        db.users.docs.extend([
            {"_id": patient_id, "role": "patient", "name": "甲", "practitioners": [str(doctor_id)]},
            {"_id": doctor_id, "role": "doctor"},
        ])
        return db, SimpleNamespace(id=doctor_id, role="doctor"), patient_id


if __name__ == "__main__":
    unittest.main()
