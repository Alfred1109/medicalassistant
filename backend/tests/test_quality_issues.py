"""Manual issue lifecycle on unique, disposable replica-set databases."""
import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from bson import ObjectId
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pydantic import ValidationError

from app.api.routers.quality_issue_router import router, get_current_active_user, get_database
from app.core.exceptions import AppBaseException
from app.core.patient_access import assigned_patient_query
from app.patients.legacy import LegacyPatientRepository
from app.patients.migration import inspect_migration, migrate_legacy_patients
from app.patients.repository import ACCOUNT_LINKS, PATIENTS, ClinicalPatientRepository
from app.schemas.quality_issue import (AssignQualityIssue, ConfirmQualityIssue, QualityIssueCreate,
    ResolveQualityIssue, ReviewQualityIssue)
from app.services.quality_issue_service import QualityIssueService
from app.services.rehabilitation_service import RehabilitationService

URI = os.environ.get("REHAB_TEST_QUALITY_ISSUE_MONGO_URI")
E2E_URI = os.environ.get("REHAB_TEST_PATIENT_E2E_URI")


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


class AggregateCursor:
    async def to_list(self, length=None):
        return [{"items": [], "count": [{"total": 0}]}]


class FakeScopeDatabase:
    """最小 fake：QualityIssueService 构造走 db[ISSUES]/db[OPERATIONS]，list 只触 issues。"""

    def __init__(self):
        self.quality_issues = SimpleNamespace(aggregate=lambda pipeline: AggregateCursor())
        self.quality_issue_operations = SimpleNamespace()

    def __getitem__(self, name):
        return getattr(self, name)


class QualityListScopeDispatchTests(unittest.IsolatedAsyncioTestCase):
    """T50 缺陷 1（质控同型迁移）：list 非 admin 范围解析必须走内核
    assigned_scope_ids（legacy 分支保留 is_active 精化），admin 保持原
    LegacyPatientRepository 全量分支。当前 canonical 被域门闩挡住，此锁定
    防止门闩移除后 canonical 查询形状被交给 users 执行。"""

    async def test_non_admin_scope_resolution_goes_through_kernel(self):
        scope = AsyncMock(return_value=[str(ObjectId())])
        with patch.object(QualityIssueService, "_actor",
                          new=AsyncMock(return_value=SimpleNamespace(_id="account"))), \
             patch("app.services.quality_issue_service.assigned_scope_ids", new=scope):
            service = QualityIssueService(FakeScopeDatabase())
            result = await service.list(SimpleNamespace(id="account", role="doctor"), limit=20)
        self.assertEqual(result["total"], 0)
        scope.assert_awaited_once()
        args, kwargs = scope.await_args
        self.assertEqual(args[1:], ("account", "doctor"))
        self.assertEqual(kwargs, {"extra_query": {"is_active": True}})

    async def test_admin_scope_keeps_legacy_full_patient_branch(self):
        with patch.object(QualityIssueService, "_actor",
                          new=AsyncMock(return_value=SimpleNamespace(_id="account"))), \
             patch("app.services.quality_issue_service.assigned_scope_ids") as kernel, \
             patch("app.services.quality_issue_service.LegacyPatientRepository") as adapter:
            adapter.return_value.assigned_ids = AsyncMock(return_value=[])
            service = QualityIssueService(FakeScopeDatabase())
            result = await service.list(SimpleNamespace(id="account", role="admin"), limit=20)
        self.assertEqual(result["total"], 0)
        adapter.return_value.assigned_ids.assert_awaited_once_with(
            {"role": "patient", "is_active": True})
        kernel.assert_not_awaited()


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
        # outsider 医护名下患者也需要自己的合法 rehab 来源：create 的
        # _source 校验要求 source 文档 patient_id 与 payload.patient_id 一致
        # （QUALITY_SOURCE_MISMATCH 404），否则该用例在 create 阶段即失败。
        self.other_plan = ObjectId()
        await self.db.rehab_plans.insert_one({"_id": self.other_plan,
            "patient_id": str(self.other_patient), "status": "active"})
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

    async def test_list_patient_scope_equals_legacy_assigned_ids(self):
        """legacy 域：list 患者范围接入 assigned_scope_query 后与原 assigned_ids 路径等价。"""
        legacy = await LegacyPatientRepository(self.db).assigned_ids(
            {**assigned_patient_query(str(self.doctor), "doctor"), "is_active": True})
        self.assertEqual(legacy, [str(self.patient)])
        outsider = SimpleNamespace(id=str(self.outsider), role="doctor")
        self.assertEqual(await LegacyPatientRepository(self.db).assigned_ids(
            {**assigned_patient_query(str(self.outsider), "doctor"), "is_active": True}),
            [str(self.other_patient)])
        mine = await self.issue()
        theirs = await self.svc.create(
            self.create_payload(patient_id=str(self.other_patient),
                                source_id=str(self.other_plan)), outsider)
        result = await self.svc.list(self.actor, limit=100)
        self.assertEqual(result["total"], 1)
        self.assertEqual([item["id"] for item in result["items"]], [mine["id"]])
        self.assertEqual([item["id"] for item in (await self.svc.list(outsider, limit=100))["items"]],
                         [theirs[0]["id"]])

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

    async def test_canonical_domain_does_not_fall_back_to_users(self):
        # T63 波次 2 门闩移除：canonical 不再 503，但患者实体只读
        # clinical_patients——本用例只造了 users 患者，canonical 下必须
        # fail-closed 404，绝不回读 users 命中存量账号文档。
        await self.db.patient_domain_state.insert_one(
            {"_id": "clinical-patients-v1", "mode": "canonical", "schema_version": 1})
        with self.assertRaises(AppBaseException) as caught:
            await self.issue()
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(caught.exception.error_code, "QUALITY_PATIENT_UNAVAILABLE")
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



