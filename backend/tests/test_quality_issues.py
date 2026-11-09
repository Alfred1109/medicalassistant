"""Manual issue lifecycle on unique, disposable replica-set databases."""
import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from bson import ObjectId
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pydantic import ValidationError

from app.api.routers.quality_issue_router import router, get_current_active_user, get_database
from app.core.exceptions import AppBaseException
from app.schemas.quality_issue import (AssignQualityIssue, ConfirmQualityIssue, QualityIssueCreate,
    ResolveQualityIssue, ReviewQualityIssue)
from app.services.quality_issue_service import QualityIssueService
from app.services.rehabilitation_service import RehabilitationService

URI = os.environ.get("REHAB_TEST_QUALITY_ISSUE_MONGO_URI")


class QualityIssueSchemaTests(unittest.TestCase):
    def test_manual_evidence_identity_and_cas_are_strict(self):
        data = dict(request_id="request-one", patient_id=str(ObjectId()), source_type="followup",
                    source_id=str(ObjectId()), title="Concern", description="Human-reviewed concern", evidence_refs=["ref-1"])
        for changes in ({"source_type": "automatic"}, {"evidence_refs": [" "]},
                        {"created_by": "forged"}, {"patient_id": "not-an-id"}):
            with self.assertRaises(ValidationError):
                QualityIssueCreate.model_validate({**data, **changes})
        with self.assertRaises(ValidationError):
            ConfirmQualityIssue(request_id="request-one", expected_version=True, note="checked")


