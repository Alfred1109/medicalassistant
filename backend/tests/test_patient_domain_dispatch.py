"""患者域开关分派：legacy 行为不变、canonical 走临床域、未知状态 fail-closed。

全部使用内存 fake（不依赖真实 Mongo）。fake 语义对齐 motor：
- `db[name]` 与属性访问都可取得集合；
- `find` 返回带 `to_list` 的游标；`$in` 采用严格相等（ObjectId 与其字符串
  字面量是不同候选，与 LegacyPatientRepository 的双字面量兼容语义一致）。
"""
import re
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from bson import ObjectId
from pymongo.errors import PyMongoError

from app.core.patient_access import (
    PatientAccessError, assigned_scope_ids, assigned_scope_query, ensure_patient_access,
    ensure_self_patient_access, load_patient_doc, patient_domain_mode)
from app.db.indexes import ensure_patient_scope_indexes
from app.patients.legacy import LegacyPatientIdentityError
from app.patients.repository import (
    SCHEMA_VERSION, STATE_ID, ClinicalPatientRepository,
    PatientDomainError, create_patient_indexes)

CANONICAL_STATE = {"_id": STATE_ID, "mode": "canonical", "schema_version": SCHEMA_VERSION}
PATIENT_ID, DOCTOR_ID, MANAGER_ID = str(ObjectId()), ObjectId(), str(ObjectId())


class FakeCursor:
    def __init__(self, documents):
        self.documents = documents
        self._iter = None

    async def to_list(self, length=None):
        rows = list(self.documents)
        return rows if length is None else rows[:length]

    def __aiter__(self):
        self._iter = iter(self.documents)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration from None


def _matches(document, query):
    for key, condition in query.items():
        if key == "$or":
            if not any(_matches(document, sub) for sub in condition):
                return False
            continue
        value = document.get(key)
        if isinstance(condition, dict):
            if "$in" in condition:
                candidates = condition["$in"]
                if isinstance(value, list):
                    # Mongo 数组字段语义：任一元素命中即匹配（保持严格相等）。
                    if not any(item == element for item in candidates for element in value):
                        return False
                elif not any(value == item for item in candidates):
                    return False
            elif "$regex" in condition:
                if not isinstance(value, str):
                    return False
                flags = re.IGNORECASE if "i" in (condition.get("$options") or "") else 0
                if not re.search(condition["$regex"], value, flags):
                    return False
            elif "$exists" in condition:
                if bool(key in document) is not bool(condition["$exists"]):
                    return False
            else:
                return False
        elif value != condition:
            return False
    return True


class FakeCollection:
    def __init__(self, documents=()):
        self.documents = list(documents)

    async def find_one(self, query, *args, **kwargs):
        for document in self.documents:
            if _matches(document, query):
                return deepcopy(document)
        return None

    def find(self, query, projection=None, **kwargs):
        return FakeCursor([deepcopy(document) for document in self.documents
                           if _matches(document, query)])


class BrokenCollection(FakeCollection):
    """模拟状态读取的传输层失败（fail-closed 断言用）。"""

    async def find_one(self, query, *args, **kwargs):
        raise PyMongoError("synthetic state read failure")


class FakeDatabase:
    def __init__(self, state=None, state_collection=None, users=None,
                 clinical=None, links=None):
        self.users = users if users is not None else FakeCollection()
        self.clinical_patients = clinical if clinical is not None else FakeCollection()
        self.patient_account_links = links if links is not None else FakeCollection()
        self.patient_domain_state = (state_collection if state_collection is not None
                                     else FakeCollection([state] if state else []))
        self.devices = FakeCollection()
        self._collections = {name: getattr(self, name) for name in
                             ("users", "clinical_patients", "patient_account_links",
                              "patient_domain_state", "devices")}

    def __getitem__(self, name):
        return self._collections.setdefault(name, FakeCollection())


def legacy_user(identifier, *, practitioners=(), health_managers=(), role="patient"):
    return {"_id": ObjectId(identifier) if ObjectId.is_valid(identifier) else identifier,
            "role": role, "is_active": True, "name": "synthetic-legacy",
            "practitioners": list(practitioners), "health_managers": list(health_managers)}


