#!/usr/bin/env python3
"""Project-local Linux development lifecycle. Never manages MongoDB or packages.

Run ./start.sh --check for prerequisites, ./start.sh --status for process state,
and ./stop.sh to stop only processes carrying this runtime's recorded identity.
Configuration: MEDICALASSISTANT_PYTHON, MEDICALASSISTANT_HOST,
MEDICALASSISTANT_BACKEND_PORT, MEDICALASSISTANT_FRONTEND_PORT,
MEDICALASSISTANT_START_TIMEOUT. Database settings use backend Settings as usual.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import select
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TOKEN_NAME = "MEDICALASSISTANT_RUNTIME_TOKEN"
STATE_DIR = ROOT / ".runtime"
STATE_FILE = STATE_DIR / "processes.json"


class RuntimeFailure(Exception):
    pass


def process_info(pid: int):
    """Return Linux start identity and process group, excluding zombies."""
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        if fields[0] in {"Z", "X", "x"}:
            return None
        return {"start": int(fields[19]), "group": int(fields[2])}
    except (OSError, ValueError, IndexError):
        return None


def process_token(pid: int):
    try:
        prefix = (TOKEN_NAME + "=").encode()
        return next((v[len(prefix):].decode() for v in
                     Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
                     if v.startswith(prefix)), None)
    except (OSError, UnicodeError):
        return None


def owned_group(record: dict):
    """A recycled PID/group never qualifies without its unguessable run token.

    Surviving descendants are discoverable even after the leader has exited.
    Refuse a mixed/unreadable group instead of sending signals to unknown PIDs.
    """
    members = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        pid = int(entry.name)
        # stat and environ are separate kernel reads. A process can exit (or
        # become a zombie) between them, especially after SIGTERM. Re-read its
        # identity before treating missing environment as an unknown process.
        for attempt in range(6):
            before = process_info(pid)
            if not before or before["group"] != record["pid"]:
                break
            token = process_token(pid)
            after = process_info(pid)
            if not after or after["group"] != record["pid"]:
                break
            if before == after and token == record["token"]:
                if (after["start"] < record["start"] or
                        (pid == record["pid"] and after["start"] != record["start"])):
                    raise RuntimeFailure(f"Refusing to signal unverified process group {record['pid']}")
                members.append(pid)
                break
            if token is None and attempt < 5:
                # During exit the kernel may release environ before stat
                # reports a dead process. Give that transition bounded time;
                # a living unreadable/mismatched identity still fails closed.
                time.sleep(0.02)
                continue
            raise RuntimeFailure(f"Refusing to signal unverified process group {record['pid']}")
    return members


def stop_owned(record: dict, timeout=6.0):
    if not owned_group(record):
        return
    try:
        os.killpg(record["pid"], signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not owned_group(record):
            return
        time.sleep(0.1)
    if owned_group(record):
        try:
            os.killpg(record["pid"], signal.SIGKILL)
        except ProcessLookupError:
            return
    deadline = time.monotonic() + 2
    while owned_group(record):
        if time.monotonic() >= deadline:
            raise RuntimeFailure(f"Process group {record['pid']} did not stop")
        time.sleep(0.1)


def spawn(name, command, cwd, environment, log_dir):
    token = secrets.token_hex(24)
    env = dict(environment, **{TOKEN_NAME: token})
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{name}.log"
    with log_path.open("ab", buffering=0) as log:
        log.write(f"\n--- {time.strftime('%Y-%m-%dT%H:%M:%S%z')} start ---\n".encode())
        child = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=subprocess.STDOUT,
                                 start_new_session=True)
    info = process_info(child.pid)
    if not info:
        child.wait()
        raise RuntimeFailure(f"{name} exited during launch; see {log_path}")
    return child, {"name": name, "pid": child.pid, "start": info["start"],
                   "token": token, "log": str(log_path)}


def ensure_port_free(host, port):
    try:
        with socket.create_server((host, port)):
            pass
    except OSError as exc:
        raise RuntimeFailure(f"Port {host}:{port} is unavailable; no process was stopped") from exc


def wait_http(child, url, timeout, *, database=False):
    deadline = time.monotonic() + timeout
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(
        url, headers={"Accept": "application/json" if database else "text/html"})
    reason = "not ready"
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeFailure(f"Service exited with {child.returncode} while waiting for {url}")
        try:
            with opener.open(request, timeout=1) as response:
                body = response.read(1024 * 1024)
                if response.status != 200:
                    reason = f"HTTP {response.status}"
                elif database:
                    health = json.loads(body)
                    if (health.get("status") == "healthy" and
                            health.get("components", {}).get("database", {}).get("status") == "connected"):
                        if child.poll() is None:
                            return
                    reason = "database/API not healthy"
                elif "text/html" in response.headers.get("Content-Type", ""):
                    if child.poll() is None:
                        return
                else:
                    reason = "frontend response is not HTML"
        except urllib.error.HTTPError as exc:
            reason = f"HTTP {exc.code}"
            exc.close()
        except (OSError, ValueError, urllib.error.URLError) as exc:
            reason = type(exc).__name__
        time.sleep(0.2)
    raise RuntimeFailure(f"Timed out waiting for {url}: {reason}")


def backend_python():
    configured = os.environ.get("MEDICALASSISTANT_PYTHON")
    candidates = [Path(configured)] if configured else [
        ROOT / "backend/.venv/bin/python", ROOT / "backend/venv/bin/python",
        ROOT / ".venv/bin/python"]
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.absolute())
    raise RuntimeFailure("Project Python environment missing. Install dependencies first; "
                         "set MEDICALASSISTANT_PYTHON or prepare backend/venv.")


def verify_websocket_runtime(python):
    """Import the selected Uvicorn protocol, not merely the HTTP server package.

    Uvicorn's base installation can serve healthy HTTP while silently having no
    WebSocket implementation. requirements.txt pins the chosen websockets backend.
    """
    probe = "from uvicorn.protocols.websockets.websockets_impl import WebSocketProtocol; assert callable(WebSocketProtocol)"
    try:
        result = subprocess.run([python, "-c", probe], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeFailure("Backend WebSocket protocol validation could not finish") from exc
    if result.returncode:
        raise RuntimeFailure("Selected backend Python lacks compatible Uvicorn WebSocket support. "
                             "Install backend/requirements.txt into that environment before starting.")


def backend_command(python, host, port):
    # No automatic fallback to an HTTP-only Uvicorn installation.
    return [python, "-m", "uvicorn", "app.main:app", "--host", host,
            "--port", str(port), "--ws", "websockets"]


def preflight():
    if os.environ.get("DEBUG", "false").lower() not in {
            "1", "0", "true", "false", "yes", "no", "on", "off", "y", "n", "t", "f"}:
        raise RuntimeFailure("DEBUG must be a boolean value for the backend. "
                             "Use project-scoped DEBUG=false ./start.sh; global environment was not changed.")
    python = backend_python()
    node = shutil.which("node")
    vite = ROOT / "frontend/node_modules/vite/bin/vite.js"
    if not node or not vite.is_file():
        raise RuntimeFailure("Node.js/Vite dependencies missing. Prepare frontend dependencies first.")
    verify_websocket_runtime(python)
    # Use application configuration without importing app.main (which has side effects).
    # Fail closed on dependency, configuration or DB errors; never print credentials.
    probe = """
