"""The apply CLI verifies stopped service, process identities and empty ports."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("clinical_patient_maintenance_cli", ROOT / "backend/scripts/manage_clinical_patients.py")
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


class PatientMaintenanceGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        (self.project / "scripts").mkdir()
        shutil.copy2(ROOT / "scripts/runtime.py", self.project / "scripts/runtime.py")
        for name in ("start.sh", "stop.sh"):
            (self.project / name).write_text("#!/bin/sh\nexit 0\n")
        self.ports = []
        for _ in range(2):
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                self.ports.append(probe.getsockname()[1])
        self.values = {"ActiveState": "inactive", "MainPID": "0", "WorkingDirectory": str(self.project),
                       "ExecStart": str(self.project / "start.sh"), "ExecStop": str(self.project / "stop.sh")}

    def tearDown(self):
        self.temp.cleanup()

    def output(self, arguments, **kwargs):
        return self.values[arguments[-2].split("=", 1)[1]] + "\n"

    def guard(self):
        return CLI.stopped_unit_guard("synthetic-only.service", self.project, self.ports)

    def test_actual_empty_runtime_and_ports_with_stopped_unit_are_accepted(self):
        with patch.object(CLI.subprocess, "check_output", side_effect=self.output):
            receipt = self.guard()()
        self.assertTrue(receipt["application_stopped"])
        self.assertTrue(receipt["managed_processes_stopped"])
        self.assertFalse(receipt["unknown_external_writers_excluded"])

    def test_active_or_mismatched_unit_is_refused(self):
        for key, value in (("ActiveState", "active"), ("MainPID", "123"),
                           ("WorkingDirectory", "/wrong"), ("ExecStart", "/wrong/start.sh"),
                           ("ExecStop", "/wrong/stop.sh")):
            original = self.values[key]
            self.values[key] = value
            with self.subTest(key=key), patch.object(CLI.subprocess, "check_output", side_effect=self.output):
                with self.assertRaises(CLI.PatientDomainError):
                    self.guard()()
            self.values[key] = original

    def test_inactive_systemd_does_not_hide_an_actual_leftover_listener(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", self.ports[0]))
            listener.listen()
            with patch.object(CLI.subprocess, "check_output", side_effect=self.output):
                with self.assertRaises(CLI.PatientDomainError) as rejected:
                    self.guard()()
        self.assertEqual(rejected.exception.code, "APPLICATION_PORT_REMAINS_OCCUPIED")

    def test_inactive_systemd_does_not_hide_an_owned_application_process(self):
        token = "b" * 48
        child = subprocess.Popen(["sleep", "30"], start_new_session=True,
                                 env={**os.environ, "MEDICALASSISTANT_RUNTIME_TOKEN": token})
        try:
            fields = Path(f"/proc/{child.pid}/stat").read_text().rsplit(")", 1)[1].split()
            state = self.project / ".runtime"
            state.mkdir(mode=0o700)
            (state / "processes.json").write_text(json.dumps({"root": str(self.project), "processes": [
                {"pid": child.pid, "start": int(fields[19]), "token": token, "name": "synthetic"}]}))
            with patch.object(CLI.subprocess, "check_output", side_effect=self.output):
                with self.assertRaises(CLI.PatientDomainError) as rejected:
                    self.guard()()
            self.assertEqual(rejected.exception.code, "MANAGED_APPLICATION_PROCESS_REMAINS")
            self.assertIsNone(child.poll())  # the verifier never stops or signals anything
        finally:
            child.terminate()
            child.wait(timeout=5)

    def test_explicit_ports_are_mandatory(self):
        for ports in ([], [self.ports[0]], [80, 90], [True, 9000]):
            with self.subTest(ports=ports), self.assertRaises(CLI.PatientDomainError):
                CLI.stopped_unit_guard("synthetic-only", self.project, ports)
