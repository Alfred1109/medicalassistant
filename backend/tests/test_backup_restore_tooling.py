"""备份与恢复演练工具的单元测试（不依赖真实 mongodump / MongoDB）。

覆盖 scripts/backup_mongodb.py 与 scripts/verify_restore.py：
- mongodump 命令行组装（--gzip --archive、--oplog 开关）；
- 主机闸门：缺省拒绝非本机，--allow-remote 放行；
- 连接串掩码：mask_uri / mask_text 不泄露明文密码；
- backup main 全流程（打桩 subprocess.run 与 Mongo client）：
  归档路径落位、manifest 字段完整性、manifest 不含连接串明文、
  mongodump 失败时不产出 manifest；
- verify 对账逻辑（合成 manifest + 打桩 client）：计数/索引/库/集合/集合缺
  失、patient_domain_state 一致与漂移、多出集合只记信息不算失败；
- 对账只读：打桩集合收到任何写调用立即失败。

运行：DEBUG=false .venv/bin/python -m pytest tests/test_backup_restore_tooling.py -q
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.backup_mongodb import (
    MANIFEST_FORMAT,
    STATE_COLLECTION,
    build_command,
    check_host_allowed,
    connect_client,
    main as backup_main,
    mask_text,
    mask_uri,
)
from scripts.verify_restore import REPORT_FORMAT, verify_against_manifest

URI = "mongodb://alice:s3cret-pw@127.0.0.1:37021/rehab?replicaSet=rehab_rs&directConnection=true"


def _fake_indexes(names):
    return [{"name": name} for name in names]


class FakeCollection:
    def __init__(self, count=0, indexes=(), state_doc=None):
        self._count = count
        self._indexes = list(indexes)
        self._state_doc = state_doc

    def count_documents(self, query):
        assert query == {}
        return self._count

    def list_indexes(self):
        return _fake_indexes(self._indexes)

    def find_one(self, query):
        if self._state_doc is not None and query == {"_id": "clinical-patients-v1"}:
            return dict(self._state_doc)
        return None

    # 对账工具必须是只读的：任何写调用立即失败
    def insert_one(self, *a, **k):
        raise AssertionError("verify 工具不允许写库")

    def update_one(self, *a, **k):
        raise AssertionError("verify 工具不允许写库")

    def delete_many(self, *a, **k):
        raise AssertionError("verify 工具不允许写库")

    def drop(self, *a, **k):
        raise AssertionError("verify 工具不允许写库")


class FakeDatabase:
    def __init__(self, collections):
        self._collections = dict(collections)

    def list_collection_names(self):
        return sorted(self._collections)

    def __getitem__(self, name):
        return self._collections[name]


class FakeClient:
    def __init__(self, databases):
        self._databases = dict(databases)
        self.closed = False

    def list_database_names(self):
        return sorted(self._databases)

    def __getitem__(self, name):
        return self._databases[name]

    def close(self):
        self.closed = True


class FakeAdmin:
    def __init__(self, commands):
        self._commands = commands

    def command(self, name):
        return self._commands[name]


class BackupHarness(FakeClient):
    """backup_mongodb.snapshot_client 所需的 admin 通道打桩。"""

    def __init__(self, databases):
        super().__init__(databases)
        self.admin = FakeAdmin({
            "buildInfo": {"version": "7.0.16"},
            "hello": {"setName": "rehab_rs"},
        })


class CommandAssemblyTests(unittest.TestCase):
    def test_build_command_defaults(self):
        command = build_command(URI, Path("/tmp/out.archive.gz"))
        self.assertEqual(command[0], "mongodump")
        self.assertIn("--gzip", command)
        self.assertIn(f"--archive={Path('/tmp/out.archive.gz')}", command)
        self.assertIn(URI, command)
        self.assertNotIn("--oplog", command)

    def test_build_command_with_oplog(self):
        command = build_command(URI, Path("/tmp/out.archive.gz"), mongodump_bin="/usr/bin/mongodump", oplog=True)
        self.assertEqual(command[0], "/usr/bin/mongodump")
        self.assertIn("--oplog", command)

    def test_host_gate_blocks_remote_by_default(self):
        with self.assertRaises(SystemExit):
            check_host_allowed("mongodb://user:pw@10.1.2.3:27017", False)

    def test_host_gate_allows_localhost_and_remote_flag(self):
        check_host_allowed("mongodb://user:pw@localhost:27017", False)
        check_host_allowed(URI, False)  # 127.0.0.1 在白名单内
        check_host_allowed("mongodb://user:pw@10.1.2.3:27017", True)

    def test_mask_uri_hides_credentials(self):
        masked = mask_uri(URI)
        self.assertNotIn("s3cret-pw", masked)
        self.assertNotIn("alice", masked)
        self.assertIn("127.0.0.1:37021/rehab?replicaSet=rehab_rs", masked)

    def test_mask_text_masks_uri_inside_tool_output(self):
        text = "error connecting: mongodb://bob:hunter2@db.host:27017/?tls=1"
        masked = mask_text(text)
        self.assertNotIn("hunter2", masked)
        self.assertIn("***@db.host:27017/?tls=1", masked)


class BackupMainTests(unittest.TestCase):
    def _fake_client(self):
        return BackupHarness({
            "rehab_assistant": FakeDatabase({
                "users": FakeCollection(count=3, indexes=["_id_"]),
                "clinical_patients": FakeCollection(count=2, indexes=["_id_", "clinical_patient_id_unique"]),
                STATE_COLLECTION: FakeCollection(count=1,
                                                 state_doc={"_id": "clinical-patients-v1", "mode": "canonical"}),
            }),
            "admin": FakeDatabase({}),  # 系统库应被 manifest 排除
        })

    def test_main_writes_complete_manifest_without_leaking_uri(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)

            def fake_run(command, **kwargs):
                # 模拟 mongodump 产出归档文件（从命令行取 --archive 目标）
                archive_arg = next(item for item in command if item.startswith("--archive="))
                archive = Path(archive_arg.split("=", 1)[1])
                archive.write_bytes(b"fake archive bytes")
                self.assertEqual(command[1:3], ["--uri", URI])
                self.assertIn("--gzip", command)
                from subprocess import CompletedProcess
                return CompletedProcess(command, 0)

            with patch("scripts.backup_mongodb.subprocess.run", side_effect=fake_run), \
                    patch("scripts.backup_mongodb.connect_client", return_value=self._fake_client()) as fake_open:
                manifest = backup_main(["--uri", URI, "--output-dir", str(out_dir)])

            fake_open.assert_called_once_with(URI)
            manifest_files = list(out_dir.glob("*.manifest.json"))
            self.assertEqual(len(manifest_files), 1)
            manifest_file = manifest_files[0]
            self.assertEqual(json.loads(manifest_file.read_text(encoding="utf-8")), manifest)
            self.assertTrue((out_dir / manifest["archive_file"]).is_file())
            self.assertEqual(manifest["format"], MANIFEST_FORMAT)
            self.assertEqual(manifest["mongo_version"], "7.0.16")
            self.assertEqual(manifest["topology"], {"replica_set": "rehab_rs"})
            self.assertEqual(manifest["source_uri_masked"], mask_uri(URI))
            self.assertNotIn("s3cret-pw", json.dumps(manifest))
            self.assertTrue(manifest["archive_file"].endswith(".archive.gz"))
            self.assertEqual(manifest["archive_size_bytes"], len(b"fake archive bytes"))
            self.assertEqual(len(manifest["archive_sha256"]), 64)
            self.assertEqual(manifest["patient_domain_state"], {"present": True, "mode": "canonical"})
            self.assertNotIn("admin", manifest["databases"])
            rehab = manifest["databases"]["rehab_assistant"]["collections"]
            self.assertEqual(rehab["users"]["count"], 3)
            self.assertEqual(rehab["users"]["indexes"], ["_id_"])
            self.assertEqual(rehab["clinical_patients"]["indexes"],
                             ["_id_", "clinical_patient_id_unique"])

    def test_main_failure_leaves_no_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            from subprocess import CompletedProcess
            with patch("scripts.backup_mongodb.subprocess.run",
                       return_value=CompletedProcess(["mongodump"], 1, stderr="boom")), \
                    patch("scripts.backup_mongodb.connect_client") as fake_connect:
                with self.assertRaises(SystemExit):
                    backup_main(["--uri", URI, "--output-dir", tmp])
            self.assertEqual(list(Path(tmp).iterdir()), [])
            fake_connect.assert_not_called()

    def test_main_failure_removes_partial_archive(self):
        # 实测回归（2026-11-14 本机演练）：mongodump 中途失败（如源库断连）会
        # 留下半成品归档，不得残留——会被误当作可用备份。失败路径必须清理。
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)

            def fake_run(command, **kwargs):
                archive_arg = next(item for item in command if item.startswith("--archive="))
                Path(archive_arg.split("=", 1)[1]).write_bytes(b"partial archive")
                from subprocess import CompletedProcess
                return CompletedProcess(command, 1, stderr="network error mid-dump")

            with patch("scripts.backup_mongodb.subprocess.run", side_effect=fake_run), \
                    patch("scripts.backup_mongodb.connect_client") as fake_connect:
                with self.assertRaises(SystemExit):
                    backup_main(["--uri", URI, "--output-dir", str(out_dir)])
            self.assertEqual(list(out_dir.iterdir()), [])  # 半成品归档已被清理
            fake_connect.assert_not_called()

    def test_connect_client_signatures_untouched(self):
        # 打桩点存在且可被 patch（真实连接不在单测范围）
        self.assertTrue(callable(connect_client))


class VerifyTests(unittest.TestCase):
    def _manifest(self, state={"present": True, "mode": "canonical"}):
        return {
            "format": MANIFEST_FORMAT,
            "created_at": "2026-01-01T00:00:00+00:00",
            "databases": {
                "rehab_assistant": {"collections": {
                    "users": {"count": 3, "indexes": ["_id_", "user_email_unique"]},
                    "clinical_patients": {"count": 2, "indexes": ["_id_"]},
                }},
            },
            "patient_domain_state": state,
        }

    def _client(self, users_count=3, users_indexes=("_id_", "user_email_unique"),
                databases=("rehab_assistant",), state=True, mode="canonical",
                extra_collection=None):
        collections = {
            "users": FakeCollection(count=users_count, indexes=users_indexes),
            "clinical_patients": FakeCollection(count=2, indexes=["_id_"]),
        }
        if extra_collection:
            collections[extra_collection] = FakeCollection(count=1, indexes=["_id_"])
        if state:
            collections[STATE_COLLECTION] = FakeCollection(
                count=1, state_doc={"_id": "clinical-patients-v1", "mode": mode})
        return FakeClient({name: FakeDatabase(collections) for name in databases})

    def test_matching_manifest_reports_ok(self):
        report = verify_against_manifest(self._manifest(), self._client())
        self.assertTrue(report["ok"])
        self.assertEqual(report["differences"], [])
        self.assertEqual(report["format"], REPORT_FORMAT)
        self.assertEqual(report["checked"],
                         {"databases": 1, "collections": 2, "indexes": 3})

    def test_count_and_index_mismatches_are_reported(self):
        client = self._client(users_count=5, users_indexes=("_id_",))
        report = verify_against_manifest(self._manifest(), client)
        self.assertFalse(report["ok"])
        types = sorted((d["type"], d["collection"]) for d in report["differences"])
        self.assertEqual(types, [("count_mismatch", "users"), ("missing_index", "users")])
        count_diff = next(d for d in report["differences"] if d["type"] == "count_mismatch")
        self.assertEqual((count_diff["expected"], count_diff["actual"]), (3, 5))

    def test_missing_collection_and_database(self):
        # 整库缺失（rehab_assistant 不在恢复实例上）
        report = verify_against_manifest(self._manifest(), FakeClient({"other_db": FakeDatabase({})}))
        self.assertFalse(report["ok"])
        self.assertIn("missing_database", [d["type"] for d in report["differences"]])
        # 库在但集合缺失
        partial = FakeClient({"rehab_assistant": FakeDatabase({
            "users": FakeCollection(count=3, indexes=["_id_", "user_email_unique"])})})
        report = verify_against_manifest(self._manifest(), partial)
        self.assertFalse(report["ok"])
        missing = [d for d in report["differences"] if d["type"] == "missing_collection"]
        self.assertEqual([d["collection"] for d in missing], ["clinical_patients"])
        self.assertEqual(missing[0]["expected"], 2)

    def test_patient_domain_state_missing_after_restore(self):
        report = verify_against_manifest(self._manifest(), self._client(state=False))
        self.assertFalse(report["ok"])
        diff = next(d for d in report["differences"] if d["type"] == "patient_domain_state_mismatch")
        self.assertEqual(diff["expected"], {"present": True, "mode": "canonical"})
        self.assertEqual(diff["actual"], {"present": False, "mode": None})

    def test_patient_domain_state_mode_drift(self):
        report = verify_against_manifest(self._manifest(), self._client(mode="legacy"))
        self.assertFalse(report["ok"])
        self.assertTrue(any(d["type"] == "patient_domain_state_mismatch"
                            for d in report["differences"]))

    def test_extra_collection_is_informational_only(self):
        report = verify_against_manifest(self._manifest(),
                                         self._client(extra_collection="stale_leftover"))
        self.assertTrue(report["ok"])
        self.assertEqual(report["extra_collections"],
                         [{"database": "rehab_assistant", "collection": "stale_leftover"}])

    def test_state_absent_in_manifest_stays_absent(self):
        report = verify_against_manifest(self._manifest(state={"present": False, "mode": None}),
                                         self._client(state=False))
        self.assertTrue(report["ok"])
        self.assertEqual(report["differences"], [])

    def test_unsupported_manifest_format_fails_closed(self):
        report = verify_against_manifest({"format": "something-else"}, self._client())
        self.assertFalse(report["ok"])
        self.assertEqual(report["differences"][0]["type"], "unsupported_manifest_format")

    def test_verify_is_read_only(self):
        client = self._client()
        report = verify_against_manifest(self._manifest(), client)
        self.assertTrue(report["ok"])
        for database in client._databases.values():
            for collection in database._collections.values():
                # 触发写护栏：如果对账过程调用过写方法，上面早已 AssertionError
                with self.assertRaises(AssertionError):
                    collection.insert_one({"x": 1})


if __name__ == "__main__":
    unittest.main()
