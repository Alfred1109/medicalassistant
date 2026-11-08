"""Actual TCP/WebSocket protocol closure used by the project launcher.

The server is a disposable synthetic app in a private directory, not Rehabman
or any real database. This catches missing WS dependencies that TestClient's
in-process ASGI transport cannot detect.
"""
import asyncio
import importlib.util
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

import websockets

SPEC = importlib.util.spec_from_file_location("rehab_ws_runtime", Path(__file__).resolve().parents[2] / "scripts/runtime.py")
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


FIXTURE = '''from fastapi import FastAPI, WebSocket
app = FastAPI()
@app.websocket("/ws/probe")
async def probe(socket: WebSocket):
    await socket.accept()
    value = await socket.receive_json()
    await socket.send_json({"echo": value})
    await socket.close(code=1000)
'''


class WebSocketRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_project_launch_command_performs_real_upgrade_and_json_exchange(self):
        runtime.verify_websocket_runtime(sys.executable)
        with tempfile.TemporaryDirectory(prefix="rehab-ws-runtime-") as directory:
            folder = Path(directory)
            (folder / "app").mkdir()
            (folder / "app/__init__.py").write_text("")
            (folder / "app/main.py").write_text(FIXTURE)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen()
                port = listener.getsockname()[1]
                with (folder / "server.log").open("wb") as log:
                    child = subprocess.Popen(runtime.backend_command(sys.executable, "127.0.0.1", port)
                        + ["--fd", str(listener.fileno())], cwd=folder, pass_fds=(listener.fileno(),),
                        stdin=subprocess.DEVNULL, stdout=log, stderr=log)
                    try:
                        deadline = time.monotonic() + 8
                        while True:
                            if child.poll() is not None:
                                self.fail("Synthetic Uvicorn failed: " + (folder / "server.log").read_text())
                            try:
                                async with websockets.connect(f"ws://127.0.0.1:{port}/ws/probe", open_timeout=1) as connection:
                                    await connection.send('{"probe":"synthetic"}')
                                    self.assertEqual(await connection.recv(), '{"echo":{"probe":"synthetic"}}')
                                    await connection.wait_closed()
                                    self.assertEqual(connection.close_code, 1000)
                                break
                            except (OSError, asyncio.TimeoutError):
                                if time.monotonic() >= deadline:
                                    self.fail("Synthetic WebSocket handshake did not become ready")
                                await asyncio.sleep(0.03)
                    finally:
                        child.terminate()
                        child.wait(timeout=5)

    def test_missing_protocol_dependency_fails_before_application_or_database_start(self):
        # Real child interpreter, with only the websockets import blocked; this
        # reproduces the partial environment that served HTTP but not WebSocket.
        with tempfile.TemporaryDirectory(prefix="rehab-ws-missing-") as directory:
            wrapper = Path(directory) / "python-without-websockets"
            wrapper.write_text("#!" + sys.executable + "\n" + '''import sys, importlib.abc
class BlockWebsockets(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "websockets" or fullname.startswith("websockets."):
            raise ModuleNotFoundError("synthetic missing websockets")
sys.meta_path.insert(0, BlockWebsockets())
exec(sys.argv[2])
''')
            wrapper.chmod(0o700)
            with self.assertRaisesRegex(runtime.RuntimeFailure, "WebSocket support"):
                runtime.verify_websocket_runtime(str(wrapper))
