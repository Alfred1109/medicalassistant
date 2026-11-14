"""patient_reference_audit 只读盘点工具的单元测试。

用内存打桩集合（参照 tests/test_migrate_legacy_collections.py 的 FakeCollection
模式，不依赖真实 MongoDB）验证：
- 双形态引用（ObjectId / 24 位 hex 字符串）正确归并到同一 identity key 计数；
- 悬空、歧义（同 key 多 users 文档）、字段缺失、null（devices 历史非患者绑定）；
- 空集合与不存在的集合全 0；
- 大集合分批：batch_size 边界下每条文档恰好被处理一次；
- users 患者：is_active 分布、同 key 多文档组清单、医护归属字段双形态/悬空/歧义；
- 工具只读：打桩集合收到任何写调用（insert/update/delete）立即失败；
- 主机闸门：缺省拒绝非 localhost 连接串。

运行：DEBUG=false .venv/bin/python -m pytest tests/test_patient_reference_audit.py -q
"""
import asyncio
import unittest

from bson import ObjectId

from scripts.patient_reference_audit import (
    check_host_allowed,
    classify_form,
    audit_database,
)

OID = "64a1b2c3d4e5f6a7b8c9d0e1"
OID2 = "64a1b2c3d4e5f6a7b8c9d0e2"
OID3 = "64a1b2c3d4e5f6a7b8c9d0e3"
NO_REF = "64a1b2c3d4e5f6a7b8c9d0ff"


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
        self._fail_write = ("patient_reference_audit 必须只读；收到写调用 %s")

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


def users_docs():
    return [
        {"_id": ObjectId(OID), "role": "patient", "is_active": True,
         "practitioners": [OID2], "health_managers": []},
        {"_id": OID, "role": "patient", "is_active": False},          # 同 key 字符串形态
        {"_id": ObjectId(OID2), "role": "doctor"},
        {"_id": ObjectId(OID3), "role": "patient", "is_active": True},
    ]


def run_audit(collections, **kwargs):
    return asyncio.run(audit_database(
        FakeDatabase(collections), batch_size=kwargs.pop("batch_size", 2),
        **kwargs))


