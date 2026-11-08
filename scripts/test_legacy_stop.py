"""Explicit legacy migration tests use only synthetic local listener processes."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("runtime_legacy_test", Path(__file__).with_name("runtime.py"))
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)

SERVER = """import socket,time
s=socket.socket();s.bind(('127.0.0.1',0));s.listen()
print(s.getsockname()[1],flush=True)
time.sleep(120)
"""


@unittest.skipUnless(hasattr(os, "pidfd_open"), "Linux pidfd required")
class LegacyStopTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="rehab-legacy-stop-test-")
        self.root = Path(self.directory.name)
        (self.root / "backend/app").mkdir(parents=True)
        (self.root / "backend/app/main.py").write_text("# synthetic fixture\n")
        (self.root / "frontend").mkdir()
        (self.root / "frontend/package.json").write_text("{}")
        self.patch = patch.object(runtime, "ROOT", self.root)
        self.patch.start()
        self.children = []
        self.receipt = self.root / "legacy.json"

    def tearDown(self):
        for child in self.children:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=3)
            child.stdout.close()
        self.patch.stop()
        self.directory.cleanup()

    def listener(self):
        child = subprocess.Popen([sys.executable, "-u", "-c", SERVER],
                                 cwd=self.root / "backend", stdout=subprocess.PIPE,
                                 text=True, start_new_session=True)
        self.children.append(child)
        self.assertTrue(child.stdout.readline().strip().isdigit())
        return child, runtime.legacy_process_identity(child.pid)

    def write(self, identities):
        self.receipt.write_text(json.dumps({"version": 1, "controller_root": str(self.root),
                                           "legacy_root": str(self.root), "processes": identities}))
        self.receipt.chmod(0o600)

    def test_dry_run_never_stops_and_confirm_is_one_time(self):
        child, identity = self.listener()
        self.write([identity])
        runtime.stop_legacy(self.receipt)
        self.assertIsNone(child.poll())
        self.assertFalse(Path(str(self.receipt) + ".used").exists())
        runtime.stop_legacy(self.receipt, confirm=True)
        child.wait(timeout=2)
        audit = json.loads(Path(str(self.receipt) + ".used").read_text())
        self.assertEqual(audit["status"], "stopped")
        with self.assertRaises(runtime.RuntimeFailure):
            runtime.stop_legacy(self.receipt, confirm=True)

    def test_every_target_is_checked_before_any_signal(self):
        first, first_identity = self.listener()
        second, second_identity = self.listener()
        second_identity["start_ticks"] += 1
        self.write([first_identity, second_identity])
        with self.assertRaises(runtime.RuntimeFailure):
            runtime.stop_legacy(self.receipt, confirm=True)
        self.assertIsNone(first.poll())
        self.assertIsNone(second.poll())
        self.assertFalse(Path(str(self.receipt) + ".used").exists())

    def test_identity_and_listener_mismatches_refuse_without_signaling(self):
        child, original = self.listener()
        replacements = {"start_ticks": original["start_ticks"] + 1,
                        "uid": os.geteuid() + 1, "cwd": str(self.root / "frontend"),
                        "exe": "/wrong/python", "cmdline": ["wrong"],
                        "listeners": [{"host": "127.0.0.1", "port": 1}]}
        for field, value in replacements.items():
            with self.subTest(field=field):
                self.write([{**original, field: value}])
                with self.assertRaises(runtime.RuntimeFailure):
                    runtime.stop_legacy(self.receipt, confirm=True)
                self.assertIsNone(child.poll())

    def test_receipt_is_private_and_bound_to_controller(self):
        child, identity = self.listener()
        self.write([identity])
        self.receipt.chmod(0o644)
        with self.assertRaises(runtime.RuntimeFailure):
            runtime.stop_legacy(self.receipt, confirm=True)
        self.write([identity])
        data = json.loads(self.receipt.read_text())
        data["controller_root"] = "/wrong/root"
        self.receipt.write_text(json.dumps(data))
        with self.assertRaises(runtime.RuntimeFailure):
            runtime.stop_legacy(self.receipt, confirm=True)
        self.assertIsNone(child.poll())

    def test_signal_uses_pidfd_and_never_process_group(self):
        child, identity = self.listener()
        self.write([identity])
        with patch.object(runtime.os, "killpg", side_effect=AssertionError("must not signal group")):
            runtime.stop_legacy(self.receipt, confirm=True)
        child.wait(timeout=2)

    def test_terminated_signal_timeout_is_audited_without_force_kill(self):
        code = SERVER.replace("import socket,time", "import socket,time,signal\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)")
        child = subprocess.Popen([sys.executable, "-u", "-c", code],
                                 cwd=self.root / "backend", stdout=subprocess.PIPE,
                                 text=True, start_new_session=True)
        self.children.append(child)
        child.stdout.readline()
        self.write([runtime.legacy_process_identity(child.pid)])
        try:
            with self.assertRaises(runtime.RuntimeFailure):
                runtime.stop_legacy(self.receipt, confirm=True, timeout=0.05)
            self.assertIsNone(child.poll())
            audit = json.loads(Path(str(self.receipt) + ".used").read_text())
            self.assertEqual(audit["status"], "incomplete")
            self.assertEqual(audit["pending_pids"], [child.pid])
        finally:
            child.kill()  # Only this test's known synthetic child is cleaned up.
            child.wait(timeout=2)


if __name__ == "__main__":
    unittest.main()