def clinical_patient(identifier, *, practitioners=(), health_managers=(),
                     name=None, status="active"):
    return {"_id": ObjectId(identifier) if ObjectId.is_valid(identifier) else identifier,
            "patient_id": str(identifier), "schema_version": SCHEMA_VERSION,
            "status": status, "name": name, "practitioners": list(practitioners),
            "health_managers": list(health_managers), "legacy_user_id": str(identifier)}


def verified_link(identifier):
    return {"_id": "legacy:" + identifier, "account_id": identifier,
            "account_document_id": ObjectId(identifier) if ObjectId.is_valid(identifier) else identifier,
            "patient_id": identifier, "source": "legacy_same_document",
            "schema_version": SCHEMA_VERSION, "status": "verified",
            "audit": {"reviewer": "synthetic-reviewer", "evidence_reference": "synthetic-evidence",
                      "operation": "legacy_same_document_migration",
                      "at": datetime.now(timezone.utc)}}


def canonical_db(*, clinical=(), links=(), users=()):
    def collection(value):
        return value if isinstance(value, FakeCollection) else FakeCollection(list(value))
    return FakeDatabase(state=dict(CANONICAL_STATE), clinical=collection(clinical),
                        links=collection(links), users=collection(users))


class LegacyDispatchTests(unittest.IsolatedAsyncioTestCase):
    """无状态文档（现状默认）：所有内核入口保持 legacy 语义。"""

    async def test_missing_state_document_keeps_every_legacy_entry_point(self):
        db = FakeDatabase(users=FakeCollection([
            legacy_user(PATIENT_ID, practitioners=[DOCTOR_ID])]))
        self.assertEqual(await patient_domain_mode(db), "legacy")
        patient = await load_patient_doc(db, PATIENT_ID)
        self.assertEqual(str(patient["_id"]), PATIENT_ID)
        self.assertEqual(await ensure_patient_access(db, PATIENT_ID, str(DOCTOR_ID), "doctor"),
                         patient)
        self.assertEqual(await ensure_self_patient_access(
            db, type("Actor", (), {"id": PATIENT_ID, "role": "patient"})()), PATIENT_ID)
        query = await assigned_scope_query(db, str(DOCTOR_ID), "doctor")
        self.assertEqual(query, {"role": "patient",
                                 "practitioners": {"$in": [str(DOCTOR_ID), DOCTOR_ID]}})

    async def test_ambiguous_legacy_identity_still_latches_503(self):
        db = FakeDatabase(users=FakeCollection([
            legacy_user(PATIENT_ID), legacy_user(PATIENT_ID)]))
        with self.assertRaises(LegacyPatientIdentityError) as ambiguous:
            await load_patient_doc(db, PATIENT_ID)
        self.assertEqual(ambiguous.exception.status_code, 503)

    async def test_unassigned_medical_role_is_still_rejected(self):
        db = FakeDatabase(users=FakeCollection([legacy_user(PATIENT_ID)]))
        with self.assertRaises(PatientAccessError) as denied:
            await ensure_patient_access(db, PATIENT_ID, str(DOCTOR_ID), "doctor")
        self.assertEqual(denied.exception.status_code, 403)


class FailClosedStateTests(unittest.IsolatedAsyncioTestCase):
    """状态读取失败或未知状态：拒绝请求，绝不回退 legacy。"""

    async def test_unreadable_state_rejects_instead_of_legacy_fallback(self):
        db = FakeDatabase(state_collection=BrokenCollection(),
                          users=FakeCollection([legacy_user(PATIENT_ID)]))
        with self.assertRaises(PatientAccessError) as rejected:
            await patient_domain_mode(db)
        self.assertEqual(rejected.exception.status_code, 503)
        self.assertEqual(rejected.exception.error_code, "PATIENT_DOMAIN_STATE_UNAVAILABLE")
        for operation in (lambda: load_patient_doc(db, PATIENT_ID),
                          lambda: ensure_patient_access(db, PATIENT_ID, str(DOCTOR_ID), "doctor"),
                          lambda: ensure_self_patient_access(
                              db, type("Actor", (), {"id": PATIENT_ID, "role": "patient"})()),
                          lambda: assigned_scope_query(db, str(DOCTOR_ID), "doctor")):
            with self.assertRaises(PatientAccessError) as rejected:
                await operation()
            self.assertEqual(rejected.exception.status_code, 503)
            self.assertEqual(rejected.exception.error_code, "PATIENT_DOMAIN_STATE_UNAVAILABLE")
        self.assertEqual(db.users.documents, [legacy_user(PATIENT_ID)])

    async def test_migrating_or_version_mismatched_state_is_rejected(self):
        users = FakeCollection([legacy_user(PATIENT_ID)])
        for state in ({"_id": STATE_ID, "mode": "migrating", "schema_version": SCHEMA_VERSION},
                      {"_id": STATE_ID, "mode": "canonical", "schema_version": SCHEMA_VERSION + 1},
                      # 显式 legacy 但版本不符/缺失：同样 fail-closed，绝不猜域
                      {"_id": STATE_ID, "mode": "legacy", "schema_version": SCHEMA_VERSION + 1},
                      {"_id": STATE_ID, "mode": "legacy"},
                      {"_id": STATE_ID, "mode": "unknown-mode", "schema_version": SCHEMA_VERSION}):
            with self.subTest(state=state["mode"]):
                db = FakeDatabase(state=state, users=FakeCollection(users.documents))
                with self.assertRaises(PatientAccessError) as rejected:
                    await load_patient_doc(db, PATIENT_ID)
                self.assertEqual(rejected.exception.status_code, 503)
                self.assertEqual(rejected.exception.error_code, "PATIENT_DOMAIN_STATE_UNAVAILABLE")