class PatientReferenceAuditTest(unittest.TestCase):
    def test_dual_form_references_share_identity_key(self):
        db = FakeDatabase({
            "users": FakeCollection(users_docs()),
            "followup_records": FakeCollection([
                {"_id": ObjectId(), "patient_id": ObjectId(OID3)},
                {"_id": ObjectId(), "patient_id": OID3},   # 同 key 字符串形态
            ]),
        })
        report = run_audit({"users": db._collections["users"],
                            "followup_records": db._collections["followup_records"]})
        stats = report["collections"]["followup_records"]
        self.assertEqual(stats["total_documents"], 2)
        self.assertEqual(stats["objectid_form"], 1)
        self.assertEqual(stats["string_form"], 1)
        self.assertEqual(stats["dangling"], 0)
        self.assertEqual(stats["ambiguous"], 0)

    def test_dangling_reference_counted_with_examples(self):
        db = FakeDatabase({
            "users": FakeCollection(users_docs()),
            "quality_issues": FakeCollection([
                {"_id": ObjectId(), "patient_id": NO_REF},
                {"_id": ObjectId(), "patient_id": ObjectId(NO_REF)},
            ]),
        })
        report = run_audit({"users": db._collections["users"],
                            "quality_issues": db._collections["quality_issues"]})
        stats = report["collections"]["quality_issues"]
        self.assertEqual(stats["dangling"], 2)
        self.assertEqual(len(stats["dangling_examples"]), 1)  # 同 key 只记一条样本
        self.assertEqual(stats["dangling_examples"][0]["key"], NO_REF)

    def test_ambiguous_reference_when_key_hits_multiple_users(self):
        db = FakeDatabase({
            "users": FakeCollection(users_docs()),
            "health_records": FakeCollection([
                {"_id": ObjectId(), "patient_id": OID},   # OID 命中两个患者文档
                {"_id": ObjectId(), "patient_id": OID3},
            ]),
        })
        report = run_audit({"users": db._collections["users"],
                            "health_records": db._collections["health_records"]})
        stats = report["collections"]["health_records"]
        self.assertEqual(stats["ambiguous"], 1)
        self.assertEqual(stats["dangling"], 0)
        self.assertEqual(stats["ambiguous_examples"][0]["user_ids"], [OID, OID])

    def test_missing_null_and_other_forms(self):
        db = FakeDatabase({
            "users": FakeCollection(users_docs()),
            "devices": FakeCollection([
                {"_id": ObjectId()},                                   # 字段缺失
                {"_id": ObjectId(), "patient_id": None},               # 历史非患者绑定
                {"_id": ObjectId(), "patient_id": OID3},
                {"_id": ObjectId(), "patient_id": "not-a-patient-id"},  # 自由字符串
            ]),
            "patientmanager.daily_records": FakeCollection([
                {"_id": "legacy-string-id", "user_id": OID3},
            ]),
        })
        report = run_audit({"users": db._collections["users"],
                            "devices": db._collections["devices"],
                            "patientmanager.daily_records":
                                db._collections["patientmanager.daily_records"]})
        devices = report["collections"]["devices"]
        self.assertEqual(devices["missing"], 1)
        self.assertEqual(devices["null"], 1)
        self.assertEqual(devices["other_form"], 1)
        self.assertEqual(devices["string_form"], 1)
        # 自由字符串无法匹配任何 users 文档，按 identity_key 口径记悬空
        self.assertEqual(devices["dangling"], 1)
        daily = report["collections"]["patientmanager.daily_records"]
        self.assertEqual(daily["total_documents"], 1)
        self.assertEqual(daily["string_form"], 1)
        self.assertEqual(daily["dangling"], 0)

    def test_empty_and_absent_collections(self):
        report = run_audit({
            "users": FakeCollection(users_docs()),
            "rehab_plans": FakeCollection([]),
        })
        for name in ("rehab_plans", "followup_records", "external_patient_links"):
            stats = report["collections"][name]
            self.assertEqual(stats["total_documents"], 0)
            self.assertEqual(stats["missing"], 0)
            self.assertEqual(stats["dangling"], 0)
            self.assertEqual(stats["ambiguous"], 0)

    def test_batch_boundary_processes_every_document_once(self):
        total = 25  # batch_size=10 时越过整批边界，最后一批 5 条
        refs = [{"_id": ObjectId(), "patient_id": OID3} for _ in range(total)]
        db = FakeDatabase({
            "users": FakeCollection(users_docs()),
            "rehab_plans": FakeCollection(refs),
        })
        report = run_audit({"users": db._collections["users"],
                            "rehab_plans": db._collections["rehab_plans"]},
                           batch_size=10)
        stats = report["collections"]["rehab_plans"]
        self.assertEqual(stats["total_documents"], total)
        self.assertEqual(stats["dangling"], 0)
        self.assertEqual(stats["ambiguous"], 0)

    def test_users_patient_stats_and_attribution(self):
        db = FakeDatabase({"users": FakeCollection([
            {"_id": ObjectId(OID), "role": "patient", "is_active": True,
             "practitioners": [ObjectId(OID2)],        # 医护 ObjectId 形态
             "health_managers": [NO_REF]},             # 医护悬空
            {"_id": OID, "role": "patient", "is_active": False},  # 同 key 组
            {"_id": ObjectId(OID2), "role": "doctor"},
            {"_id": ObjectId(OID3), "role": "patient"},           # is_active 缺失
        ])})
        report = run_audit({"users": db._collections["users"]})
        patients = report["users_patients"]
        self.assertEqual(patients["total_patients"], 3)
        self.assertEqual(patients["is_active"],
                         {"true": 1, "false": 1, "missing": 1, "other": 0})
        self.assertEqual(len(patients["duplicate_identity_groups"]), 1)
        group = patients["duplicate_identity_groups"][0]
        self.assertEqual(group["key"], OID)
        self.assertEqual(group["count"], 2)
        self.assertEqual(sorted(group["user_ids"]), [OID, OID])
        practitioners = patients["attribution_fields"]["practitioners"]
        self.assertEqual(practitioners["entries"], 1)
        self.assertEqual(practitioners["objectid_form"], 1)
        self.assertEqual(practitioners["resolved_roles"], {"doctor": 1})
        managers = patients["attribution_fields"]["health_managers"]
        self.assertEqual(managers["dangling"], 1)
        self.assertEqual(managers["dangling_examples"][0]["key"], NO_REF)

    def test_audit_never_writes_and_uses_read_queries_only(self):
        collection = FakeCollection(users_docs())
        run_audit({"users": collection})
        for query in collection.find_queries:
            # 只允许读过滤条件；不应出现任何带投影外的修改意图查询
            self.assertNotIn("$set", query)
            self.assertNotIn("$unset", query)

    def test_host_gate_rejects_remote_by_default(self):
        check_host_allowed("mongodb://localhost:27017/x", False)
        check_host_allowed("mongodb://127.0.0.1:27017/x", False)
        with self.assertRaises(SystemExit):
            check_host_allowed("mongodb://prod-host:27017/x", False)
        check_host_allowed("mongodb://prod-host:27017/x", True)

    def test_classify_form(self):
        self.assertEqual(classify_form(ObjectId(OID)), "objectid")
        self.assertEqual(classify_form(OID), "string")
        self.assertEqual(classify_form("legacy-free-id"), "other")
        self.assertEqual(classify_form(None), "other")


if __name__ == "__main__":
    unittest.main()
