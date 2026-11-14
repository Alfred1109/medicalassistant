"""标签唯一性盘点工具（scripts/label_uniqueness_audit.py）与创建路径
11000 兜底的单元测试（无 URI，内存打桩，不依赖真实 MongoDB）。

覆盖：
- tags 集合同 (name, category) 键重复组检测（含 _id 清单）；
- 组键按索引语义归并：name 缺失与 null 同键互撞；
- 异常形状计数：missing / null / blank / unstripped / overlength；
- 软引用悬空：health_records / organizations 的 tags 条目不在标签
  字典 name 中计悬空，非字符串条目计 other_form；
- 空集合与不存在的集合全 0；分批游标边界每条文档恰好处理一次；
- 工具只读：打桩集合收到任何写调用立即失败；
- 主机闸门：缺省拒绝非 localhost 连接串；
- 创建路径 DuplicateKeyError(11000) 兜底：唯一索引建好后查重-插入
  竞态的并发重复转换为既有 TAG_EXISTS 语义（409，错误码不变）。

运行：DEBUG=false .venv/bin/python -m pytest tests/test_label_uniqueness_audit.py -q
"""
import asyncio
import unittest
from types import SimpleNamespace

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from app.directory.records import create_tag
from scripts.label_uniqueness_audit import (
    audit_database,
    check_host_allowed,
    normalize_group_key,
)


class FakeCursor:
    """最小化游标打桩：分批 to_list，逐批推进，耗尽后返回空列表。"""

    def __init__(self, docs):
        self._docs = list(docs)
        self._pos = 0

    async def to_list(self, length=None):
        if length is None:
            batch = self._docs[self._pos:]
            self._pos = len(self._docs)
            return batch
        batch = self._docs[self._pos:self._pos + length]
        self._pos += len(batch)
        return batch


class FakeCollection:
    """只读打桩集合：任何写调用立即失败，证明盘点工具绝不写库。"""

    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.find_queries = []
        self._fail_write = "label_uniqueness_audit 必须只读；收到写调用 %s"

    def find(self, query, projection=None, **options):
        self.find_queries.append(dict(query))

        def match(doc):
            for key, value in query.items():
                if doc.get(key) != value:
                    return False
            return True
        return FakeCursor([doc for doc in self.docs if match(doc)])

    def _reject(self, *args, **kwargs):
        raise AssertionError(self._fail_write)

    insert_one = insert_many = update_one = update_many = replace_one = _reject
    delete_one = delete_many = create_index = drop_index = _reject
    drop = aggregate = _reject


class FakeDatabase:
    def __init__(self, collections, name="rehabman-test"):
        self._collections = dict(collections)
        self.name = name

    def __getitem__(self, name):
        return self._collections.get(name, FakeCollection())


def run_audit(collections, **kwargs):
    return asyncio.run(audit_database(
        FakeDatabase(collections), batch_size=kwargs.pop("batch_size", 2),
        **kwargs))