class ExplicitLegacyStateTests(unittest.IsolatedAsyncioTestCase):
    """显式 `{mode: "legacy"}` 状态（回拨 SOP 载体）：与无文档 legacy 行为完全一致。

    差别仅在状态可审计、回拨不会静默降级；canonical 仓库写路径
    （require_canonical）在该状态下保持 fail-closed 拒绝。
    """

    def explicit_legacy_db(self, **kwargs):
        return FakeDatabase(state={"_id": STATE_ID, "mode": "legacy",
                                   "schema_version": SCHEMA_VERSION,
                                   "reviewer": "rollback-reviewer",
                                   "evidence_reference": "change-ticket-42",
                                   "operation": "canonical_domain_rollback"}, **kwargs)

    async def test_explicit_legacy_state_keeps_every_legacy_entry_point(self):
        db = self.explicit_legacy_db(users=FakeCollection([
            legacy_user(PATIENT_ID, practitioners=[DOCTOR_ID])]))
        self.assertEqual(await patient_domain_mode(db), "legacy")
        patient = await load_patient_doc(db, PATIENT_ID)
        self.assertEqual(str(patient["_id"]), PATIENT_ID)
        self.assertEqual(await ensure_patient_access(db, PATIENT_ID, str(DOCTOR_ID), "doctor"),
                         patient)
        # 患者自取不再要求 verified 链接：与无文档 legacy 完全一致
        self.assertEqual(await ensure_self_patient_access(
            db, type("Actor", (), {"id": PATIENT_ID, "role": "patient"})()), PATIENT_ID)
        self.assertEqual(await assigned_scope_query(db, str(DOCTOR_ID), "doctor"),
                         {"role": "patient",
                          "practitioners": {"$in": [str(DOCTOR_ID), DOCTOR_ID]}})
        scope = await assigned_scope_ids(db, str(DOCTOR_ID), "doctor")
        self.assertEqual(scope, [PATIENT_ID])  # 范围执行仍落在 users

    async def test_canonical_repository_paths_refuse_without_half_state(self):
        """回拨后 canonical 读写路径（require_canonical）fail-closed，不产生半状态。"""
        db = self.explicit_legacy_db(
            clinical=FakeCollection([clinical_patient(PATIENT_ID)]),
            links=FakeCollection([verified_link(PATIENT_ID)]))
        repo = ClinicalPatientRepository(db)
        for operation in (lambda: repo.get(PATIENT_ID),
                          lambda: repo.list_assigned(str(DOCTOR_ID), "doctor"),
                          lambda: repo.resolve_self(PATIENT_ID),
                          lambda: repo.create_from_source(
                              {"origin": "https://source.example",
                               "system": "form-platform-11344", "environment": "production",
                               "patient_id": 1},
                              reviewer="reviewer", evidence_reference="evidence")):
            with self.subTest(operation=operation):
                with self.assertRaises(PatientDomainError) as refused:
                    await operation()
                self.assertEqual(refused.exception.code, "PATIENT_DOMAIN_NOT_MIGRATED")
        # fail-closed 拒绝不产生写入：clinical/links/状态文档原样保留
        self.assertEqual(len(db.clinical_patients.documents), 1)
        self.assertEqual(len(db.patient_account_links.documents), 1)
        self.assertEqual(db.patient_domain_state.documents[0]["mode"], "legacy")

    async def test_legacy_version_mismatch_still_fails_closed(self):
        db = FakeDatabase(state={"_id": STATE_ID, "mode": "legacy",
                                 "schema_version": SCHEMA_VERSION + 1},
                          users=FakeCollection([legacy_user(PATIENT_ID)]))
        with self.assertRaises(PatientAccessError) as rejected:
            await load_patient_doc(db, PATIENT_ID)
        self.assertEqual(rejected.exception.status_code, 503)
        self.assertEqual(rejected.exception.error_code, "PATIENT_DOMAIN_STATE_UNAVAILABLE")