@unittest.skipUnless(E2E_URI, "set REHAB_TEST_PATIENT_E2E_URI to an isolated replica set")
class QualityIssueCanonicalReplicaTests(unittest.IsolatedAsyncioTestCase):
    """T63 波次 2：副本集门控下 canonical 模式质控全流程。

    造数手法复用 test_canonical_accountless_loop.py：legacy 最小数据 →
    migrate_legacy_patients → canonical 模式 → 质控全生命周期；断言栅栏
    双载体（account_fences + clinical_patients._fence_quality_access，栅栏名
    域化 "quality_access"（T67 缺陷 1），users 不再
    承担栅栏计数）与 patient_id 引用一致性语义（迁移保留主键值不变）。
    """

    SOURCE = {"origin": "https://source.example", "system": "form-platform-11344",
              "environment": "production", "patient_id": 311}

    @staticmethod
    def stopped():
        return {"application_stopped": True, "guard_reference": "qc-replica-fixture"}

    async def asyncSetUp(self):
        self.assertTrue(E2E_URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")))

        self.mongo = AsyncIOMotorClient(E2E_URI, serverSelectionTimeoutMS=4000)
        self.db = self.mongo["rehab_quality_canonical_" + uuid4().hex]
        self.temp = tempfile.TemporaryDirectory()
        self.doctor, self.manager, self.outsider, self.admin = (str(ObjectId()) for _ in range(4))
        self.patient = ObjectId()
        self.plan = ObjectId()
        await self.db.users.insert_many([
            {"_id": self.patient, "role": "patient", "is_active": True, "name": "迁移患者",
             "practitioners": [self.doctor], "health_managers": [self.manager]},
            {"_id": ObjectId(self.doctor), "role": "doctor", "is_active": True, "name": "Clinician"},
            {"_id": ObjectId(self.manager), "role": "health_manager", "is_active": True, "name": "Manager"},
            {"_id": ObjectId(self.outsider), "role": "doctor", "is_active": True, "name": "Outsider"},
            {"_id": ObjectId(self.admin), "role": "admin", "is_active": True},
        ])
        await self.db.rehab_plans.insert_one(
            {"_id": self.plan, "patient_id": str(self.patient), "status": "active"})
        result = await migrate_legacy_patients(self.db,
            expected_manifest=await inspect_migration(self.db),
            backup_directory=Path(self.temp.name) / uuid4().hex,
            reviewer="qc-replica-reviewer", evidence_reference="qc-replica-evidence",
            maintenance_guard=self.stopped)
        self.assertEqual(result["migrated_count"], 1)
        self.repo = ClinicalPatientRepository(self.db)
        self.patient_id = str(self.patient)  # 迁移保留主键：clinical.patient_id == str(users._id)
        self.assertEqual((await self.repo.get(self.patient_id))["patient_id"], self.patient_id)
        self.svc = QualityIssueService(self.db)
        self.actor = SimpleNamespace(id=self.doctor, role="doctor")

    async def asyncTearDown(self):
        await self.mongo.drop_database(self.db.name)
        self.mongo.close()
        self.temp.cleanup()

    def create_payload(self, **changes):
        return QualityIssueCreate.model_validate({"request_id": uuid4().hex, "patient_id": self.patient_id,
            "source_type": "rehab_plan", "source_id": str(self.plan), "title": "Manual concern",
            "description": "A clinician observed missing documentation", "evidence_refs": ["review-record-1"], **changes})

    async def issue(self, **changes):
        return (await self.svc.create(self.create_payload(**changes), self.actor))[0]

    async def fence_state(self):
        return {"account": await self.db.account_fences.find_one(
                    {"account_id": self.doctor, "fence_name": "quality_access"}),
                "patient": (await self.repo.get(self.patient_id)).get("_fence_quality_access"),
                "users_doctor": (await self.db.users.find_one({"_id": ObjectId(self.doctor)})).get("_access_fence"),
                "users_patient": (await self.db.users.find_one({"_id": self.patient})).get("_access_fence")}

    async def test_full_lifecycle_scope_and_dual_carrier_fence(self):
        # 创建即双载体复核：账号跳 account_fences（count=1）、患者跳
        # clinical_patients._fence_quality_access（=1）；users 文档零栅栏写入。
        issue = await self.issue()
        state = await self.fence_state()
        self.assertEqual(state["patient"], 1)
        self.assertEqual(state["account"]["count"], 1)
        self.assertIsNone(state["users_doctor"])
        self.assertIsNone(state["users_patient"])
        # 全生命周期：指派（第二次账号跳 → count=2）→ 确认 → 处置 → 复核关闭
        issue = await self.svc.mutate(issue["id"], "assign", AssignQualityIssue(
            request_id=uuid4().hex, expected_version=0, assignee_id=self.doctor,
            note="Assign for verification"), self.actor)
        # assign 两跳栅栏：_patient 双载体复核（账号跳 + 患者跳）+ _assignee
        # 账号跳 → 账号计数 1+2=3，患者栅栏 1+1=2。
        state = await self.fence_state()
        self.assertEqual(state["account"]["count"], 3)
        self.assertEqual(state["patient"], 2)
        issue = await self.svc.mutate(issue["id"], "confirm", ConfirmQualityIssue(
            request_id=uuid4().hex, expected_version=1, note="Verified and accepted"), self.actor)
        issue = await self.svc.mutate(issue["id"], "resolve", ResolveQualityIssue(
            request_id=uuid4().hex, expected_version=2, resolution="Documentation completed",
            evidence_refs=["action-record-1"]), self.actor)
        issue = await self.svc.mutate(issue["id"], "review", ReviewQualityIssue(
            request_id=uuid4().hex, expected_version=3, decision="approve",
            note="Evidence reviewed", evidence_refs=["review-final"]), self.actor)
        self.assertEqual((issue["status"], issue["version"]), ("closed", 4))
        self.assertEqual([entry["action"] for entry in issue["timeline"]],
                         ["create", "assign", "confirm", "resolve", "review"])
        self.assertEqual((await self.svc.detail(issue["id"], self.actor))["resolution"],
                         "Documentation completed")
        # list 范围走 clinical_patients 归属：本人可见，越权医生不可见；
        # admin 经 _all_patient_ids 枚举全部 active canonical 患者。
        outsider = SimpleNamespace(id=self.outsider, role="doctor")
        mine = await self.svc.list(self.actor, limit=100)
        self.assertEqual((mine["total"], [item["id"] for item in mine["items"]]), (1, [issue["id"]]))
        self.assertEqual((await self.svc.list(outsider, limit=100))["total"], 0)
        self.assertEqual((await self.svc.list(SimpleNamespace(id=self.admin, role="admin")))["total"], 1)
        # 未分配医生的创建与读取被拒（canonical 归属校验同构）
        with self.assertRaises(AppBaseException) as denied:
            await self.svc.create(self.create_payload(request_id=uuid4().hex), outsider)
        self.assertEqual(denied.exception.error_code, "QUALITY_PATIENT_NOT_ASSIGNED")
        with self.assertRaises(AppBaseException):
            await self.svc.detail(issue["id"], outsider)

    async def test_accountless_patient_reference_and_deactivation_semantics(self):
        # 无账号临床患者：canonical 建档（无 users/links 写入）→ 直接更新归属
        # 替位（与迁移投影同一数据形态）→ 质控全流程引用其 patient_id。
        document = await self.repo.create_from_source(self.SOURCE,
            reviewer="qc-replica-reviewer", evidence_reference="qc-replica-evidence-2",
            name="无账号患者")
        accountless_id = document["patient_id"]
        self.assertEqual(await self.db.users.count_documents({"role": "patient"}), 1)
        self.assertEqual(await self.db[ACCOUNT_LINKS].count_documents({"patient_id": accountless_id}), 0)
        await self.db[PATIENTS].update_one({"patient_id": accountless_id},
            {"$set": {"practitioners": [self.doctor], "health_managers": [self.manager]}})
        accountless_plan = ObjectId()
        await self.db.rehab_plans.insert_one(
            {"_id": accountless_plan, "patient_id": accountless_id, "status": "active"})
        issue = await self.issue(patient_id=accountless_id, source_id=str(accountless_plan))
        self.assertEqual(issue["patient_id"], accountless_id)
        listed = await self.svc.list(self.actor, limit=100)
        self.assertEqual([item["id"] for item in listed["items"]], [issue["id"]])
        self.assertEqual({item["id"] for item in (await self.svc.assignees(accountless_id, self.actor))["items"]},
                         {self.doctor, self.manager})
        # 停用（status != active）后：历史文档保留，但对象级访问 404、范围枚举排除
        await self.db[PATIENTS].update_one({"patient_id": accountless_id}, {"$set": {"status": "inactive"}})
        with self.assertRaises(AppBaseException) as unavailable:
            await self.svc.detail(issue["id"], self.actor)
        self.assertEqual((unavailable.exception.status_code, unavailable.exception.error_code), (404, "QUALITY_PATIENT_UNAVAILABLE"))
        self.assertEqual((await self.svc.list(self.actor, limit=100))["total"], 0)
        with self.assertRaises(AppBaseException):
            await self.issue(patient_id=accountless_id)
        self.assertEqual(await self.db.quality_issues.count_documents({}), 1)


if __name__ == "__main__":
    unittest.main()