@unittest.skipUnless(URI, "set REHAB_TEST_QUALITY_ISSUE_MONGO_URI to an isolated replica set")
class QualityIssueMongoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue(URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")))
        self.mongo = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=4000)
        self.db = self.mongo["rehab_quality_issue_test_" + uuid4().hex]
        ids = [ObjectId() for _ in range(8)]
        self.patient, self.other_patient, self.doctor, self.manager, self.outsider, self.admin, self.plan, self.followup = ids
        await self.db.users.insert_many([
            {"_id": self.patient, "role": "patient", "is_active": True, "name": "Confidential patient",
             "practitioners": [str(self.doctor)], "health_managers": [str(self.manager)]},
            {"_id": self.other_patient, "role": "patient", "is_active": True, "practitioners": [str(self.outsider)]},
            {"_id": self.doctor, "role": "doctor", "is_active": True, "name": "Clinician"},
            {"_id": self.manager, "role": "health_manager", "is_active": True, "name": "Manager"},
            {"_id": self.outsider, "role": "doctor", "is_active": True},
            {"_id": self.admin, "role": "admin", "is_active": True},
        ])
        await self.db.rehab_plans.insert_one({"_id": self.plan, "patient_id": str(self.patient), "status": "active"})
        await self.db["followup_records"].insert_one({"_id": self.followup, "patient_id": str(self.patient), "status": "scheduled"})
        self.actor = SimpleNamespace(id=str(self.doctor), role="doctor")
        self.svc = QualityIssueService(self.db)

    async def asyncTearDown(self):
        await self.mongo.drop_database(self.db.name)
        self.mongo.close()

    def create_payload(self, **changes):
        return QualityIssueCreate.model_validate({"request_id": uuid4().hex, "patient_id": str(self.patient),
            "source_type": "rehab_plan", "source_id": str(self.plan), "title": "Manual concern",
            "description": "A clinician observed missing documentation", "evidence_refs": ["review-record-1"], **changes})

    async def issue(self, **changes):
        return (await self.svc.create(self.create_payload(**changes), self.actor))[0]

    async def assign(self, issue):
        return await self.svc.mutate(issue["id"], "assign", AssignQualityIssue(request_id=uuid4().hex,
            expected_version=issue["version"], assignee_id=str(self.doctor), note="Assign for verification"), self.actor)

    async def confirm(self, issue):
        return await self.svc.mutate(issue["id"], "confirm", ConfirmQualityIssue(request_id=uuid4().hex,
            expected_version=issue["version"], note="Verified and accepted"), self.actor)

    async def resolve(self, issue):
        return await self.svc.mutate(issue["id"], "resolve", ResolveQualityIssue(request_id=uuid4().hex,
            expected_version=issue["version"], resolution="Documentation completed", evidence_refs=["action-record-1"]), self.actor)

    async def test_full_lifecycle_self_review_is_explicit_audited_and_closed_is_immutable(self):
        issue = await self.issue()
        self.assertEqual(issue["version"], 0)
        issue = await self.resolve(await self.confirm(await self.assign(issue)))
        issue = await self.svc.mutate(issue["id"], "review", ReviewQualityIssue(request_id=uuid4().hex,
            expected_version=issue["version"], decision="approve", note="Evidence reviewed", evidence_refs=["review-final"]), self.actor)
        self.assertEqual((issue["status"], issue["version"]), ("closed", 4))
        self.assertEqual([entry["action"] for entry in issue["timeline"]], ["create", "assign", "confirm", "resolve", "review"])
        self.assertTrue(all(entry["actor_id"] == str(self.doctor) for entry in issue["timeline"]))
        with self.assertRaises(AppBaseException):
            await self.assign(issue)
        self.assertEqual((await self.svc.detail(issue["id"], self.actor))["resolution"], "Documentation completed")

    async def test_review_return_requires_new_disposition_and_preserves_prior_evidence(self):
        issue = await self.resolve(await self.confirm(await self.assign(await self.issue())))
        issue = await self.svc.mutate(issue["id"], "review", ReviewQualityIssue(request_id=uuid4().hex,
            expected_version=issue["version"], decision="return", note="Need additional evidence", evidence_refs=["review-return"]), self.actor)
        self.assertEqual(issue["status"], "in_progress")
        issue = await self.resolve(issue)
        self.assertEqual(issue["status"], "pending_review")
        self.assertEqual(len([entry for entry in issue["timeline"] if entry["action"] == "resolve"]), 2)

    async def test_real_sources_must_exist_and_belong_to_the_authorized_patient(self):
        followup = await self.issue(source_type="followup", source_id=str(self.followup))
        self.assertEqual(followup["source_id"], str(self.followup))
        for changes in ({"source_id": str(ObjectId())}, {"patient_id": str(self.other_patient)},):
            with self.assertRaises(AppBaseException):
                await self.issue(**changes)
        await self.db.rehab_plans.update_one({"_id": self.plan}, {"$set": {"patient_id": str(self.other_patient)}})
        with self.assertRaises(AppBaseException) as caught:
            await self.issue()
        self.assertEqual(caught.exception.error_code, "QUALITY_SOURCE_MISMATCH")

    async def test_current_roles_and_patient_assignment_control_every_action(self):
        issue = await self.issue()
        for actor in (SimpleNamespace(id=str(self.patient), role="patient"),
                      SimpleNamespace(id=str(self.outsider), role="doctor"),
                      SimpleNamespace(id=str(self.admin), role="admin")):
            with self.assertRaises(AppBaseException):
                await self.svc.create(self.create_payload(), actor)
        self.assertEqual((await self.svc.detail(issue["id"], SimpleNamespace(id=str(self.admin), role="admin")))["id"], issue["id"])
        with self.assertRaises(AppBaseException):
            await self.svc.detail(issue["id"], SimpleNamespace(id=str(self.outsider), role="doctor"))
        issue = await self.assign(issue)
        with self.assertRaises(AppBaseException) as caught:
            await self.svc.mutate(issue["id"], "confirm", ConfirmQualityIssue(request_id=uuid4().hex,
                expected_version=issue["version"], note="not my assignment"), SimpleNamespace(id=str(self.manager), role="health_manager"))
        self.assertEqual(caught.exception.error_code, "QUALITY_ASSIGNEE_REQUIRED")

    async def test_assignee_directory_is_current_and_unassigned_candidates_are_rejected(self):
        directory = await self.svc.assignees(str(self.patient), self.actor)
        self.assertEqual({item["id"] for item in directory["items"]}, {str(self.doctor), str(self.manager)})
        issue = await self.issue()
        for identifier in (self.outsider, self.patient, self.admin):
            with self.assertRaises(AppBaseException):
                await self.svc.mutate(issue["id"], "assign", AssignQualityIssue(request_id=uuid4().hex,
                    expected_version=0, assignee_id=str(identifier), note="check candidate"), self.actor)
        await self.db.users.update_one({"_id": self.manager}, {"$set": {"is_active": False}})
        self.assertEqual([item["id"] for item in (await self.svc.assignees(str(self.patient), self.actor))["items"]], [str(self.doctor)])

    async def test_idempotent_create_concurrency_and_payload_conflict(self):
        payload = self.create_payload()
        results = await asyncio.gather(*[self.svc.create(payload, self.actor) for _ in range(4)])
        self.assertEqual(len({issue["id"] for issue, _ in results}), 1)
        self.assertEqual(await self.db.quality_issues.count_documents({}), 1)
        changed = payload.model_copy(update={"title": "different"})
        with self.assertRaises(AppBaseException) as caught:
            await self.svc.create(changed, self.actor)
        self.assertEqual(caught.exception.error_code, "QUALITY_IDEMPOTENCY_CONFLICT")

    async def test_mutation_cas_has_one_winner_and_successful_retry_does_not_append(self):
        issue = await self.assign(await self.issue())
        first = ConfirmQualityIssue(request_id=uuid4().hex, expected_version=1, note="accepted")
        second = ConfirmQualityIssue(request_id=uuid4().hex, expected_version=1, note="other accept")
        results = await asyncio.gather(self.svc.mutate(issue["id"], "confirm", first, self.actor),
            self.svc.mutate(issue["id"], "confirm", second, self.actor), return_exceptions=True)
        self.assertEqual(sum(isinstance(item, dict) for item in results), 1)
        winning = first if isinstance(results[0], dict) else second
        replay = await self.svc.mutate(issue["id"], "confirm", winning, self.actor)
        self.assertEqual(len(replay["timeline"]), 3)
        self.assertEqual(replay["version"], 2)

    async def test_failure_after_issue_update_rolls_back_timeline_version_and_access_fences(self):
        issue = await self.issue()
        before = await self.db.quality_issues.find_one({"_id": ObjectId(issue["id"])})
        patient = await self.db.users.find_one({"_id": self.patient})
        async def failure(*args, **kwargs):
            raise RuntimeError("injected receipt failure")
        with patch.object(self.svc, "_write_receipt", side_effect=failure):
            with self.assertRaises(RuntimeError):
                await self.assign(issue)
        self.assertEqual(await self.db.quality_issues.find_one({"_id": ObjectId(issue["id"])}), before)
        self.assertEqual(await self.db.users.find_one({"_id": self.patient}), patient)

    async def test_concurrent_assignment_revocation_rechecks_before_create(self):
        seen, release = asyncio.Event(), asyncio.Event()
        original = self.svc._fence
        first = True
        async def paused(document, session):
            nonlocal first
            if first:
                first = False
                seen.set()
                await release.wait()
            return await original(document, session)
        with patch.object(self.svc, "_fence", side_effect=paused):
            running = asyncio.create_task(self.issue())
            await asyncio.wait_for(seen.wait(), 5)
            await self.db.users.update_one({"_id": self.patient}, {"$set": {"practitioners": []}})
            release.set()
            with self.assertRaises(AppBaseException) as caught:
                await running
        self.assertEqual(caught.exception.error_code, "QUALITY_PATIENT_NOT_ASSIGNED")
        self.assertEqual(await self.db.quality_issues.count_documents({}), 0)

    async def test_source_patient_change_and_delete_during_creation_leave_no_issue(self):
        for mutation in ("reassign", "delete"):
            await self.db.rehab_plans.replace_one({"_id": self.plan}, {"_id": self.plan, "patient_id": str(self.patient)}, upsert=True)
            seen, release = asyncio.Event(), asyncio.Event()
            original = RehabilitationService.fence_quality_source
            first = True
            async def paused(service, document, session):
                nonlocal first
                if first:
                    first = False
                    seen.set()
                    await release.wait()
                return await original(service, document, session)
            with patch.object(RehabilitationService, "fence_quality_source", paused):
                running = asyncio.create_task(self.issue())
                await asyncio.wait_for(seen.wait(), 5)
                if mutation == "delete":
                    await self.db.rehab_plans.delete_one({"_id": self.plan})
                else:
                    await self.db.rehab_plans.update_one({"_id": self.plan}, {"$set": {"patient_id": str(self.other_patient)}})
                release.set()
                with self.assertRaises(AppBaseException) as caught:
                    await running
            self.assertEqual(caught.exception.error_code, "QUALITY_SOURCE_MISMATCH")
        self.assertEqual(await self.db.quality_issues.count_documents({}), 0)

    async def test_pagination_filters_and_empty_scope_never_broaden_authorization(self):
        for _ in range(23):
            await self.issue()
        first = await self.svc.list(self.actor, skip=0, limit=20)
        second = await self.svc.list(self.actor, skip=20, limit=20)
        self.assertEqual((first["total"], len(first["items"]), len(second["items"])), (23, 20, 3))
        self.assertEqual(len({item["id"] for item in first["items"] + second["items"]}), 23)
        self.assertNotIn("timeline", first["items"][0])
        self.assertEqual((await self.svc.list(SimpleNamespace(id=str(self.outsider), role="doctor")))["total"], 0)
        self.assertEqual((await self.svc.list(self.actor, status="closed"))["total"], 0)

    async def test_canonical_domain_and_inactive_account_do_not_fall_back(self):
        await self.db.patient_domain_state.insert_one({"_id": "clinical-patients-v1", "mode": "canonical"})
        with self.assertRaises(AppBaseException) as caught:
            await self.issue()
        self.assertEqual(caught.exception.error_code, "QUALITY_PATIENT_DOMAIN_UNSUPPORTED")
        await self.db.patient_domain_state.delete_many({})
        await self.db.users.update_one({"_id": self.doctor}, {"$set": {"is_active": False}})
        with self.assertRaises(AppBaseException) as caught:
            await self.issue()
        self.assertEqual(caught.exception.error_code, "QUALITY_ACCOUNT_UNAVAILABLE")

    async def test_deactivated_patient_history_is_preserved_but_not_publicly_enumerated(self):
        issue = await self.issue()
        admin = SimpleNamespace(id=str(self.admin), role="admin")
        self.assertEqual((await self.svc.list(admin))["total"], 1)
        await self.db.users.update_one({"_id": self.patient}, {"$set": {"is_active": False}})
        for actor in (self.actor, admin):
            self.assertEqual((await self.svc.list(actor))["total"], 0)
            with self.assertRaises(AppBaseException) as caught:
                await self.svc.detail(issue["id"], actor)
            self.assertEqual(caught.exception.error_code, "QUALITY_PATIENT_UNAVAILABLE")
        self.assertEqual(await self.db.quality_issues.count_documents({}), 1)
        preserved = await self.db.quality_issues.find_one({"_id": ObjectId(issue["id"])})
        self.assertEqual(len(preserved["timeline"]), 1)

    async def test_same_visible_patient_id_collision_cannot_enumerate_or_mutate_history(self):
        issue = await self.issue()
        await self.db.users.insert_one({"_id": str(self.patient), "role": "patient", "is_active": True,
            "practitioners": [str(self.outsider)], "name": "Unrelated same-visible-ID patient"})
        for actor in (self.actor, SimpleNamespace(id=str(self.admin), role="admin")):
            with self.assertRaises(AppBaseException) as caught:
                await self.svc.list(actor)
            self.assertEqual(caught.exception.error_code, "QUALITY_PATIENT_IDENTITY_AMBIGUOUS")
            with self.assertRaises(AppBaseException):
                await self.svc.detail(issue["id"], actor)
        with self.assertRaises(AppBaseException):
            await self.svc.assignees(str(self.patient), self.actor)
        with self.assertRaises(AppBaseException):
            await self.issue()
        with self.assertRaises(AppBaseException):
            await self.assign(issue)
        self.assertEqual(await self.db.quality_issues.count_documents({}), 1)
        self.assertEqual((await self.db.quality_issues.find_one({"_id": ObjectId(issue["id"])}))["version"], 0)

    async def test_same_visible_clinician_id_is_not_a_valid_actor_or_assignee(self):
        issue = await self.issue()
        await self.db.users.insert_one({"_id": str(self.doctor), "role": "doctor", "is_active": True})
        with self.assertRaises(AppBaseException) as caught:
            await self.svc.list(self.actor)
        self.assertEqual(caught.exception.error_code, "QUALITY_ACCOUNT_UNAVAILABLE")
        manager = SimpleNamespace(id=str(self.manager), role="health_manager")
        directory = await self.svc.assignees(str(self.patient), manager)
        self.assertNotIn(str(self.doctor), [item["id"] for item in directory["items"]])
        with self.assertRaises(AppBaseException) as caught:
            await self.svc.mutate(issue["id"], "assign", AssignQualityIssue(request_id=uuid4().hex,
                expected_version=0, assignee_id=str(self.doctor), note="Must not select ambiguous account"), manager)
        self.assertEqual(caught.exception.error_code, "QUALITY_ASSIGNEE_UNAVAILABLE")

    async def test_list_patient_identity_verification_is_batched_not_n_plus_one(self):
        issue = await self.issue()
        template = await self.db.quality_issues.find_one({"_id": ObjectId(issue["id"])})
        patients = [{"_id": ObjectId(), "role": "patient", "is_active": True,
                     "practitioners": [str(self.doctor)]} for _ in range(30)]
        await self.db.users.insert_many(patients)
        await self.db.quality_issues.insert_many([{**template, "_id": ObjectId(), "patient_id": str(patient["_id"])} for patient in patients])
        calls = []
        original = AsyncIOMotorCollection.find
        def counted(collection, *args, **kwargs):
            if collection.name == "users":
                calls.append(args[0])
            return original(collection, *args, **kwargs)
        with patch.object(AsyncIOMotorCollection, "find", counted):
            result = await self.svc.list(self.actor, limit=100)
        self.assertEqual(result["total"], 31)
        self.assertEqual(len(calls), 3)  # actor, candidate scope, one identity batch

    async def test_rest_scope_privacy_static_route_and_retry_status(self):
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[get_current_active_user] = lambda: self.actor
        app.dependency_overrides[get_database] = lambda: self.db
        @app.exception_handler(AppBaseException)
        async def domain_error(request, error):
            return JSONResponse(status_code=error.status_code, content={"code": error.error_code})
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            body = self.create_payload().model_dump()
            first = await client.post("/api/quality/issues", json=body)
            again = await client.post("/api/quality/issues", json=body)
            self.assertEqual((first.status_code, again.status_code), (201, 200))
            self.assertEqual(first.headers["cache-control"], "no-store")
            self.assertTrue(first.json()["created_at"].endswith("+00:00"))
            directory = await client.get("/api/quality/issues/assignees", params={"patient_id": str(self.patient)})
            self.assertEqual(directory.status_code, 200)
            self.actor.id, self.actor.role = str(self.patient), "patient"
            self.assertEqual((await client.get("/api/quality/issues")).status_code, 403)
