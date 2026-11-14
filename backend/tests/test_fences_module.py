"""栅栏载体模块的内存 fake 测试。

真实并发正确性由 account_fences 唯一索引与 Mongo 事务（写冲突重试、整体
回滚）保证，由隔离副本集集成测试覆盖（对照 test_device_mutation_transactions
的既有惯例）；本文件只用内存 fake 验证调用序列、CAS 判定与异常路径，
不模拟并发交错与事务回滚。
"""
import asyncio
import unittest

from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from app.core.fences import (
    ACCOUNT_FENCES,
    AccountFenceStore,
    FenceInvalid,
    FenceMismatch,
    PatientFenceStore,
    create_account_fence_indexes,
    dual_bump,
    patient_fence_field,
)


class FakeFenceCollection:
    """只实现栅栏模块用到的三种操作的内存集合（等值匹配 + $inc）。

    session 一律记录不执行——fake 上没有事务，真实 session 语义由 Mongo 保证。
    """

    def __init__(self, name):
        self.name = name
        self.docs = []
        self.indexes = []
        self.calls = []
        self.sessions = []

    async def create_index(self, keys, name=None, unique=False, **kwargs):
        self.indexes.append({"keys": keys, "name": name, "unique": unique, "kwargs": kwargs})

    @staticmethod
    def _match(document, query):
        for key, expected in query.items():
            if document.get(key) != expected:
                return False
        return True

    @staticmethod
    def _apply_inc(document, update):
        for field, delta in update.get("$inc", {}).items():
            current = document.get(field, 0)
            if type(current) not in (int, float):
                # 模拟 Mongo $inc 打在非数值字段上的 TypeMismatch（code 14）
                error = PyMongoError("Cannot apply $inc to non-numeric value")
                error.code = 14
                raise error
            document[field] = current + delta

    async def find_one(self, query, projection=None, session=None, **kwargs):
        self.sessions.append(session)
        self.calls.append(("find_one", dict(query)))
        for document in self.docs:
            if self._match(document, query):
                return dict(document)
        return None

    async def find_one_and_update(self, query, update, return_document=False,
                                  upsert=False, session=None, **kwargs):
        self.sessions.append(session)
        self.calls.append(("find_one_and_update", dict(query), bool(upsert)))
        for document in self.docs:
            if self._match(document, query):
                self._apply_inc(document, update)
                return dict(document)
        if upsert:
            document = {key: value for key, value in query.items()
                        if not isinstance(value, dict)}
            self._apply_inc(document, update)
            self.docs.append(document)
            return dict(document)
        return None


class FakeDatabase(dict):
    def __getitem__(self, name):
        if name not in self:
            self[name] = FakeFenceCollection(name)
        return dict.__getitem__(self, name)


class AccountFenceStoreTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDatabase()
        self.store = AccountFenceStore(self.db)

    def test_bump_first_insert_then_increment(self):
        self.assertEqual(asyncio.run(self.store.bump("a1", "fill_use_revision")), 1)
        self.assertEqual(asyncio.run(self.store.bump("a1", "fill_use_revision")), 2)
        self.assertEqual(asyncio.run(self.store.bump("a1", "report_access_revision")), 1)
        self.assertEqual(asyncio.run(self.store.bump("a2", "fill_use_revision")), 1)
        rows = self.db[ACCOUNT_FENCES].docs
        self.assertEqual(
            sorted((row["account_id"], row["fence_name"], row["count"]) for row in rows),
            [("a1", "fill_use_revision", 2), ("a1", "report_access_revision", 1),
             ("a2", "fill_use_revision", 1)])
        # upsert 的插入文档只带定位键与计数，不污染 users 文档
        self.assertEqual(set(rows[0]), {"account_id", "fence_name", "count"})

    def test_check_passes_and_increments_when_expected_matches(self):
        asyncio.run(self.store.bump("a1", "fill_use_revision"))
        self.assertEqual(asyncio.run(self.store.check("a1", "fill_use_revision", 1)), 2)
        self.assertEqual(asyncio.run(self.store.check("a1", "fill_use_revision", 2)), 3)

    def test_check_expected_zero_passes_when_counter_absent(self):
        self.assertEqual(asyncio.run(self.store.check("a1", "fill_use_revision", 0)), 1)
        # 计数器已存在后，expected=0 必然失配（计数只会 >= 1）；
        # 而对尚无计数器的 a2，expected=0 仍视同首次递增
        self.assertEqual(asyncio.run(self.store.check("a2", "fill_use_revision", 0)), 1)
        with self.assertRaises(FenceMismatch) as raised:
            asyncio.run(self.store.check("a1", "fill_use_revision", 0))
        self.assertEqual(raised.exception.error_code, "FENCE_MISMATCH")

    def test_check_mismatch_rejects_without_writing(self):
        asyncio.run(self.store.bump("a1", "fill_use_revision"))
        collection = self.db[ACCOUNT_FENCES]
        before = [dict(row) for row in collection.docs]
        with self.assertRaises(FenceMismatch) as raised:
            asyncio.run(self.store.check("a1", "fill_use_revision", 5))
        self.assertEqual(raised.exception.error_code, "FENCE_MISMATCH")
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.details["carrier"], "account")
        self.assertEqual(collection.docs, before)

    def test_check_counter_disappeared_rejects(self):
        asyncio.run(self.store.bump("a1", "fill_use_revision"))
        self.db[ACCOUNT_FENCES].docs.clear()
        with self.assertRaises(FenceMismatch):
            asyncio.run(self.store.check("a1", "fill_use_revision", 1))

    def test_invalid_arguments_raise_fence_invalid(self):
        for fence_name in ("", "with.dot", "with$dollar", 123, None, "x" * 65):
            with self.assertRaises(FenceInvalid):
                asyncio.run(self.store.bump("a1", fence_name))
        with self.assertRaises(FenceInvalid):
            asyncio.run(self.store.bump("", "fill_use_revision"))
        with self.assertRaises(FenceInvalid):
            asyncio.run(self.store.check("a1", "fill_use_revision", "1"))
        with self.assertRaises(FenceInvalid):
            asyncio.run(self.store.check("a1", "fill_use_revision", -1))
        self.assertEqual(self.db[ACCOUNT_FENCES].docs, [])


class PatientFenceStoreTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDatabase()
        self.store = PatientFenceStore(self.db)
        self.db["clinical_patients"].docs = [
            {"_id": "p1", "patient_id": "p1", "status": "active",
             "practitioners": ["d1"], "health_managers": ["h1"]},
            {"_id": "p2", "patient_id": "p2", "status": "archived"},
        ]

    def test_bump_first_and_repeat_on_existing_patient(self):
        self.assertEqual(asyncio.run(self.store.bump("p1", "access")), 1)
        self.assertEqual(asyncio.run(self.store.bump("p1", "access")), 2)
        row = self.db["clinical_patients"].docs[0]
        self.assertEqual(row[patient_fence_field("access")], 2)
        # 栅栏字段按命名约定带下划线前缀，不进入业务投影
        self.assertEqual(patient_fence_field("access"), "_fence_access")

    def test_bump_missing_patient_rejects(self):
        with self.assertRaises(FenceMismatch) as raised:
            asyncio.run(self.store.bump("missing", "access"))
        self.assertEqual(raised.exception.details["carrier"], "patient")

    def test_bump_extra_query_mismatch_rejects(self):
        extra = {"status": "active", "practitioners": ["d1"]}
        self.assertEqual(asyncio.run(self.store.bump("p1", "access", extra_query=extra)), 1)
        with self.assertRaises(FenceMismatch):
            asyncio.run(self.store.bump("p1", "access",
                                        extra_query={"practitioners": ["other"]}))
        # 归属快照变化后原条件不再命中，栅栏不被递增
        self.assertEqual(self.db["clinical_patients"].docs[0][patient_fence_field("access")], 1)

    def test_check_passes_with_and_without_existing_field(self):
        # 字段尚未出现（等值 0 语义）：视同首次递增
        self.assertEqual(asyncio.run(self.store.check("p1", "access", 0)), 1)
        self.assertEqual(asyncio.run(self.store.check("p1", "access", 1)), 2)
        self.assertEqual(asyncio.run(self.store.check("p1", "access", 2)), 3)

    def test_check_mismatch_rejects_without_writing(self):
        asyncio.run(self.store.bump("p1", "access"))
        collection = self.db["clinical_patients"]
        before = [dict(row) for row in collection.docs]
        with self.assertRaises(FenceMismatch):
            asyncio.run(self.store.check("p1", "access", 5))
        with self.assertRaises(FenceMismatch):
            asyncio.run(self.store.check("p1", "access", 0))  # 字段已出现，0 失配
        self.assertEqual(collection.docs, before)

    def test_check_expected_zero_patient_missing_rejects(self):
        # 患者载体与账号载体不同：文档缺失即归属失效，expected=0 也拒绝
        with self.assertRaises(FenceMismatch):
            asyncio.run(self.store.check("missing", "access", 0))

    def test_extra_query_cannot_override_patient_id_locator(self):
        # T56/B6 防御：归属快照条件不得覆盖 patient_id 定位键（否则栅栏递增
        # 会打到别的患者文档上），必须 fail-closed 拒绝
        with self.assertRaises(FenceInvalid) as raised:
            asyncio.run(self.store.bump("p1", "access", extra_query={"patient_id": "p2"}))
        self.assertEqual(raised.exception.error_code, "FENCE_INVALID")
        self.assertEqual(self.db["clinical_patients"].docs[0].get("_fence_access"), None)
        with self.assertRaises(FenceInvalid):
            asyncio.run(self.store.check("p1", "access", 0,
                                         extra_query={"patient_id": "p2"}))

    def test_check_extra_query_snapshot_mismatch_rejects(self):
        asyncio.run(self.store.bump("p1", "report_access"))
        extra = {"status": "active", "practitioners": ["d1"], "health_managers": ["h1"]}
        self.assertEqual(asyncio.run(
            self.store.check("p1", "report_access", 1, extra_query=extra)), 2)
        changed = {**extra, "practitioners": ["d2"]}
        with self.assertRaises(FenceMismatch):
            asyncio.run(self.store.check("p1", "report_access", 2, extra_query=changed))

    def test_non_numeric_field_surfaces_as_fence_invalid(self):
        self.db["clinical_patients"].docs[0][patient_fence_field("access")] = "corrupt"
        with self.assertRaises(FenceInvalid) as raised:
            asyncio.run(self.store.bump("p1", "access"))
        self.assertEqual(raised.exception.error_code, "FENCE_INVALID")
        self.assertEqual(raised.exception.status_code, 503)


class DualBumpTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDatabase()
        self.accounts = AccountFenceStore(self.db)
        self.patients = PatientFenceStore(self.db)
        self.db["clinical_patients"].docs = [
            {"_id": "p1", "patient_id": "p1", "status": "active"}]

    def test_dual_bump_success_bumps_account_then_patient(self):
        result = asyncio.run(dual_bump(
            (self.accounts, "a1", "access"),
            (self.patients, "p1", "access"),
            session="session-marker"))
        self.assertEqual(result, (1, 1))
        collection = self.db["clinical_patients"]
        # 调用序列：先账号载体，后患者载体（同一 session 透传）
        account_calls = [call for call in collection.calls if call[1].get("patient_id") == "p1"]
        fence_calls = [call for call in self.db[ACCOUNT_FENCES].calls]
        self.assertEqual(fence_calls[0][1], {"account_id": "a1", "fence_name": "access"})
        self.assertEqual(account_calls[0][1].get("patient_id"), "p1")
        self.assertEqual(collection.sessions, ["session-marker"])
        self.assertEqual(self.db[ACCOUNT_FENCES].sessions, ["session-marker"])

    def test_dual_bump_with_expected_uses_check_hops(self):
        asyncio.run(self.accounts.bump("a1", "access"))
        asyncio.run(self.patients.bump("p1", "access"))
        result = asyncio.run(dual_bump(
            (self.accounts, "a1", "access", 1),
            (self.patients, "p1", "access", 1)))
        self.assertEqual(result, (2, 2))

    def test_dual_bump_patient_hop_failure_propagates_and_annotates(self):
        with self.assertRaises(FenceMismatch) as raised:
            asyncio.run(dual_bump(
                (self.accounts, "a1", "access"),
                (self.patients, "missing", "access")))
        self.assertEqual(raised.exception.details["hop"], "patient")
        # fake 无事务回滚：第一跳结果在 fake 上可见——真实回滚由 Mongo 事务保证，
        # 此断言只验证"第一跳已发生、第二跳失败即抛"的调用序列
        self.assertEqual(self.db[ACCOUNT_FENCES].docs[0]["count"], 1)
        self.assertEqual(self.db["clinical_patients"].docs[0].get("_fence_access"), None)

    def test_dual_bump_account_hop_failure_propagates_without_patient_call(self):
        asyncio.run(self.accounts.bump("a1", "access"))
        with self.assertRaises(FenceMismatch) as raised:
            asyncio.run(dual_bump(
                (self.accounts, "a1", "access", 7),
                (self.patients, "p1", "access")))
        self.assertEqual(raised.exception.details["hop"], "account")
        self.assertEqual(self.db["clinical_patients"].calls, [])

    def test_dual_bump_account_hop_fence_invalid_passes_through(self):
        # T56/B2：账号跳的 FenceInvalid（503，参数/载体无效）原样透传，
        # 不得被包装成 FenceMismatch（409 CAS miss）——数据损坏与授权变化
        # 必须可区分。错误详情不带 hop 标注。
        with self.assertRaises(FenceInvalid) as raised:
            asyncio.run(dual_bump(
                (self.accounts, "", "access"),
                (self.patients, "p1", "access")))
        self.assertEqual(raised.exception.error_code, "FENCE_INVALID")
        self.assertEqual(raised.exception.status_code, 503)
        self.assertNotIn("hop", raised.exception.details)
        self.assertEqual(self.db["clinical_patients"].calls, [])

    def test_dual_bump_patient_hop_fence_invalid_passes_through(self):
        # T56/B2：患者跳载体数据损坏（栅栏字段被打成非数值）→ FenceInvalid
        # 503 透传；账号跳已成功，真实回滚由 Mongo 事务保证（fake 上可见）
        self.db["clinical_patients"].docs[0][patient_fence_field("access")] = "corrupt"
        with self.assertRaises(FenceInvalid) as raised:
            asyncio.run(dual_bump(
                (self.accounts, "a1", "access"),
                (self.patients, "p1", "access")))
        self.assertEqual(raised.exception.error_code, "FENCE_INVALID")
        self.assertEqual(raised.exception.status_code, 503)
        self.assertNotIn("hop", raised.exception.details)
        self.assertNotIsInstance(raised.exception, FenceMismatch)

    def test_dual_bump_validates_hop_descriptors(self):
        with self.assertRaises(FenceInvalid):
            asyncio.run(dual_bump((self.accounts, "a1"), (self.patients, "p1", "access")))
        with self.assertRaises(FenceInvalid):
            asyncio.run(dual_bump(("not-a-store", "a1", "access"),
                                  (self.patients, "p1", "access")))
        with self.assertRaises(FenceInvalid):
            asyncio.run(dual_bump((self.accounts, "a1", "access", "1"),
                                  (self.patients, "p1", "access")))


class IndexDeclarationTests(unittest.TestCase):
    def test_index_declaration_shape(self):
        db = FakeDatabase()
        asyncio.run(create_account_fence_indexes(db))
        (index,) = db[ACCOUNT_FENCES].indexes
        self.assertEqual(index["keys"], [("account_id", 1), ("fence_name", 1)])
        self.assertEqual(index["name"], "account_fence_unique")
        self.assertTrue(index["unique"])

    def test_index_declaration_is_not_wired_into_stores(self):
        # AccountFenceStore/PatientFenceStore 构造与读写不触发任何 create_index
        db = FakeDatabase()
        db["clinical_patients"].docs = [{"_id": "p1", "patient_id": "p1"}]
        asyncio.run(AccountFenceStore(db).bump("a1", "access"))
        asyncio.run(PatientFenceStore(db).bump("p1", "access"))
        self.assertEqual(db[ACCOUNT_FENCES].indexes, [])
        self.assertEqual(db["clinical_patients"].indexes, [])


if __name__ == "__main__":
    unittest.main()