import asyncio
import fastapi, uvicorn, pydantic, motor, pymongo
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
async def main():
    if not settings.HEALTH_CHECK_INCLUDE_DB:
        raise RuntimeError('Database health reporting must be enabled')
    client = AsyncIOMotorClient(settings.MONGODB_URL, serverSelectionTimeoutMS=4000,
                               connectTimeoutMS=4000)
    try:
        await client[settings.MONGODB_DB_NAME].command('ping')
    finally:
        client.close()
asyncio.run(main())
"""
    try:
        result = subprocess.run([python, "-c", probe], cwd=ROOT / "backend",
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeFailure("Backend environment/database preflight could not finish") from exc
    if result.returncode:
        raise RuntimeFailure("Backend dependency/configuration/MongoDB preflight failed. "
                             "Verify the project environment and configured database. "
                             "No database service was started or stopped.")
    return python, node, str(vite)


def read_state():
    if not STATE_FILE.exists():
        return []
    try:
        data = json.loads(STATE_FILE.read_text())
        if data.get("root") != str(ROOT) or not isinstance(data.get("processes"), list):
            raise ValueError("root or process list mismatch")
        for record in data["processes"]:
            if (not isinstance(record["pid"], int) or record["pid"] <= 1 or
                    not isinstance(record["start"], int) or
                    not isinstance(record["token"], str) or len(record["token"]) != 48):
                raise ValueError("invalid process identity")
        return data["processes"]
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise RuntimeFailure(f"Invalid runtime state: {STATE_FILE}; refusing process operations") from exc


def save_state(records):
    temporary = STATE_DIR / "processes.json.tmp"
    temporary.write_text(json.dumps({"root": str(ROOT), "processes": records}, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(STATE_FILE)


def cleanup_records(records):
    """Attempt every owned group, retaining every failed identity for retry."""
    failures = []
    remaining = []
    for record in reversed(records):
        try:
            stop_owned(record)
        except (RuntimeFailure, OSError) as exc:
            remaining.append(record)
            failures.append(f"{record['name']}: {exc}")
    remaining.reverse()
    save_state(remaining)
    return failures


@contextmanager
def runtime_lock():
    STATE_DIR.mkdir(mode=0o700, exist_ok=True)
    with (STATE_DIR / "lifecycle.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeFailure("Another project start/stop operation is running") from exc
        yield


def settings():
    host = os.environ.get("MEDICALASSISTANT_HOST", "127.0.0.1")
    try:
        ports = [int(os.environ.get(key, default)) for key, default in [
            ("MEDICALASSISTANT_BACKEND_PORT", "5502"),
            ("MEDICALASSISTANT_FRONTEND_PORT", "5501")]]
        timeout = float(os.environ.get("MEDICALASSISTANT_START_TIMEOUT", "45"))
        if any(not 1 <= p <= 65535 for p in ports) or ports[0] == ports[1] or not 1 <= timeout <= 300:
            raise ValueError()
    except ValueError as exc:
        raise RuntimeFailure("Invalid runtime port or timeout configuration") from exc
    # Health requests always use loopback for wildcard listening addresses.
    local_host = "127.0.0.1" if host == "0.0.0.0" else host
    if ":" in host:
        raise RuntimeFailure("Use an IPv4 host or hostname for this development runtime")
    return host, local_host, *ports, timeout


def start(check_only=False):
    host, local, backend_port, frontend_port, timeout = settings()
    records = read_state()
    if any(owned_group(record) for record in records):
        raise RuntimeFailure("Project processes are already running. Use ./stop.sh before starting again.")
    ensure_port_free(host, backend_port)
    ensure_port_free(host, frontend_port)
    python, node, vite = preflight()
    if check_only:
        print("Prerequisites, database ping and port checks passed; no service started.")
        return
    started = []
    children = []
    try:
        env = os.environ.copy()
        child, record = spawn("backend", backend_command(python, host, backend_port),
                              ROOT / "backend", env, ROOT / "logs")
        started.append(record); children.append(child); save_state(started)
        wait_http(child, f"http://{local}:{backend_port}/health", timeout, database=True)
        # Browser API URLs belong to the public deployment configuration. A
        # server-loopback URL works locally but sends remote browsers to their
        # own machine. Only Vite's server-side proxy needs the backend listener.
        # Keep an explicit VITE_API_URL unchanged; otherwise Vite loads the
        # deployment prefix from its environment/.env files and uses same origin.
        frontend_env = dict(env, VITE_BACKEND_TARGET=f"http://{local}:{backend_port}")
        child, record = spawn("frontend", [node, vite, "--host", host, "--port", str(frontend_port),
            "--strictPort"], ROOT / "frontend", frontend_env, ROOT / "logs")
        started.append(record); children.append(child); save_state(started)
        wait_http(child, f"http://{local}:{frontend_port}/", timeout)
        print(f"Started: http://{local}:{frontend_port} (backend http://{local}:{backend_port})")
        print(f"Database is externally managed. Logs: {ROOT / 'logs'}")
    except BaseException as original:
        # Roll back only children created by this start attempt, using identity checks.
        failures = cleanup_records(started)
        for child in children:
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        if failures:
            raise RuntimeFailure("Startup failed; cleanup incomplete, state retained for ./stop.sh: "
                                 + "; ".join(failures)) from original
        raise


def stop():
    records = read_state()
    failures = cleanup_records(records)
    if failures:
        raise RuntimeFailure("Some process groups could not be verified/stopped; state retained for retry: "
                             + "; ".join(failures))
    print("Project processes stopped. External database services were not changed.")


def legacy_process_identity(pid):
    """Read an explicit PID identity and its owned TCP listeners; never infer targets."""
    info = process_info(pid)
    if info is None:
        raise RuntimeFailure(f"Legacy PID {pid} is not running")
    base = Path(f"/proc/{pid}")
    try:
        uid_line = next(line for line in (base / "status").read_text().splitlines()
                        if line.startswith("Uid:"))
        uids = [int(value) for value in uid_line.split()[1:]]
        if len(set(uids)) != 1:
            raise RuntimeFailure(f"Legacy PID {pid} has mixed UID credentials")
        inodes = set()
        for fd in (base / "fd").iterdir():
            try:
                target = os.readlink(fd)
            except FileNotFoundError:
                continue
            if target.startswith("socket:["):
                inodes.add(target[8:-1])
        listeners = []
        for filename, family in (("tcp", socket.AF_INET), ("tcp6", socket.AF_INET6)):
            for line in (base / "net" / filename).read_text().splitlines()[1:]:
                fields = line.split()
                if fields[3] != "0A" or fields[9] not in inodes:
                    continue
                address, port = fields[1].split(":")
                raw = bytes.fromhex(address)
                raw = (raw[::-1] if family == socket.AF_INET else
                       b"".join(raw[i:i + 4][::-1] for i in range(0, 16, 4)))
                listeners.append({"host": socket.inet_ntop(family, raw), "port": int(port, 16)})
        arguments = (base / "cmdline").read_bytes().split(b"\0")
        if arguments and arguments[-1] == b"":
            arguments.pop()
        identity = {
            "pid": pid, "start_ticks": info["start"], "uid": uids[0],
            "cwd": os.readlink(base / "cwd"), "exe": os.readlink(base / "exe"),
            "cmdline": [os.fsdecode(value) for value in arguments],
            "listeners": sorted(listeners, key=lambda item: (item["host"], item["port"])),
        }
    except (OSError, ValueError, StopIteration, IndexError) as exc:
        raise RuntimeFailure(f"Cannot verify legacy PID {pid}") from exc
    if process_info(pid) != info:
        raise RuntimeFailure(f"Legacy PID {pid} changed during inspection")
    return identity


def stop_legacy(receipt_path, *, confirm=False, timeout=6.0):
    """One-time explicit migration stop. Receipt validation alone sends no signals."""
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise RuntimeFailure("Legacy stop requires Linux pidfd support")
    path = Path(receipt_path).absolute()
    handles = []
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as source:
            metadata = os.fstat(source.fileno())
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
                    or stat.S_IMODE(metadata.st_mode) & 0o077):
                raise RuntimeFailure("Legacy receipt must be a private file owned by the current user")
            raw = source.read()
        receipt = json.loads(raw)
        if receipt.get("version") != 1 or receipt.get("controller_root") != str(ROOT):
            raise RuntimeFailure("Legacy receipt controller root/version mismatch")
        legacy_root = Path(receipt["legacy_root"])
        if (not legacy_root.is_absolute() or legacy_root.resolve() != legacy_root
                or not (legacy_root / "backend/app/main.py").is_file()
                or not (legacy_root / "frontend/package.json").is_file()):
            raise RuntimeFailure("Legacy receipt does not identify an existing project root")
        processes = receipt["processes"]
        if not isinstance(processes, list) or not processes or len(processes) > 2:
            raise RuntimeFailure("Legacy receipt requires one or two explicit application PIDs")
        seen = set()
        for expected in processes:
            pid = expected["pid"]
            if (type(pid) is not int or pid <= 1 or pid == os.getpid() or pid in seen
                    or expected["uid"] != os.geteuid()
                    or expected["cwd"] not in {str(legacy_root / "backend"), str(legacy_root / "frontend")}
                    or not expected["listeners"]):
                raise RuntimeFailure("Invalid explicit legacy process scope")
            seen.add(pid)
            handle = os.pidfd_open(pid)
            handles.append((handle, expected))
            if legacy_process_identity(pid) != expected:
                raise RuntimeFailure(f"Legacy PID {pid} does not match its receipt")
        marker = path.with_name(path.name + ".used")
        if marker.exists() or marker.is_symlink():
            raise RuntimeFailure("Legacy receipt has already been used")
        if not confirm:
            print(f"Validated {len(handles)} legacy PID identities; no processes stopped. "
                  "Use --confirm-legacy-stop with this receipt to stop them once.")
            return
        # Verify every identity again before any process receives a signal.
        for _, expected in handles:
            if legacy_process_identity(expected["pid"]) != expected:
                raise RuntimeFailure("Legacy process changed before stop; no signals sent")
        audit = {"receipt_sha256": hashlib.sha256(raw).hexdigest(), "controller_root": str(ROOT),
                 "legacy_root": str(legacy_root), "pids": sorted(seen), "started_at": time.time(),
                 "status": "stopping"}
        audit_fd = os.open(marker, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(audit_fd, "w+") as destination:
            json.dump(audit, destination); destination.flush(); os.fsync(destination.fileno())
            for handle, _ in handles:
                try:
                    signal.pidfd_send_signal(handle, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            deadline = time.monotonic() + timeout
            pending = []
            for handle, expected in handles:
                if not select.select([handle], [], [], max(0, deadline - time.monotonic()))[0]:
                    pending.append(expected["pid"])
            audit.update(finished_at=time.time(), status="stopped" if not pending else "incomplete", pending_pids=pending)
            destination.seek(0); destination.truncate()
            json.dump(audit, destination, indent=2)
            destination.write("\n"); destination.flush(); os.fsync(destination.fileno())
        if pending:
            raise RuntimeFailure(f"Legacy PIDs did not exit after SIGTERM: {pending}; no force kill attempted")
        print(f"Stopped {len(handles)} verified legacy application PIDs. Database services were not changed.")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise RuntimeFailure("Legacy receipt/process verification failed") from exc
    finally:
        for handle, _ in handles:
            os.close(handle)


def status():
    records = read_state()
    if not records:
        print("No managed project processes.")
        return
    for record in records:
        members = owned_group(record)
        print(f"{record['name']}: {'running' if members else 'stopped'} (recorded PID {record['pid']})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "stop"])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true")
    group.add_argument("--status", action="store_true")
    parser.add_argument("--legacy-receipt", type=Path,
                        help="Private explicit legacy PID receipt; validates only unless confirmed")
    parser.add_argument("--confirm-legacy-stop", action="store_true")
    args = parser.parse_args()
    if args.action == "stop" and args.check:
        parser.error("--check is only valid for start")
    if args.legacy_receipt and (args.action != "stop" or args.status or args.check):
        parser.error("--legacy-receipt is only valid for an explicit stop")
    if args.confirm_legacy_stop and not args.legacy_receipt:
        parser.error("--confirm-legacy-stop requires --legacy-receipt")
    if not Path("/proc/self/stat").exists():
        raise RuntimeFailure("This runtime requires Linux /proc for safe process identity checks")
    with runtime_lock():
        if args.legacy_receipt:
            stop_legacy(args.legacy_receipt, confirm=args.confirm_legacy_stop)
        elif args.status:
            status()
        elif args.action == "stop":
            stop()
        else:
            start(args.check)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeFailure, KeyboardInterrupt) as exc:
        print(f"Runtime error: {exc}", file=sys.stderr)
        sys.exit(1)