class CanonicalDispatchTests(unittest.IsolatedAsyncioTestCase):
    """canonical 状态：对象读取、归属校验、self 解析与范围查询走临床域。"""

    async def test_object_access_reads_clinical_patient_and_never_users(self):
        doctor = legacy_user(DOCTOR_ID, role="doctor")
        db = canonical_db(clinical=[clinical_patient(PATIENT_ID, practitioners=[DOCTOR_ID])],
                          users=[doctor, legacy_user(PATIENT_ID)])
        patient = await load_patient_doc(db, PATIENT_ID)
        self.assertEqual(patient["patient_id"], PATIENT_ID)
        self.assertNotIn("role", patient)
        self.assertNotIn("is_active", patient)
        self.assertEqual(await ensure_patient_access(db, PATIENT_ID, str(DOCTOR_ID), "doctor"),
                         patient)
        # canonical 分支不以 users 的 is_active 作为患者可用状态
        self.assertEqual(db.users.documents, [doctor, legacy_user(PATIENT_ID)])

    async def test_missing_clinical_patient_stays_404_without_users_fallback(self):
        db = canonical_db(users=[legacy_user(PATIENT_ID)])
        with self.assertRaises(PatientAccessError) as missing:
            await load_patient_doc(db, PATIENT_ID)
        self.assertEqual(missing.exception.status_code, 404)
        self.assertEqual(missing.exception.error_code, "PATIENT_NOT_FOUND")

    async def test_assignment_check_uses_clinical_relation_fields(self):
        db = canonical_db(clinical=[clinical_patient(PATIENT_ID, health_managers=[MANAGER_ID])])
        self.assertEqual((await ensure_patient_access(
            db, PATIENT_ID, MANAGER_ID, "health_manager"))["patient_id"], PATIENT_ID)
        with self.assertRaises(PatientAccessError) as denied:
            await ensure_patient_access(db, PATIENT_ID, MANAGER_ID, "doctor")
        self.assertEqual(denied.exception.status_code, 403)

    async def test_self_resolution_requires_verified_link_and_active_clinical_record(self):
        clinical = clinical_patient(PATIENT_ID)
        actor = type("Actor", (), {"id": PATIENT_ID, "role": "patient"})()
        db = canonical_db(clinical=[clinical], links=[verified_link(PATIENT_ID)],
                          users=[legacy_user(PATIENT_ID)])
        self.assertEqual(await ensure_self_patient_access(db, actor), PATIENT_ID)

        # 无链接 / 链接停用 / 临床记录不可用 / 账号不可用：一律拒绝
        for mutate in (lambda documents: documents["links"].documents.clear(),
                       lambda documents: documents["links"].documents[0].update(status="disabled"),
                       lambda documents: documents["clinical"].documents[0].update(status="inactive"),
                       lambda documents: documents["users"].documents[0].update(is_active=False)):
            documents = {"clinical": FakeCollection([deepcopy(clinical)]),
                         "links": FakeCollection([verified_link(PATIENT_ID)]),
                         "users": FakeCollection([legacy_user(PATIENT_ID)])}
            mutate(documents)
            broken = canonical_db(clinical=documents["clinical"], links=documents["links"],
                                  users=documents["users"])
            with self.subTest(stage=mutate):
                with self.assertRaises(PatientAccessError) as denied:
                    await ensure_self_patient_access(broken, actor)
                self.assertEqual(denied.exception.status_code, 403)

    async def test_self_resolution_never_assumes_account_id_is_patient_id(self):
        tampered = verified_link(PATIENT_ID)
        tampered["patient_id"] = str(ObjectId())  # 链接两侧不一致
        db = canonical_db(clinical=[clinical_patient(PATIENT_ID)], links=[tampered],
                          users=[legacy_user(PATIENT_ID)])
        actor = type("Actor", (), {"id": PATIENT_ID, "role": "patient"})()
        with self.assertRaises(PatientAccessError) as denied:
            await ensure_self_patient_access(db, actor)
        self.assertEqual(denied.exception.status_code, 403)

    async def test_assigned_scope_query_switches_shape_by_domain(self):
        legacy_db = FakeDatabase(users=FakeCollection([legacy_user(PATIENT_ID)]))
        legacy_query = await assigned_scope_query(legacy_db, MANAGER_ID, "health_manager")
        self.assertEqual(legacy_query, {"role": "patient",
                                        "health_managers": {"$in": [MANAGER_ID, ObjectId(MANAGER_ID)]}})
        canonical = await assigned_scope_query(canonical_db(), MANAGER_ID, "health_manager")
        self.assertEqual(canonical, {"status": "active",
                                     "health_managers": {"$in": [MANAGER_ID, ObjectId(MANAGER_ID)]}})
        for db in (legacy_db, canonical_db()):
            with self.subTest(mode=await patient_domain_mode(db)):
                with self.assertRaises(PatientAccessError):
                    await assigned_scope_query(db, MANAGER_ID, "patient")

    async def test_assigned_scope_ids_executes_on_the_domain_collection(self):
        """范围解析构造+执行一体：canonical 落 clinical_patients，legacy 落 users。"""
        doctor = legacy_user(DOCTOR_ID, role="doctor")
        db = canonical_db(clinical=[clinical_patient(PATIENT_ID, practitioners=[DOCTOR_ID]),
                                    clinical_patient(str(ObjectId()), practitioners=[DOCTOR_ID],
                                                     status="inactive")],
                          users=[doctor, legacy_user(PATIENT_ID)])
        self.assertEqual(await assigned_scope_ids(db, str(DOCTOR_ID), "doctor"), [PATIENT_ID])
        self.assertEqual(db.users.documents, [doctor, legacy_user(PATIENT_ID)])

    async def test_assigned_scope_ids_legacy_path_equals_original_assigned_ids(self):
        user = legacy_user(PATIENT_ID, practitioners=[DOCTOR_ID])
        db = FakeDatabase(users=FakeCollection([user]))
        self.assertEqual(await assigned_scope_ids(db, str(DOCTOR_ID), "doctor"), [PATIENT_ID])
        self.assertEqual(await assigned_scope_ids(db, str(DOCTOR_ID), "doctor", extra_query={
            "$or": [{"is_active": True}, {"is_active": {"$exists": False}}]}), [PATIENT_ID])
        # extra_query 只叠加 legacy 分支：canonical 无 is_active 字段语义
        canonical = canonical_db(clinical=[clinical_patient(PATIENT_ID,
                                                            practitioners=[DOCTOR_ID])])
        self.assertEqual(await assigned_scope_ids(canonical, str(DOCTOR_ID), "doctor",
                                                  extra_query={"is_active": False}),
                         [PATIENT_ID])

    async def test_assigned_scope_ids_keeps_legacy_identity_ambiguity_guard(self):
        db = FakeDatabase(users=FakeCollection([
            legacy_user(PATIENT_ID, practitioners=[DOCTOR_ID]),
            legacy_user(PATIENT_ID, practitioners=[DOCTOR_ID])]))
        with self.assertRaises(LegacyPatientIdentityError):
            await assigned_scope_ids(db, str(DOCTOR_ID), "doctor")

    async def test_inactive_canonical_patient_is_denied_at_object_access(self):
        """canonical 停用患者：load/ensure 按 404 拒绝，对齐 legacy is_active=False 语义。"""
        db = canonical_db(clinical=[clinical_patient(PATIENT_ID, practitioners=[DOCTOR_ID],
                                                     status="inactive")])
        with self.assertRaises(PatientAccessError) as missing:
            await load_patient_doc(db, PATIENT_ID)
        self.assertEqual(missing.exception.status_code, 404)
        self.assertEqual(missing.exception.error_code, "PATIENT_NOT_FOUND")
        with self.assertRaises(PatientAccessError) as denied:
            await ensure_patient_access(db, PATIENT_ID, str(DOCTOR_ID), "doctor")
        self.assertEqual(denied.exception.status_code, 404)