class LabelUniquenessAuditTest(unittest.TestCase):
    def test_duplicate_groups_detected_with_ids(self):
        db = FakeDatabase({"tags": FakeCollection([
            {"_id": "t1", "name": "步行", "category": "康复"},
            {"_id": "t2", "name": "步行", "category": "康复"},
            {"_id": "t3", "name": "步行", "category": "宣教"},  # 不同键
            {"_id": "t4", "name": "拉伸", "category": "康复"},
        ])})
        report = run_audit({"tags": db._collections["tags"]})
        tags = report["tags"]
        self.assertEqual(tags["total_documents"], 4)
        self.assertEqual(tags["duplicate_key_groups"], 1)
        self.assertEqual(tags["duplicate_documents"], 2)
        self.assertEqual(tags["duplicate_examples"], [
            {"name": "步行", "category": "康复", "ids": ["t1", "t2"]}])
        self.assertFalse(tags["examples_truncated"])

    def test_missing_and_null_name_share_index_key_semantics(self):
        """缺失与 null 同视为 null 键（唯一索引语义），两者互撞成重复组。"""
        db = FakeDatabase({"tags": FakeCollection([
            {"_id": "t1", "category": "康复"},                    # name 缺失
            {"_id": "t2", "name": None, "category": "康复"},      # name null
            {"_id": "t3", "name": "步行", "category": "康复"},
        ])})
        report = run_audit({"tags": db._collections["tags"]})
        tags = report["tags"]
        self.assertEqual(tags["missing_name"], 1)
        self.assertEqual(tags["null_name"], 1)
        self.assertEqual(tags["duplicate_key_groups"], 1)
        self.assertEqual(tags["duplicate_examples"][0]["name"], "<missing>")
        self.assertEqual(tags["duplicate_examples"][0]["category"], "康复")

    def test_anomaly_shape_counters(self):
        db = FakeDatabase({"tags": FakeCollection([
            {"_id": "t1", "name": " 步行 ", "category": "康复"},   # 未 strip
            {"_id": "t2", "name": "   ", "category": "康复"},      # strip 后空白
            {"_id": "t3", "name": "x" * 41, "category": "康复"},   # 超长
            {"_id": "t4", "name": "正常", "category": "康复"},
        ])})
        report = run_audit({"tags": db._collections["tags"]}, batch_size=3)
        tags = report["tags"]
        # " 步行 " 与 "   " 均带首尾空白，都计 unstripped
        self.assertEqual(tags["unstripped"], 2)
        self.assertEqual(tags["blank_name"], 1)
        self.assertEqual(tags["overlength_name"], 1)
        self.assertEqual(tags["overlength_category"], 0)
        self.assertEqual(tags["missing_name"], 0)
        self.assertEqual(tags["total_documents"], 4)

    def test_soft_reference_dangling_names(self):
        db = FakeDatabase({
            "tags": FakeCollection([
                {"_id": "t1", "name": "步行", "category": "康复"},
                {"_id": "t2", "name": "拉伸", "category": "康复"},
            ]),
            "health_records": FakeCollection([
                {"_id": "h1", "tags": ["步行", "不存在", "拉伸"]},
                {"_id": "h2", "tags": ["不存在"]},                  # 重复悬空值去重记样本
                {"_id": "h3", "tags": []},                          # 空列表不计文档
                {"_id": "h4"},                                      # 字段缺失不计
            ]),
            "organizations": FakeCollection([
                {"_id": "o1", "tags": ["步行", 123]},               # 非字符串条目
            ]),
        })
        report = run_audit({
            "tags": db._collections["tags"],
            "health_records": db._collections["health_records"],
            "organizations": db._collections["organizations"]})
        health = report["references"]["health_records"]
        self.assertEqual(health["field"], "tags")
        self.assertEqual(health["documents_with_field"], 2)
        self.assertEqual(health["tag_entries"], 4)
        self.assertEqual(health["dangling_name"], 2)
        self.assertEqual(health["dangling_examples"], ["不存在"])
        orgs = report["references"]["organizations"]
        self.assertEqual(orgs["tag_entries"], 2)
        self.assertEqual(orgs["other_form_entries"], 1)
        self.assertEqual(orgs["dangling_name"], 0)

    def test_dangling_examples_truncation(self):
        names = [f"tag{i}" for i in range(5)]
        docs = [{"_id": "t", "name": "known", "category": "康复"}]
        db = FakeDatabase({
            "tags": FakeCollection(docs),
            "health_records": FakeCollection([
                {"_id": "h", "tags": names + ["unknown"]},
            ]),
        })
        report = run_audit({"tags": db._collections["tags"],
                            "health_records": db._collections["health_records"]},
                           max_examples=3)
        health = report["references"]["health_records"]
        self.assertEqual(health["dangling_name"], 6)  # tag0..tag4 + unknown 均不在字典
        self.assertEqual(len(health["dangling_examples"]), 3)
        self.assertTrue(health["examples_truncated"])

    def test_duplicate_examples_truncation(self):
        # 3 个重复键组超过 max_examples=2：样本截断且 truncated 置位
        docs = []
        for i, name in enumerate(("步行", "拉伸", "按摩")):
            docs.append({"_id": f"a{i}", "name": name, "category": "康复"})
            docs.append({"_id": f"b{i}", "name": name, "category": "康复"})
        db = FakeDatabase({"tags": FakeCollection(docs)})
        report = run_audit({"tags": db._collections["tags"]}, max_examples=2)
        tags = report["tags"]
        self.assertEqual(tags["duplicate_key_groups"], 3)
        self.assertEqual(tags["duplicate_documents"], 6)
        self.assertEqual(len(tags["duplicate_examples"]), 2)
        self.assertTrue(tags["examples_truncated"])

    def test_empty_and_absent_collections_all_zero(self):
        report = run_audit({"tags": FakeCollection([])})
        self.assertEqual(report["tags"]["total_documents"], 0)
        self.assertEqual(report["tags"]["duplicate_key_groups"], 0)
        self.assertEqual(report["references"]["health_records"]["dangling_name"], 0)
        self.assertEqual(report["references"]["organizations"]["documents_with_field"], 0)

    def test_batch_boundary_processes_every_document_once(self):
        total = 25  # batch_size=10 时越过整批边界，最后一批 5 条
        docs = [{"_id": f"t{i}", "name": "步行", "category": "康复"}
                for i in range(total)]
        db = FakeDatabase({"tags": FakeCollection(docs)})
        report = run_audit({"tags": db._collections["tags"]}, batch_size=10)
        self.assertEqual(report["tags"]["total_documents"], total)
        self.assertEqual(report["tags"]["duplicate_documents"], total)

    def test_audit_never_writes_and_uses_read_queries_only(self):
        collection = FakeCollection([
            {"_id": "t1", "name": "步行", "category": "康复"}])
        run_audit({"tags": collection})
        for query in collection.find_queries:
            self.assertNotIn("$set", query)
            self.assertNotIn("$unset", query)

    def test_host_gate_rejects_remote_by_default(self):
        check_host_allowed("mongodb://localhost:27017/x", False)
        check_host_allowed("mongodb://127.0.0.1:27017/x", False)
        with self.assertRaises(SystemExit):
            check_host_allowed("mongodb://prod-host:27017/x", False)
        check_host_allowed("mongodb://prod-host:27017/x", True)

    def test_normalize_group_key_treats_missing_and_null_equal(self):
        self.assertEqual(
            normalize_group_key({"category": "康复"}),
            normalize_group_key({"name": None, "category": "康复"}))
        self.assertNotEqual(
            normalize_group_key({"name": "步行", "category": "康复"}),
            normalize_group_key({"name": "步行", "category": "宣教"}))


