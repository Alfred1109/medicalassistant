"""T71 ICF 域测试：字典配置、评估 CRUD 授权、指标计算、预警触发、报告与导出。

沿用 test_clinical_workspace 的假集合风格；对象级授权走内核
ensure_patient_access（legacy 分支，fake Database 覆盖 users 与域状态集合）。
"""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from bson import ObjectId
from fastapi import HTTPException

from app.core.patient_access import PatientAccessError
from app.services import icf_service
from app.services.icf_service import (
    create_assessment, create_category, compute_patient_metrics,
    ensure_default_categories, evaluate_metrics_and_alert, export_report_html,
    export_report_json, generate_report, get_report, list_assessments,
    list_categories, list_metric_configs, list_reports, review_assessment,
    review_icf_report, update_assessment, update_category, update_metric_config)


def _match(doc, query):
    for key, value in query.items():
        current = doc
        for part in key.split("."):
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if isinstance(value, dict) and "$in" in value:
            if current not in value["$in"]:
                return False
        elif current != value:
            return False
    return True


class Collection:
    def __init__(self):
        self.docs = []

    async def insert_one(self, document, **kwargs):
        self.docs.append(document)
        return SimpleNamespace(inserted_id=document["_id"])

    async def insert_many(self, documents, **kwargs):
        for document in documents:
            self.docs.append(document)
        return SimpleNamespace(inserted_ids=[document["_id"] for document in documents])

    async def find_one(self, query, *args, sort=None, **kwargs):
        rows = [doc for doc in self.docs if _match(doc, query)]
        if sort:
            for key, direction in reversed(sort):
                rows = sorted(rows, key=lambda doc: doc.get(key) or datetime.min,
                              reverse=direction < 0)
        return rows[0] if rows else None

    async def update_one(self, query, update, **kwargs):
        for doc in self.docs:
            if _match(doc, query):
                doc.update(update.get("$set") or {})
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)

    def find(self, query, *args, **kwargs):
        rows = [doc for doc in self.docs if _match(doc, query)]
        return _Cursor(rows)

    def aggregate(self, pipeline, **kwargs):
        return _Cursor([])


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, key, direction=1):
        self.rows.sort(key=lambda doc: doc.get(key) or datetime.min, reverse=direction < 0)
        return self

    async def to_list(self, length=None):
        return list(self.rows if length is None else self.rows[:length])

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
        self.icf_categories = Collection()
        self.icf_assessments = Collection()
        self.icf_reports = Collection()
        self.icf_metric_configs = Collection()
        self.health_data_thresholds = Collection()
        self.health_data_alerts = Collection()

    def __getitem__(self, name):
        # HealthAlertService 经 db[collection_name] 访问集合：已存在的命名
        # 集合直接复用；未知集合（患者域状态等）返回空集合
        # （read_domain_mode 观察 legacy 缺省）。
        existing = self.__dict__.get(name)
        if isinstance(existing, Collection):
            return existing
        return self.__dict__.setdefault(f"_extra_{name}", Collection())

    async def create_index(self, *args, **kwargs):
        return None


def _clinical_pair(db):
    patient_id = ObjectId()
    doctor_id = ObjectId()
    db.users.docs.extend([
        {"_id": patient_id, "role": "patient", "name": "患者甲",
         "practitioners": [str(doctor_id)]},
        {"_id": doctor_id, "role": "doctor"},
    ])
    return patient_id, SimpleNamespace(id=doctor_id, role="doctor")


def _items(*triples):
    return [{"code": code, "qualifier": qualifier} for code, qualifier, _ in triples]


def _assess(db, doctor, patient_id, *, assessed_at, triples):
    items = [{"code": code, "qualifier": qualifier, "note": note,
              "qualifier_kind": "numeric" if isinstance(qualifier, int) else "text"}
             for code, qualifier, note in triples]
    document = {"_id": ObjectId(), "patient_id": str(patient_id),
                "assessor_id": str(doctor.id), "items": items,
                "source": "manual", "source_ref": "", "assessed_at": assessed_at,
                "note": "", "review_status": "reviewed", "review_note": "已核对",
                "reviewer_id": str(doctor.id),
                "reviewed_at": assessed_at,
                "mutation_version": 0, "content_revision": 1,
                "created_at": assessed_at, "updated_at": assessed_at, "metadata": {}}
    db.icf_assessments.docs.append(document)
    return document


