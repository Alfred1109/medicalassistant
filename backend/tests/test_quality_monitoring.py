"""Process facts against an explicitly isolated local MongoDB."""
import csv
import io
import os
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from bson import ObjectId
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient
from unittest.mock import AsyncMock
from unittest.mock import patch

from app.api.routers.quality_monitoring_router import router, service
from app.core.auth import get_current_active_user
from app.core.exceptions import AppBaseException
from app.services.quality_monitoring_service import QualityMonitoringService, csv_safe
from app.services.followup_service import FollowupService, followup_from_mongo, map_followup_record_to_response
from app.models.health_record import FollowUpRecord

URI = os.environ.get("REHAB_TEST_QUALITY_MONITORING_MONGO_URI")


def application(actor, svc):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_current_active_user] = lambda: actor
    app.dependency_overrides[service] = lambda: svc

    @app.exception_handler(AppBaseException)
    async def domain_error(request, exc):
        return JSONResponse(status_code=exc.status_code, content={"code": exc.error_code})
    return app


class QualityInputTests(unittest.TestCase):
    def test_spreadsheet_formula_cells_are_escaped(self):
        for value in ("=CMD()", "+1", "-1", "@SUM(1)", "  =1", "\tvalue", "\rvalue", "\nvalue"):
            self.assertTrue(csv_safe(value).startswith("'"))
        self.assertEqual(csv_safe("普通文字"), "普通文字")

    def test_ambiguous_and_inverted_dates_are_rejected(self):
        for start, end in ((datetime(2026, 11, 9), None),
                           (datetime(2026, 11, 10, tzinfo=timezone.utc), datetime(2026, 11, 9, tzinfo=timezone.utc))):
            with self.assertRaises(AppBaseException):
                QualityMonitoringService.dates(start, end)


