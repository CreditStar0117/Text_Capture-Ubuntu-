import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from text_capture import ipc

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    return tmp_path


def pump_until(predicate, timeout=3.0):
    from PyQt6.QtCore import QCoreApplication

    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise TimeoutError
        QCoreApplication.processEvents()
        time.sleep(0.005)


def send_in_thread(command):
    result = {}
    thread = threading.Thread(target=lambda: result.setdefault("reply", ipc.send(command)))
    thread.start()
    return thread, result


def test_no_instance_running(runtime):
    assert ipc.send("capture") is None


def test_commands_are_forwarded(qapp, runtime):
    fd = ipc.acquire_lock()
    received = []
    server = ipc.start_server(received.append)
    try:
        for command in ("capture", "quit"):
            thread, result = send_in_thread(command)
            pump_until(lambda: not thread.is_alive())
            assert result["reply"] == "ok"
        pump_until(lambda: len(received) == 2)
        assert received == ["capture", "quit"]

        thread, result = send_in_thread("bogus")
        pump_until(lambda: not thread.is_alive())
        assert result["reply"].startswith("error")
        assert received == ["capture", "quit"]
    finally:
        server.close()
        os.close(fd)


def test_lock_is_exclusive(runtime):
    fd = ipc.acquire_lock()
    assert fd is not None
    assert ipc.acquire_lock() is None
    os.close(fd)
    second = ipc.acquire_lock()
    assert second is not None
    os.close(second)


def test_stale_socket_is_replaced(qapp, runtime):
    # A socket file left behind by a crashed instance: it exists, but nobody listens.
    dead = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    dead.bind(str(ipc.socket_path()))
    dead.close()
    assert ipc.socket_path().exists()
    assert ipc.send("start") is None

    fd = ipc.acquire_lock()
    received = []
    server = ipc.start_server(received.append)
    try:
        thread, result = send_in_thread("start")
        pump_until(lambda: not thread.is_alive())
        assert result["reply"] == "ok"
    finally:
        server.close()
        os.close(fd)


CONTENDER = """
import sys, time
from text_capture import ipc
start_at = float(sys.argv[1])
while time.time() < start_at:
    pass
fd = ipc.acquire_lock()
if fd is None:
    print("client", flush=True)
    sys.exit(0)
from PyQt6.QtCore import QCoreApplication, QTimer
app = QCoreApplication([])
server = ipc.start_server(lambda command: None)
print("server", flush=True)
QTimer.singleShot(1500, app.quit)
app.exec()
"""


def test_simultaneous_starts_leave_one_server(runtime):
    env = {**os.environ, "XDG_RUNTIME_DIR": str(runtime), "PYTHONPATH": str(ROOT)}
    start_at = str(time.time() + 0.7)
    procs = [
        subprocess.Popen([sys.executable, "-c", CONTENDER, start_at], env=env, stdout=subprocess.PIPE, text=True)
        for _ in range(2)
    ]
    first_lines = [p.stdout.readline().strip() for p in procs]
    assert sorted(first_lines) == ["client", "server"]
    assert ipc.send("start") == "ok"
    for p in procs:
        p.wait(timeout=10)
