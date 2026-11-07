"""Isolated lifecycle tests; no application/database services are used."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("runtime", Path(__file__).with_name("runtime.py"))
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)

SERVER = r'''
from http.server import BaseHTTPRequestHandler, HTTPServer
import json, sys
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        healthy = sys.argv[2] == 'healthy'
        is_api = self.path == '/health'
        status = 200 if healthy or not is_api else 207
        body = (json.dumps({'status': 'healthy' if healthy else 'degraded',
                            'components': {'database': {'status': 'connected' if healthy else 'disconnected'}}})
                if is_api else '<html><body>isolated runtime test</body></html>')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json' if is_api else 'text/html')
        self.end_headers(); self.wfile.write(body.encode())
    def log_message(self, *args): pass
HTTPServer(('127.0.0.1', int(sys.argv[1])), Handler).serve_forever()
'''

HTML_ONLY_SERVER = SERVER.replace(
    "        healthy = sys.argv[2] == 'healthy'",
    """        if 'text/html' not in self.headers.get('Accept', ''):
            self.send_error(404, 'HTML navigation required')
            return
        healthy = sys.argv[2] == 'healthy'"""
)


def unused_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="medicalassistant-runtime-test-")
        self.root = Path(self.directory.name)
        (self.root / "backend").mkdir(); (self.root / "frontend").mkdir()
        (self.root / ".runtime").mkdir()
        self.patches = [patch.object(runtime, "ROOT", self.root),
                        patch.object(runtime, "STATE_DIR", self.root / ".runtime"),
                        patch.object(runtime, "STATE_FILE", self.root / ".runtime/processes.json")]
        for p in self.patches: p.start()
        self.children = []
        self.records = []

    def tearDown(self):
        for record in reversed(self.records):
            runtime.stop_owned(record, timeout=0.5)
        for child in self.children:
            try: child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.terminate(); child.wait(timeout=2)
        for p in reversed(self.patches): p.stop()
        self.directory.cleanup()

    def spawn(self, command):
        child, record = runtime.spawn("test", command, self.root, os.environ, self.root / "logs")
        self.children.append(child); self.records.append(record)
        return child, record

    def test_owned_group_lifecycle_preserves_unrelated_process(self):
        unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
        self.children.append(unrelated)
        child, record = self.spawn([sys.executable, "-c", "import time; time.sleep(30)"])
        runtime.stop_owned(record, timeout=1)
        child.wait(timeout=2)
        self.assertIsNone(unrelated.poll())

    def test_wrong_start_identity_and_token_never_signal(self):
        child, record = self.spawn([sys.executable, "-c", "import time; time.sleep(30)"])
        for forged in [dict(record, start=record["start"] - 1), dict(record, token="0" * 48)]:
            with self.assertRaises(runtime.RuntimeFailure): runtime.stop_owned(forged, timeout=0.1)
            self.assertIsNone(child.poll())

    def test_exit_between_stat_and_environ_is_not_an_unknown_process(self):
        child, record = self.spawn([sys.executable, "-c", "import time; time.sleep(30)"])
        real_token = runtime.process_token
        def exit_before_environ(pid):
            if pid == child.pid:
                child.terminate()
                child.wait(timeout=2)
            return real_token(pid)
        # The process really exits at the boundary between the two /proc reads.
        with patch.object(runtime, "process_token", side_effect=exit_before_environ):
            runtime.stop_owned(record, timeout=0.5)
        self.assertFalse(runtime.owned_group(record))

    def test_stop_continues_other_groups_and_retains_unverified_state(self):
        backend, back_record = self.spawn([sys.executable, "-c", "import time; time.sleep(30)"])
        frontend, front_record = self.spawn([sys.executable, "-c", "import time; time.sleep(30)"])
        back_record = dict(back_record, name="backend")
        unknown = dict(front_record, name="frontend", token="0" * 48)
        runtime.save_state([back_record, unknown])
        with self.assertRaises(runtime.RuntimeFailure): runtime.stop()
        backend.wait(timeout=2)
        self.assertIsNone(frontend.poll())
        self.assertEqual(runtime.read_state(), [unknown])
        # Once the unknown process has independently exited, a retry clears the
        # stale identity without signalling any replacement PID or other group.
        frontend.terminate(); frontend.wait(timeout=2)
        runtime.stop()
        self.assertEqual(runtime.read_state(), [])

    def test_orphaned_descendant_is_cleaned_by_verified_group(self):
        code = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); time.sleep(.3)"
        child, record = self.spawn([sys.executable, "-c", code])
        child.wait(timeout=2)
        self.assertTrue(runtime.owned_group(record))
        runtime.stop_owned(record, timeout=1)
        self.assertFalse(runtime.owned_group(record))

    def test_port_conflict_preserves_listener(self):
        with socket.create_server(("127.0.0.1", 0)) as listener:
            port = listener.getsockname()[1]
            with self.assertRaises(runtime.RuntimeFailure): runtime.ensure_port_free("127.0.0.1", port)
            self.assertEqual(listener.getsockname()[1], port)

    def test_http_rejects_database_degraded(self):
        port = unused_port()
        child, _ = self.spawn([sys.executable, "-c", SERVER, str(port), "degraded"])
        with self.assertRaises(runtime.RuntimeFailure):
            runtime.wait_http(child, f"http://127.0.0.1:{port}/health", 0.8, database=True)

    def test_frontend_probe_requests_html_navigation(self):
        port = unused_port()
        child, _ = self.spawn([sys.executable, "-c", HTML_ONLY_SERVER, str(port), "healthy"])
        url = f"http://127.0.0.1:{port}/"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        # Reproduce SPA dev-server behavior: a request without Accept is not a
        # navigation and must not receive the index document.
        deadline = time.monotonic() + 2
        while True:
            try:
                opener.open(url, timeout=0.3)
                self.fail("The fixture unexpectedly accepted a request without Accept")
            except urllib.error.HTTPError as exc:
                self.assertEqual(exc.code, 404)
                exc.close()
                break
            except urllib.error.URLError:
                if time.monotonic() >= deadline: raise
                time.sleep(0.02)
        runtime.wait_http(child, url, 0.8)

    def lifecycle(self, fail_frontend):
        back, front = unused_port(), unused_port()
        while front == back: front = unused_port()
        env = {"MEDICALASSISTANT_BACKEND_PORT": str(back),
               "MEDICALASSISTANT_FRONTEND_PORT": str(front),
               "MEDICALASSISTANT_START_TIMEOUT": "2", "MEDICALASSISTANT_HOST": "127.0.0.1"}
        original_spawn = runtime.spawn
        def fake_spawn(name, command, cwd, environment, log_dir):
            port = back if name == "backend" else front
            actual = ([sys.executable, "-c", "raise SystemExit(7)"] if fail_frontend and name == "frontend"
                      else [sys.executable, "-c", SERVER, str(port), "healthy"])
            child, record = original_spawn(name, actual, cwd, environment, log_dir)
            self.children.append(child); self.records.append(record)
            if name == "frontend":
                self.assertEqual(environment["VITE_BACKEND_TARGET"], f"http://127.0.0.1:{back}")
            return child, record
        with patch.dict(os.environ, env), patch.object(runtime, "preflight", return_value=(sys.executable, "node", "vite")), patch.object(runtime, "spawn", side_effect=fake_spawn):
            if fail_frontend:
                with self.assertRaises(runtime.RuntimeFailure): runtime.start()
                self.assertEqual(runtime.read_state(), [])
                self.assertTrue(all(not runtime.owned_group(r) for r in self.records))
            else:
                runtime.start()
                self.assertEqual(len(runtime.read_state()), 2)
                runtime.stop()
                runtime.stop()  # idempotent stop
                self.assertEqual(runtime.read_state(), [])
                self.assertTrue(all(not runtime.owned_group(r) for r in self.records))

    def test_successful_start_and_stop(self): self.lifecycle(False)

    def test_partial_start_failure_cleans_only_created_children(self): self.lifecycle(True)

    def test_concurrent_lifecycle_operation_is_rejected(self):
        with runtime.runtime_lock():
            with self.assertRaises(runtime.RuntimeFailure):
                with runtime.runtime_lock(): pass


if __name__ == "__main__": unittest.main()
