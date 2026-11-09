#!/usr/bin/env python3
"""Default read-only clinical-patient migration. No account or role creation.

Stop the independently managed application with its reviewed stop.sh first.
The tool rechecks its exact managed-unit identity before each migration boundary;
it cannot prove that an unknown external Mongo writer has been excluded. A full
database backup and separately reviewed maintenance procedure remain required.
"""
import argparse
import asyncio
import json
import importlib.util
import os
import stat
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient
from app.patients.migration import inspect_migration, migrate_legacy_patients, _write_private
from app.patients.repository import PatientDomainError


def stopped_unit_guard(unit, expected_directory, application_ports):
    directory = Path(expected_directory).resolve(strict=True)
    if not directory.is_dir() or not (directory / "start.sh").is_file() or not (directory / "stop.sh").is_file():
        raise PatientDomainError("INVALID_MAINTENANCE_APPLICATION")
    ports = set(application_ports or [])
    if len(ports) < 2 or any(type(port) is not int or not 1024 <= port <= 65535 for port in ports):
        raise PatientDomainError("EXPLICIT_APPLICATION_PORTS_REQUIRED")
    runtime_path = directory / "scripts/runtime.py"
    if runtime_path.is_symlink() or not runtime_path.is_file():
        raise PatientDomainError("INVALID_MAINTENANCE_APPLICATION")
    specification = importlib.util.spec_from_file_location("reviewed_patient_migration_runtime", runtime_path)
    runtime = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(runtime)
    def verify():
        values = {}
        for key in ("ActiveState", "MainPID", "WorkingDirectory", "ExecStart", "ExecStop"):
            values[key] = subprocess.check_output(
                ["systemctl", "show", unit, "--property=" + key, "--value"], text=True).strip()
        if (values["ActiveState"] not in {"inactive", "failed"} or values["MainPID"] != "0"
                or values["WorkingDirectory"] != str(directory)
                or str(directory / "start.sh") not in values["ExecStart"]
                or str(directory / "stop.sh") not in values["ExecStop"]):
            raise PatientDomainError("APPLICATION_WRITE_EXCLUSION_NOT_VERIFIED")
        if any(runtime.owned_group(record) for record in runtime.read_state()):
            raise PatientDomainError("MANAGED_APPLICATION_PROCESS_REMAINS")
        for port in ports:
            with socket.socket() as probe:
                probe.settimeout(0.25)
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    raise PatientDomainError("APPLICATION_PORT_REMAINS_OCCUPIED")
        return {"application_stopped": True, "guard_reference": "systemd:" + unit,
                "managed_processes_stopped": True, "application_ports_empty": True,
                "unknown_external_writers_excluded": False}
    return verify


def read_private_manifest(path):
    path = Path(path)
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise PatientDomainError("PRIVATE_MANIFEST_REQUIRED")
    information = path.stat()
    if (not stat.S_ISREG(information.st_mode) or information.st_uid != os.geteuid()
            or stat.S_IMODE(information.st_mode) & 0o077):
        raise PatientDomainError("PRIVATE_MANIFEST_REQUIRED")
    return json.loads(path.read_text())


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-output", type=Path, help="New private inspection manifest; never overwritten")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-manifest", type=Path)
    parser.add_argument("--expected-database-name")
    parser.add_argument("--backup-directory", type=Path)
    parser.add_argument("--reviewer")
    parser.add_argument("--evidence-reference")
    parser.add_argument("--managed-unit")
    parser.add_argument("--expected-working-directory")
    parser.add_argument("--application-port", type=int, action="append",
                        help="Each reviewed application listener (at least backend and frontend)")
    parser.add_argument("--maintenance-confirmed", action="store_true")
    args = parser.parse_args()
    # Existing business routes still use the legacy patient model. A domain
    # cutover before every route and authorization policy has been migrated
    # would create two conflicting sources of truth.
    if args.apply:
        parser.error("patient-domain cutover is disabled until business routes and authorization have been integrated and verified")
    from app.core.config import settings
    if args.apply and (not all((args.expected_manifest, args.expected_database_name,
                               args.backup_directory, args.reviewer, args.evidence_reference,
                               args.managed_unit, args.expected_working_directory, args.application_port))
                       or not args.maintenance_confirmed or args.manifest_output):
        parser.error("apply needs a reviewed manifest, exact database, private backup, reviewer/evidence, stopped managed application and maintenance confirmation")
    if args.apply and settings.MONGODB_DB_NAME != args.expected_database_name:
        parser.error("configured database does not match the reviewed database")
    client = AsyncIOMotorClient(settings.MONGODB_URL, serverSelectionTimeoutMS=5000)
    try:
        database = client[settings.MONGODB_DB_NAME]
        if args.apply:
            result = await migrate_legacy_patients(
                database, expected_manifest=read_private_manifest(args.expected_manifest),
                backup_directory=args.backup_directory, reviewer=args.reviewer,
                evidence_reference=args.evidence_reference,
                maintenance_guard=stopped_unit_guard(args.managed_unit, args.expected_working_directory,
                                                     args.application_port))
        else:
            result = await inspect_migration(database)
            if args.manifest_output:
                _write_private(args.manifest_output, json.dumps(result, sort_keys=True, indent=2).encode())
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except PatientDomainError as error:
        print(json.dumps({"error": error.code, "database_restore_supported": False}), file=sys.stderr)
        return 1
    except Exception as error:
        # Driver and validation messages can contain document values or private
        # configuration. Keep the CLI result bounded; inspect private receipts.
        print(json.dumps({"error": "PATIENT_MIGRATION_FAILED", "error_type": type(error).__name__,
                          "database_restore_supported": False}), file=sys.stderr)
        return 1
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