class CanonicalNameSearchTests(unittest.IsolatedAsyncioTestCase):
    """canonical 姓名搜索：大小写不敏感、可在 assigned 范围内过滤。"""

    def repo(self, db):
        return ClinicalPatientRepository(db)

    async def test_name_search_is_case_insensitive_and_scope_aware(self):
        assigned = clinical_patient(PATIENT_ID, practitioners=[DOCTOR_ID], name="Zhang San")
        unassigned = clinical_patient(str(ObjectId()), practitioners=[], name="zhang san")
        inactive = clinical_patient(str(ObjectId()), practitioners=[DOCTOR_ID],
                                    name="Zhang San", status="inactive")
        other = clinical_patient(str(ObjectId()), practitioners=[DOCTOR_ID], name="Li Si")
        db = canonical_db(clinical=[assigned, unassigned, inactive, other])
        repo = self.repo(db)
        self.assertEqual(await repo.matching_name_ids("ZHANG san"),
                         {assigned["patient_id"], unassigned["patient_id"], inactive["patient_id"]})
        self.assertEqual(await repo.matching_name_ids("zhang SAN", operator_id=str(DOCTOR_ID),
                                                      operator_role="doctor"),
                         {assigned["patient_id"]})
        self.assertEqual(await repo.matching_name_ids("zhang", patient_ids=[PATIENT_ID]),
                         {assigned["patient_id"]})
        self.assertEqual(await repo.matching_name_ids("li"), {other["patient_id"]})
        self.assertEqual(await repo.matching_name_ids(" nobody "), set())

    async def test_name_search_requires_canonical_state(self):
        with self.assertRaises(PatientDomainError):
            await self.repo(FakeDatabase(users=FakeCollection())).matching_name_ids("zhang")
        db = FakeDatabase(state={"_id": STATE_ID, "mode": "migrating",
                                 "schema_version": SCHEMA_VERSION})
        with self.assertRaises(PatientDomainError):
            await self.repo(db).matching_name_ids("zhang")


