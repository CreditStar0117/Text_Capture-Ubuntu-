"""Single-instance local socket server and stdlib-only client (design D3).

The client side (`send`, `acquire_lock`) uses only the standard library so that
`text-capture --capture` never pays for importing Qt. Whoever holds the lock file
is the one instance allowed to listen; the lock is released by the kernel when
that process exits, so a leftover socket file is always safe to replace.
"""

import fcntl
import os
import socket
import tempfile
from pathlib import Path

from . import APP_ID

COMMANDS = ("capture", "quit", "start")


def runtime_dir() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return Path(runtime)
    fallback = Path(tempfile.gettempdir()) / f"{APP_ID}-{os.getuid()}"
    fallback.mkdir(mode=0o700, exist_ok=True)
    return fallback


def socket_path() -> Path:
    return runtime_dir() / f"{APP_ID}.sock"


def lock_path() -> Path:
    return runtime_dir() / f"{APP_ID}.lock"


def send(command: str, timeout: float = 1.0) -> str | None:
    """Send one command to the running instance; return its reply, or None if none is listening."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(str(socket_path()))
            sock.sendall(command.encode() + b"\n")
            reply = sock.makefile("rb").readline()
    except OSError:
        return None
    return reply.decode(errors="replace").strip() or None


def acquire_lock() -> int | None:
    """Take the single-instance lock; return its fd (keep it open while running), or None if taken."""
    fd = os.open(lock_path(), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


def start_server(on_command):
    """Listen for commands; call `on_command(name)` for each. The caller must hold the lock."""
    from PyQt6.QtNetwork import QLocalServer

    path = socket_path()
    path.unlink(missing_ok=True)  # we hold the lock, so any existing socket file is stale
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen(str(path)):
        raise RuntimeError(f"cannot listen on {path}: {server.errorString()}")

    def handle(conn):
        if not conn.canReadLine():
            return
        command = bytes(conn.readLine()).decode(errors="replace").strip()
        known = command in COMMANDS
        conn.write(b"ok\n" if known else b"error unknown command\n")
        conn.flush()
        conn.disconnectFromServer()
        if known:
            on_command(command)

    def accept():
        while server.hasPendingConnections():
            conn = server.nextPendingConnection()
            conn.readyRead.connect(lambda conn=conn: handle(conn))
            conn.disconnected.connect(conn.deleteLater)
            handle(conn)

    server.newConnection.connect(accept)
    return server
