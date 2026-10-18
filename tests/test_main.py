import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from text_capture import ipc

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    return {**os.environ, "XDG_RUNTIME_DIR": str(tmp_path), "PYTHONPATH": str(ROOT)}


@pytest.fixture
def server(qapp, env):
    fd = ipc.acquire_lock()
    received = []
    srv = ipc.start_server(received.append)
    yield received
    srv.close()
    os.close(fd)


def run_pumping(args, env):
    """Run a client process while this process keeps serving Qt events; return (proc, seconds)."""
    from PyQt6.QtCore import QCoreApplication

    started = time.perf_counter()
    proc = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    while proc.poll() is None:
        QCoreApplication.processEvents()
        time.sleep(0.001)
    return proc, time.perf_counter() - started


def test_client_path_does_not_import_qt(server, env):
    code = "import sys; from text_capture.__main__ import main; rc = main(['--capture']); print(rc, 'PyQt6' in sys.modules)"
    proc, _ = run_pumping([sys.executable, "-c", code], env)
    assert proc.stdout.read().strip() == "0 False"
    assert server == ["capture"]


def test_capture_is_fast_against_running_instance(server, env):
    timings = []
    for _ in range(5):
        proc, seconds = run_pumping([sys.executable, "-m", "text_capture", "--capture"], env)
        assert proc.returncode == 0
        timings.append(seconds)
    assert server == ["capture"] * 5
    assert min(timings) < 0.1, timings


def test_quit_when_not_running(env):
    code = "import sys; from text_capture.__main__ import main; rc = main(['--quit']); print(rc, 'PyQt6' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True).stdout
    assert out.splitlines() == ["Text Capture is not running.", "0 False"]


def test_quit_and_start_are_forwarded(server, env):
    for flag, command in (("--quit", "quit"), ("--background", "start"), (None, "start")):
        args = [sys.executable, "-m", "text_capture"] + ([flag] if flag else [])
        proc, _ = run_pumping(args, env)
        assert proc.returncode == 0
        assert server[-1] == command