class IndexDeclarationTests(unittest.IsolatedAsyncioTestCase):
    """索引声明：clinical_patients.name 与 devices.patient_id 普通辅助索引。"""

    class Recorder(FakeCollection):
        def __init__(self):
            super().__init__()
            self.created = []

        async def create_index(self, keys, **kwargs):
            normalized = tuple(keys) if isinstance(keys, list) else ((keys, 1),)
            self.created.append((kwargs.get("name"), normalized))
            return kwargs.get("name")

    def recorder_db(self, collections):
        db = FakeDatabase()
        db._collections = {name: IndexDeclarationTests.Recorder() for name in collections}
        db.list_collection_names = AsyncMock(return_value=list(collections))
        return db

    async def test_patient_scope_indexes_cover_devices_and_clinical_name(self):
        db = self.recorder_db({"devices", "clinical_patients"})
        self.assertTrue(await ensure_patient_scope_indexes(db))
        created = {name: {item[0] for item in collection.created}
                   for name, collection in db._collections.items()}
        self.assertIn("device_patient_query", created["devices"])
        self.assertIn("clinical_patient_name_query", created["clinical_patients"])

    async def test_absent_collections_are_skipped_without_creating_them(self):
        db = self.recorder_db({"messages"})
        self.assertTrue(await ensure_patient_scope_indexes(db))
        self.assertEqual(list(db._collections), ["messages"])

    async def test_index_failure_never_raises_for_auxiliary_indexes(self):
        db = self.recorder_db({"devices"})
        db._collections["devices"].create_index = AsyncMock(side_effect=PyMongoError("synthetic"))
        self.assertFalse(await ensure_patient_scope_indexes(db))

    async def test_patient_index_maintenance_declares_name_query_index(self):
        db = FakeDatabase()
        for name in ("patient_account_links", "clinical_patients"):
            db._collections[name] = IndexDeclarationTests.Recorder()
        await create_patient_indexes(db)
        created = db._collections["clinical_patients"].created
        self.assertIn(("clinical_patient_name_query", (("name", 1),)), created)


if __name__ == "__main__":
    unittest.main()