@unittest.skipUnless(URI, "set REHAB_TEST_QUALITY_MONITORING_MONGO_URI to an isolated local Mongo")
class QualityMongoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue(URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")))
        self.client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.client["rehab_quality_monitoring_test_" + uuid4().hex]
        self.doctor, self.manager, self.other = map(str, (ObjectId(), ObjectId(), ObjectId()))
        self.admin = str(ObjectId())
        self.patient, self.second, self.outside = map(str, (ObjectId(), ObjectId(), ObjectId()))
        await self.db.users.insert_many([
            {"_id": ObjectId(self.doctor), "role": "doctor", "is_active": True},
            {"_id": ObjectId(self.manager), "role": "health_manager", "is_active": True},
            {"_id": ObjectId(self.other), "role": "doctor", "is_active": True},
            {"_id": ObjectId(self.admin), "role": "admin", "is_active": True},
            {"_id": ObjectId(self.patient), "role": "patient", "is_active": True, "practitioners": [self.doctor], "health_managers": [self.manager]},
            {"_id": ObjectId(self.second), "role": "patient", "is_active": True, "practitioners": [ObjectId(self.doctor)]},
            {"_id": ObjectId(self.outside), "role": "patient", "is_active": True, "practitioners": [self.other]},
        ])
        self.actor = SimpleNamespace(id=self.doctor, role="doctor")
        self.svc = QualityMonitoringService(self.db)
        self.http = AsyncClient(transport=ASGITransport(app=application(self.actor, self.svc)), base_url="http://test")
        self.when = datetime(2026, 11, 9, 8)

    async def asyncTearDown(self):
        await self.http.aclose()
        await self.client.drop_database(self.db.name)
        self.client.close()

    async def followup(self, **values):
        row = {"_id": ObjectId(), "patient_id": self.patient, "status": "scheduled", "scheduled_date": self.when, **values}
        await self.db.followup_records.insert_one(row)
        return row

    async def plan(self, **values):
        row = {"_id": ObjectId(), "patient_id": self.patient, "status": "active", "created_at": self.when, **values}
        await self.db.rehab_plans.insert_one(row)
        return row

    async def publication_version(self, plan, **values):
        row = {"_id": ObjectId(), "plan_id": str(plan["_id"]), "patient_id": plan["patient_id"],
            "workflow": "patient_publication", "status": "published",
            "snapshot": {"name": "经核实方案", "description": "医护明确填写", "goal": "记录目标", "start_date": self.when},
            "items_snapshot": [{"item_id": str(ObjectId()), "intervention_type": "exercise", "name": "医护填写运动"}],
            "published_at": self.when, "published_by": self.doctor, "confirmation_note": "逐项核实", "publication_revision": 1,
            **values}
        await self.db.rehab_plan_versions.insert_one(row)
        return row

    async def get(self, path="overview", **params):
        return await self.http.get("/api/quality-monitoring/" + path, params=params)

    async def test_scope_applies_before_counts_and_pages_for_each_medical_role(self):
        await self.followup(status="in_review")
        await self.followup(patient_id=self.second)
        await self.followup(patient_id=self.outside)
        await self.plan()
        await self.plan(patient_id=self.outside)
        overview = (await self.get()).json()
        self.assertEqual(overview["followups"]["selected_total"], 2)
        self.assertEqual(overview["followups"]["in_review_count"], 1)
        self.assertEqual(overview["plans"]["selected_total"], 1)
        self.assertEqual(overview["scope_kind"], "assigned_patients")
        self.assertEqual((await self.get(patient_id=self.patient)).json()["scope_kind"], "selected_patient")
        self.assertEqual((await self.get(patient_id=self.outside)).status_code, 403)
        self.actor.id, self.actor.role = self.manager, "health_manager"
        self.assertEqual((await self.get()).json()["followups"]["selected_total"], 1)
        self.assertEqual((await self.get(patient_id=self.second)).status_code, 403)
        self.actor.id = str(ObjectId())
        await self.db.users.insert_one({"_id": ObjectId(self.actor.id), "role": "health_manager", "is_active": True})
        self.assertEqual((await self.get()).json()["followups"]["selected_total"], 0)

    async def test_unknown_missing_invalid_statuses_and_dates_are_counted_honestly(self):
        await self.followup(status="new_state")
        await self.followup(status=None, scheduled_date=None)
        await self.followup(status={"bad": True}, scheduled_date="2026-11-09")
        await self.db.followup_records.insert_one({"_id": ObjectId(), "patient_id": self.patient})
        await self.followup(deleted=True)
        data = (await self.get()).json()["followups"]
        self.assertEqual(data["selected_total"], 4)
        self.assertEqual(data["scope_total"], 4)
        self.assertEqual(data["missing_date_count"], 2)
        self.assertEqual(data["invalid_date_count"], 1)
        statuses = {row["status"]: row["count"] for row in data["by_status"]}
        self.assertEqual((statuses["__unknown__"], statuses["__missing__"], statuses["__invalid__"]), (1, 2, 1))

    async def test_half_open_dates_and_current_plan_creation_cohort(self):
        first = await self.followup(status="in_review")
        await self.followup(scheduled_date=self.when + timedelta(days=1))
        await self.followup(scheduled_date=self.when - timedelta(milliseconds=1))
        await self.followup(scheduled_date=None)
        await self.plan()
        await self.plan(created_at=self.when + timedelta(days=1))
        params = {"start_date": "2026-11-09T16:00:00+08:00", "end_date": "2026-11-10T16:00:00+08:00"}
        overview = (await self.get(**params)).json()
        self.assertEqual(overview["followups"]["selected_total"], 1)
        self.assertEqual(overview["followups"]["scope_total"], 4)
        self.assertEqual(overview["followups"]["missing_date_count"], 1)
        self.assertEqual(overview["plans"]["selected_total"], 1)
        detail = (await self.get("followups", **params)).json()
        self.assertEqual([row["source_id"] for row in detail["items"]], [str(first["_id"])])
        self.assertEqual(detail["items"][0]["date"], "2026-11-09T08:00:00Z")

    async def test_real_pages_over_100_are_stable_and_do_not_leak_content(self):
        rows = [await self.followup(notes="private clinical notes") for _ in range(125)]
        await self.followup(patient_id=self.outside)
        first, second = (await self.get("followups", limit=100)).json(), (await self.get("followups", skip=100, limit=100)).json()
        self.assertEqual((first["total"], second["total"]), (125, 125))
        ids = [row["source_id"] for row in first["items"] + second["items"]]
        self.assertEqual(ids, sorted((str(row["_id"]) for row in rows), reverse=True))
        self.assertNotIn("notes", first["items"][0])
        self.assertEqual(first["items"][0]["source_type"], "followup")
        self.assertTrue(first["items"][0]["issue_eligible"])

    async def test_issue_eligibility_is_separate_from_reference_existence(self):
        self.actor.id, self.actor.role = self.admin, "admin"
        active = await self.followup()
        inactive_id, unknown_active_id, ambiguous_id = map(str, (ObjectId(), ObjectId(), ObjectId()))
        legacy_id = "legacy-clinical-patient"
        await self.db.users.insert_many([
            {"_id": ObjectId(inactive_id), "role": "patient", "is_active": False},
            {"_id": ObjectId(unknown_active_id), "role": "patient"},
            {"_id": legacy_id, "role": "patient", "is_active": True},
            {"_id": ObjectId(ambiguous_id), "role": "patient", "is_active": True},
            {"_id": ambiguous_id, "role": "patient", "is_active": True},
        ])
        inactive = await self.followup(patient_id=inactive_id)
        unknown_active = await self.followup(patient_id=unknown_active_id)
        legacy = await self.followup(patient_id=legacy_id)
        ambiguous = await self.followup(patient_id=ambiguous_id)
        uppercase = await self.followup(patient_id=self.patient.upper())
        string_source = await self.followup(_id=str(ObjectId()))
        response = await self.get("followups", limit=100)
        self.assertEqual(response.status_code, 200, response.text)
        items = {row["source_id"]: row for row in response.json()["items"]}
        self.assertTrue(items[str(active["_id"])]["issue_eligible"])
        for record in (inactive, unknown_active, legacy, uppercase, string_source):
            item = items[str(record["_id"])]
            self.assertEqual(item["patient_reference_state"], "valid")
            self.assertFalse(item["issue_eligible"])
        self.assertEqual(items[str(ambiguous["_id"])]["patient_reference_state"], "ambiguous")
        self.assertFalse(items[str(ambiguous["_id"])]["issue_eligible"])

    async def test_publication_facts_validate_pointer_without_leaking_drafts(self):
        valid = await self.plan(metadata={"private": "do not leak"})
        version = ObjectId()
        await self.publication_version(valid, _id=version)
        await self.db.rehab_plans.update_one({"_id": valid["_id"]}, {"$set": {"published_version_id": str(version)}})
        await self.plan()
        withdrawn = await self.plan(has_publication_history=True, published_version_id=None)
        await self.publication_version(withdrawn, status="withdrawn")
        await self.plan(has_publication_history=True, published_version_id=None)
        await self.plan(status="archived", has_publication_history=True)
        await self.plan(published_version_id="invalid")
        await self.plan(published_version_id=str(ObjectId()))
        foreign = ObjectId()
        await self.publication_version(valid, _id=foreign, patient_id=self.outside)
        await self.plan(published_version_id=str(foreign))
        summary = (await self.get()).json()["plans"]
        counts = {row["state"]: row["count"] for row in summary["publication_states"]}
        self.assertEqual(counts, {"published": 1, "unpublished": 1, "withdrawn": 1, "stopped": 1, "invalid_reference": 4})
        detail = (await self.get("plans")).json()
        self.assertEqual(detail["total"], 8)
        self.assertNotIn("metadata", str(detail))
        self.assertNotIn("snapshot", str(detail))

    async def test_required_publication_structure_and_pointer_type_fail_closed(self):
        valid = await self.plan()
        version = await self.publication_version(valid)
        await self.db.rehab_plans.update_one({"_id": valid["_id"]}, {"$set": {"published_version_id": str(version["_id"])}})
        changes = [
            {"snapshot": None}, {"snapshot": {}},
            {"snapshot": {"name": "n", "description": "d", "goal": "g", "start_date": "2026-11-09"}},
            {"items_snapshot": None}, {"items_snapshot": []},
            {"items_snapshot": [{"item_id": "bad", "intervention_type": "exercise", "name": "name"}]},
            {"published_at": None}, {"published_by": None}, {"confirmation_note": None}, {"publication_revision": 0},
        ]
        for change in changes:
            plan = await self.plan()
            saved = await self.publication_version(plan, **change)
            await self.db.rehab_plans.update_one({"_id": plan["_id"]}, {"$set": {"published_version_id": str(saved["_id"])}})
        wrong_pointer = await self.plan()
        saved = await self.publication_version(wrong_pointer)
        await self.db.rehab_plans.update_one({"_id": wrong_pointer["_id"]}, {"$set": {"published_version_id": saved["_id"]}})
        result = (await self.get()).json()
        self.assertEqual(result["publication_validation"], "reference_and_required_structure")
        counts = {item["state"]: item["count"] for item in result["plans"]["publication_states"]}
        self.assertEqual(counts["published"], 1)
        self.assertEqual(counts["invalid_reference"], len(changes) + 1)

    async def test_medical_and_selected_admin_scope_refuse_ambiguous_or_inactive_identity(self):
        await self.followup()
        await self.db.users.insert_one({"_id": self.patient, "role": "patient", "is_active": True,
            "practitioners": [self.other]})
        for path in ("overview", "followups", "plans", "report.csv"):
            response = await self.get(path)
            self.assertEqual(response.status_code, 503, (path, response.text))
            self.assertEqual(response.json()["code"], "QUALITY_PATIENT_SCOPE_UNVERIFIED")
        self.actor.id, self.actor.role = self.admin, "admin"
        self.assertEqual((await self.get()).json()["followups"]["unresolved_patient_count"], 1)
        self.assertEqual((await self.get(patient_id=self.patient)).status_code, 503)
        await self.db.users.delete_one({"_id": self.patient})
        await self.db.users.update_one({"_id": ObjectId(self.patient)}, {"$set": {"is_active": False}})
        self.assertEqual((await self.get(patient_id=self.patient)).status_code, 503)
        self.actor.id, self.actor.role = self.doctor, "doctor"
        await self.followup(patient_id=self.second)
        self.assertEqual((await self.get()).json()["followups"]["selected_total"], 1)
        self.assertEqual((await self.get(patient_id=self.patient)).status_code, 403)
        await self.db.users.delete_one({"_id": ObjectId(self.patient)})
        self.assertEqual((await self.get()).json()["followups"]["selected_total"], 1)
        # Removal after scope collection must be excluded, not keep a stale ID.
        with patch("app.services.quality_monitoring_service.followup_patient_scope", new=AsyncMock(return_value=[self.patient])):
            self.assertEqual((await self.get()).json()["followups"]["selected_total"], 0)
        # Assignment revocation after scope collection is excluded too.
        await self.db.users.update_one({"_id": ObjectId(self.second)}, {"$set": {"practitioners": []}})
        with patch("app.services.quality_monitoring_service.followup_patient_scope", new=AsyncMock(return_value=[self.second])):
            self.assertEqual((await self.get()).json()["followups"]["selected_total"], 0)
            self.assertEqual((await self.get(patient_id=self.second)).status_code, 403)

    async def test_same_value_string_source_and_objectid_source_are_not_same_navigation_target(self):
        identifier = ObjectId()
        await self.followup(_id=identifier)
        await self.followup(_id=str(identifier))
        await self.followup(_id={"legacy": "compound"})
        response = await self.get("followups")
        self.assertEqual(response.status_code, 200, response.text)
        rows = [item for item in response.json()["items"] if item["source_id"] == str(identifier)]
        self.assertEqual(len(rows), 2)
        self.assertEqual({item["source_reference_state"] for item in rows}, {"valid", "unaddressable"})
        self.assertEqual({(item["source_reference_state"], item["issue_eligible"]) for item in rows},
            {("valid", True), ("unaddressable", False)})
        invalid = next(item for item in response.json()["items"] if item["source_id"] == "[unaddressable]")
        self.assertEqual(invalid["source_reference_state"], "unaddressable")
        self.assertFalse(invalid["issue_eligible"])

    async def test_admin_orphan_scope_is_explicit_and_medical_scope_stays_empty(self):
        await self.followup(patient_id=None)
        await self.followup(patient_id=str(ObjectId()))
        await self.followup(patient_id=123)
        await self.db.rehab_plans.insert_one({"_id": ObjectId(), "status": "active"})
        self.assertEqual((await self.get()).json()["followups"]["scope_total"], 0)
        self.actor.id, self.actor.role = self.admin, "admin"
        data = (await self.get()).json()
        self.assertEqual(data["scope_kind"], "all_source_records")
        self.assertEqual(data["read_consistency"], "independent_live_reads")
        self.assertEqual(data["followups"]["unresolved_patient_count"], 3)
        self.assertEqual(data["plans"]["unresolved_patient_count"], 1)
        detail = (await self.get("followups")).json()
        self.assertEqual({row["patient_reference_state"] for row in detail["items"]}, {"missing", "invalid", "not_found"})

    async def test_csv_matches_overview_and_describes_scope_and_time_semantics(self):
        await self.followup(status="in_review")
        await self.plan()
        response = await self.get("report.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers["content-type"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(rows[0], ["section", "metric", "value", "context"])
        values = {(row[0], row[1]): row[2] for row in rows[1:]}
        self.assertEqual(values[("followups", "in_review_count")], "1")
        self.assertEqual(values[("plans", "selected_total")], "1")
        self.assertEqual(values[("scope", "read_consistency")], "independent_live_reads")
        self.assertIn("不是窗口内发布次数", response.text)
        self.assertIn("不保证全部嵌套内容通过患者DTO校验", response.text)

    async def test_canonical_domain_and_nonmedical_roles_fail_closed(self):
        for role in ("patient", "researcher", "organization_admin"):
            self.actor.role = role
            self.assertEqual((await self.get()).status_code, 403)
        self.actor.role = "doctor"
        await self.db.patient_domain_state.insert_one({"_id": "clinical-patients-v1", "mode": "canonical"})
        response = await self.get()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "QUALITY_PATIENT_DOMAIN_UNSUPPORTED")

    async def test_actor_identity_must_be_unique_active_and_role_consistent_for_all_reads(self):
        await self.followup()
        await self.db.users.insert_one({"_id": self.doctor, "role": "doctor", "is_active": True})
        for path in ("overview", "followups", "plans", "report.csv"):
            result = await self.get(path)
            self.assertEqual(result.status_code, 403)
            self.assertEqual(result.json()["code"], "QUALITY_ACCOUNT_UNAVAILABLE")
        await self.db.users.delete_one({"_id": self.doctor})
        self.assertEqual((await self.get()).status_code, 200)
        self.actor.id, self.actor.role = self.admin, "admin"
        await self.db.users.insert_one({"_id": self.admin, "role": "doctor", "is_active": True})
        self.assertEqual((await self.get()).status_code, 403)
        await self.db.users.delete_one({"_id": self.admin})
        await self.db.users.update_one({"_id": ObjectId(self.admin)}, {"$set": {"is_active": False}})
        self.assertEqual((await self.get()).status_code, 403)
        await self.db.users.update_one({"_id": ObjectId(self.admin)}, {"$set": {"is_active": True, "role": "doctor"}})
        self.assertEqual((await self.get()).status_code, 403)
        await self.db.users.delete_one({"_id": ObjectId(self.admin)})
        self.assertEqual((await self.get()).status_code, 403)

    async def test_rest_rejects_bad_pagination_and_naive_dates(self):
        for params in ({"limit": 101}, {"skip": -1}, {"start_date": "2026-11-09T00:00:00"},
                       {"start_date": "2026-11-10T00:00:00Z", "end_date": "2026-11-09T00:00:00Z"}):
            self.assertEqual((await self.get("followups", **params)).status_code, 422)

    async def test_quality_source_fence_is_internal_and_preserves_clinical_version(self):
        model = FollowUpRecord(patient_id=self.patient, created_by=self.doctor,
            follow_up_type="phone", scheduled_date=self.when, status="scheduled", notes="source")
        row = model.to_mongo()
        row.update(updated_at=self.when, mutation_version=7)
        await self.db.followup_records.insert_one(row)
        domain = FollowupService(self.db)
        source = await domain.quality_source(str(row["_id"]))
        await domain.fence_quality_source(source, None)
        stored = await self.db.followup_records.find_one({"_id": row["_id"]})
        self.assertEqual(stored["_access_fence"], 1)
        self.assertEqual((stored["updated_at"], stored["mutation_version"]), (self.when, 7))
        self.assertNotIn("_access_fence", map_followup_record_to_response(followup_from_mongo(stored)).model_dump())
        stored["_access_fence"] = "bad"
        with self.assertRaises(AppBaseException):
            await domain.fence_quality_source(stored, None)