def _fake_followups(db, patient_id):
    """随访数据源替身：绕开 FollowupService 依赖，只提供完成率所需 status。"""
    async def loader(_db, pid):
        return [{"status": row.get("status")} for row in db.followup_records.docs
                if row.get("patient_id") == str(pid)]
    return loader


class IcfDomainTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_dictionary_seeded_once_and_marked_pending_confirmation(self):
        db = Database()
        result = await list_categories(db, SimpleNamespace(id=ObjectId(), role="admin"))
        self.assertTrue(len(result["categories"]) >= 15)
        self.assertIn("待临床确认", result["note"])
        codes = [row["code"] for row in result["categories"]]
        self.assertIn("b130", codes)
        self.assertIn("d450", codes)
        self.assertEqual(result["categories"][0]["code"], sorted(codes)[0])
        # 幂等：再次调用不重复播种
        again = await list_categories(db, SimpleNamespace(id=ObjectId(), role="admin"))
        self.assertEqual(len(again["categories"]), len(result["categories"]))

    async def test_category_management_roles_and_validation(self):
        db = Database()
        actor = SimpleNamespace(id=ObjectId(), role="patient")
        with self.assertRaises(HTTPException) as caught:
            await create_category(db, actor, code="b999", name="自定义", domain="body")
        self.assertEqual(caught.exception.detail["code"], "ROLE_NOT_ALLOWED")
        doctor = SimpleNamespace(id=ObjectId(), role="doctor")
        created = await create_category(db, doctor, code="B900", name="康复自定义类目",
                                        domain="body")
        self.assertEqual(created["source"], "custom")
        with self.assertRaises(HTTPException) as caught:
            await create_category(db, doctor, code="b900", name="重复编码", domain="body")
        self.assertEqual(caught.exception.detail["code"], "ICF_CATEGORY_EXISTS")
        with self.assertRaises(HTTPException) as caught:
            await create_category(db, doctor, code="b901", name="错误域", domain="context")
        self.assertEqual(caught.exception.detail["code"], "INVALID_ICF_DOMAIN")
        disabled = await update_category(db, doctor, created["id"], enabled=False)
        self.assertFalse(disabled["enabled"])

    async def test_assessment_authorization_and_validation(self):
        db = Database()
        patient_id, doctor = _clinical_pair(db)
        stranger = SimpleNamespace(id=ObjectId(), role="doctor")
        with self.assertRaises(HTTPException) as caught:
            await create_assessment(db, stranger, str(patient_id),
                                    items=_items(("b130", 1, "")))
        self.assertEqual(caught.exception.detail["code"], "PATIENT_NOT_ASSIGNED")
        with self.assertRaises(HTTPException) as caught:
            await create_assessment(db, SimpleNamespace(id=patient_id, role="patient"),
                                    str(patient_id), items=_items(("b130", 1, "")))
        self.assertEqual(caught.exception.detail["code"], "ROLE_NOT_ALLOWED")
        with self.assertRaises(HTTPException) as caught:
            await create_assessment(db, doctor, str(patient_id),
                                    items=_items(("b999", 1, "")))
        self.assertEqual(caught.exception.detail["code"], "ICF_CODE_NOT_IN_DICTIONARY")
        with self.assertRaises(HTTPException) as caught:
            await create_assessment(db, doctor, str(patient_id),
                                    items=_items(("b130", 9, "")))
        self.assertEqual(caught.exception.detail["code"], "INVALID_ICF_QUALIFIER")
        assessment = await create_assessment(db, doctor, str(patient_id),
                                             items=[{"code": "b130", "qualifier": 2},
                                                    {"code": "b152", "qualifier": "尚可", "note": "患者自述"}],
                                             source="followup", source_ref="fu-1")
        self.assertEqual(assessment["source"], "followup")
        self.assertEqual(assessment["items"][1]["qualifier_kind"], "text")
        rows = await list_assessments(db, doctor, str(patient_id))
        self.assertEqual(len(rows["assessments"]), 1)

    async def test_assessment_update_cas_and_review_semantics(self):
        db = Database()
        patient_id, doctor = _clinical_pair(db)
        assessment = await create_assessment(db, doctor, str(patient_id),
                                             items=_items(("b130", 3, "")))
        with self.assertRaises(HTTPException) as caught:
            await update_assessment(db, doctor, assessment["id"],
                                    items=_items(("b130", 2, "")), note="",
                                    expected_version=assessment["mutation_version"] + 5)
        self.assertEqual(caught.exception.detail["code"], "ICF_ASSESSMENT_CONFLICT")
        reviewed = await review_assessment(db, doctor, assessment["id"], accepted=True,
                                           note="人工核对", expected_version=0)
        self.assertEqual(reviewed["review_status"], "reviewed")
        with self.assertRaises(HTTPException) as caught:
            await review_assessment(db, doctor, assessment["id"], accepted=True,
                                    note="", expected_version=1)
        self.assertEqual(caught.exception.detail["code"], "REVIEW_NOTE_REQUIRED")
        updated = await update_assessment(db, doctor, assessment["id"],
                                          items=_items(("b130", 1, "")), note="修订",
                                          expected_version=1)
        self.assertEqual(updated["review_status"], "pending")
        self.assertEqual(updated["mutation_version"], 2)

    async def test_metric_computation_is_config_driven(self):
        db = Database()
        patient_id, doctor = _clinical_pair(db)
        _assess(db, doctor, patient_id, assessed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                triples=(("b130", 3, ""), ("b152", 2, ""), ("d450", 2, ""), ("d540", 2, "")))
        _assess(db, doctor, patient_id, assessed_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
                triples=(("b130", 1, ""), ("b152", 3, ""), ("d450", 1, ""), ("d540", 2, "")))
        db.followup_records.docs.extend([
            {"_id": ObjectId(), "patient_id": str(patient_id), "status": "completed"},
            {"_id": ObjectId(), "patient_id": str(patient_id), "status": "scheduled"},
        ])
        with patch("app.services.icf_service._load_followups", _fake_followups(db, patient_id)):
            result = await compute_patient_metrics(db, doctor, str(patient_id))
        self.assertIn("待临床确认", result["note"])
        by_key = {row["metric_key"]: row for row in result["metrics"]}
        self.assertEqual(by_key["qualifier_improvement"]["state"], "alert")
        self.assertEqual(by_key["attainment_rate"]["state"], "alert")
        self.assertEqual(by_key["followup_completion_rate"]["state"], "alert")
        improvement_codes = {row["code"] for row in by_key["qualifier_improvement"]["detail"]
                             if row["state"] == "alert"}
        self.assertEqual(improvement_codes, {"b152", "d540"})
        # 配置驱动：放宽达标阈值后该项转 ok
        await list_metric_configs(db)
        await update_metric_config(db, doctor, "attainment_rate",
                                   params={"target_qualifier": 2, "min_rate": 0.4})
        with patch("app.services.icf_service._load_followups", _fake_followups(db, patient_id)):
            again = await compute_patient_metrics(db, doctor, str(patient_id))
        by_key = {row["metric_key"]: row for row in again["metrics"]}
        self.assertEqual(by_key["attainment_rate"]["state"], "ok")
        # 停用指标
        await update_metric_config(db, doctor, "followup_completion_rate", enabled=False)
        with patch("app.services.icf_service._load_followups", _fake_followups(db, patient_id)):
            disabled = await compute_patient_metrics(db, doctor, str(patient_id))
        by_key = {row["metric_key"]: row for row in disabled["metrics"]}
        self.assertEqual(by_key["followup_completion_rate"]["state"], "disabled")

    async def test_metric_alert_trigger_and_dedup(self):
        db = Database()
        patient_id, doctor = _clinical_pair(db)
        _assess(db, doctor, patient_id, assessed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                triples=(("b130", 3, ""),))
        _assess(db, doctor, patient_id, assessed_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
                triples=(("b130", 3, ""),))
        db.followup_records.docs.append(
            {"_id": ObjectId(), "patient_id": str(patient_id), "status": "scheduled"})
        with patch("app.services.icf_service._load_followups", _fake_followups(db, patient_id)):
            result = await evaluate_metrics_and_alert(db, doctor, str(patient_id))
        keys = sorted(row["metric_key"] for row in result["triggered"])
        self.assertEqual(keys, ["attainment_rate", "followup_completion_rate",
                                "qualifier_improvement"])
        self.assertEqual(len(db.health_data_alerts.docs), 3)
        alert = db.health_data_alerts.docs[0]
        self.assertEqual(alert["data_type"], "icf_metric")
        self.assertEqual(alert["status"], "active")
        self.assertIn("待临床确认", alert["metadata"]["note"])
        # 去重：已有未处理预警不再重复创建
        with patch("app.services.icf_service._load_followups", _fake_followups(db, patient_id)):
            second = await evaluate_metrics_and_alert(db, doctor, str(patient_id))
        self.assertEqual(len(second["triggered"]), 0)
        self.assertEqual(len(second["skipped"]), 3)
        self.assertEqual(len(db.health_data_alerts.docs), 3)

    async def test_report_generation_review_and_export_gating(self):
        db = Database()
        patient_id, doctor = _clinical_pair(db)
        draft = {"_id": ObjectId(), "patient_id": str(patient_id),
                 "assessor_id": str(doctor.id),
                 "items": [{"code": "b130", "qualifier": 3, "qualifier_kind": "numeric",
                            "note": "", "name": "精力与驱力功能", "domain": "body"}],
                 "source": "manual", "source_ref": "",
                 "assessed_at": datetime(2026, 3, 1, tzinfo=timezone.utc),
                 "note": "", "review_status": "pending", "review_note": "",
                 "reviewer_id": None, "reviewed_at": None,
                 "mutation_version": 0, "content_revision": 1,
                 "created_at": datetime(2026, 3, 1, tzinfo=timezone.utc),
                 "updated_at": datetime(2026, 3, 1, tzinfo=timezone.utc), "metadata": {}}
        db.icf_assessments.docs.append(draft)
        with self.assertRaises(HTTPException) as caught:
            await generate_report(db, doctor, str(patient_id), str(draft["_id"]))
        self.assertEqual(caught.exception.detail["code"], "ICF_ASSESSMENT_NOT_REVIEWED")
        draft.update(review_status="reviewed", reviewer_id=str(doctor.id),
                     reviewed_at=draft["assessed_at"], review_note="已核对")
        with patch("app.services.icf_service._load_followups", _fake_followups(db, patient_id)):
            report = await generate_report(db, doctor, str(patient_id), str(draft["_id"]))
        self.assertEqual(report["payload"]["patient"]["name"], "患者甲")
        self.assertIn("body", report["payload"]["domains"])
        self.assertIn("待临床确认", report["payload"]["disclaimer"])
        with self.assertRaises(HTTPException) as caught:
            export_report_json({"_id": ObjectId(report["id"]), "review_status": "pending",
                                "reviewed_snapshot": None, "payload": report["payload"]})
        self.assertEqual(caught.exception.detail["code"], "ICF_REPORT_NOT_REVIEWED")
        with self.assertRaises(HTTPException) as caught:
            await review_icf_report(db, doctor, report["id"], accepted=True, note="",
                                    expected_version=0)
        self.assertEqual(caught.exception.detail["code"], "REVIEW_NOTE_REQUIRED")
        reviewed = await review_icf_report(db, doctor, report["id"], accepted=True,
                                           note="正式报告核对通过", expected_version=0)
        self.assertEqual(reviewed["review_status"], "reviewed")
        self.assertEqual(reviewed["review_history"][0]["action"], "review")
        row = db.icf_reports.docs[0]
        export = export_report_json(row)
        self.assertEqual(export["payload"]["patient"]["name"], "患者甲")
        html = export_report_html(row)
        self.assertIn("患者甲", html)
        self.assertIn("身体功能", html)
        self.assertIn("待临床确认", html)
        # 患者本人可读已审核报告；他人被拒
        patient_view = await get_report(db, SimpleNamespace(id=patient_id, role="patient"),
                                        report["id"])
        self.assertEqual(patient_view["id"], report["id"])
        with self.assertRaises(PatientAccessError):
            await get_report(db, SimpleNamespace(id=ObjectId(), role="patient"),
                             report["id"])
        reports = await list_reports(db, doctor, str(patient_id))
        self.assertEqual(len(reports["reports"]), 1)

    async def test_metric_config_seeding_defaults(self):
        db = Database()
        result = await list_metric_configs(db)
        keys = {row["metric_key"] for row in result["metrics"]}
        self.assertEqual(keys, {"qualifier_improvement", "attainment_rate",
                                "followup_completion_rate"})
        self.assertTrue(all("待临床确认" in row["note"] for row in result["metrics"]))

    async def test_default_seed_function_is_idempotent(self):
        db = Database()
        first = await ensure_default_categories(db)
        self.assertTrue(first["seeded"])
        second = await ensure_default_categories(db)
        self.assertFalse(second["seeded"])


if __name__ == "__main__":
    unittest.main()