class _RacyCollection:
    """查重-插入竞态打桩：find_one 恒返回 None（并发窗口内对方尚未落库），
    insert_one 撞唯一索引抛 DuplicateKeyError（11000）。"""

    def __init__(self):
        self.inserted = []

    async def find_one(self, query):
        return None

    async def insert_one(self, document):
        raise DuplicateKeyError(
            "E11000 duplicate key error collection: rehabman.tags "
            "index: uniq_tag_name_category dup key: { name: \"步行\", category: \"康复\" }")

    def with_options(self, *args, **kwargs):
        return self


class CreateTagDuplicateKeyFallbackTest(unittest.TestCase):
    def test_duplicate_key_error_converts_to_existing_409_semantics(self):
        db = SimpleNamespace(tags=_RacyCollection())
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(create_tag(db, "步行", "康复", ""))
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail, {"code": "TAG_EXISTS"})

    def test_index_absence_keeps_historic_behavior(self):
        """无唯一索引（打桩不抛 11000）时行为与历史一致：插入成功。"""
        collection = _PlainCollection()
        db = SimpleNamespace(tags=collection)
        created = asyncio.run(create_tag(db, "步行", "康复", ""))
        self.assertEqual(created["name"], "步行")
        self.assertEqual(created["category"], "康复")
        self.assertEqual(len(collection.docs), 1)


class _PlainCollection:
    """历史行为打桩：无唯一索引，查重未命中即插入成功。"""

    def __init__(self):
        self.docs = []

    async def find_one(self, query):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return doc
        return None

    async def insert_one(self, document):
        self.docs.append(document)


if __name__ == "__main__":
    unittest.main()
