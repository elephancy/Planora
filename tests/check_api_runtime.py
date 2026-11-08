"""Exercise the production image with only its API dependencies installed.

Mount this file read-only into the built image and run it from /app. The
temporary API and SQLite files belong entirely to this disposable check.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


def check_runtime() -> None:
    assert importlib.util.find_spec("PyQt6") is None, "Desktop Qt must not be installed in the API image"
    sys.path.insert(0, str(Path.cwd()))
    from scripts.backup_planora import backup_database, restore_database
    from scripts.retention_planora import cleanup_database
    from utils.exporter import Document
    from utils.generator import generate_instance, instance_to_json

    assert Document is not None, "DOCX export dependency must remain available"
    with tempfile.TemporaryDirectory(prefix="planora-runtime-") as temporary:
        directory = Path(temporary)
        database = directory / "planora.sqlite3"
        os.environ["PLANORA_DB_PATH"] = str(database)
        from api import server

        assert server.ROOT_DIR == Path.cwd()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        environment = {
            **os.environ,
            "PLANORA_DB_PATH": str(database),
            "PLANORA_TRUST_DEV_HEADERS": "1",
            "PLANORA_PRODUCTION": "0",
        }
        process = subprocess.Popen(
            [sys.executable, "-m", "api.server", "--host", "127.0.0.1", "--port", str(port)],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        def request(path: str, payload: dict | None = None) -> dict:
            body = None if payload is None else json.dumps(payload).encode()
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}{path}",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=20) as response:  # nosec B310: fixture loopback only
                return json.load(response)

        try:
            deadline = time.monotonic() + 15
            while True:
                assert process.poll() is None, "API exited before readiness"
                try:
                    assert request("/ready")["ready"] is True
                    break
                except (urllib.error.URLError, ConnectionError):
                    if time.monotonic() >= deadline:
                        raise AssertionError("API did not become ready") from None
                    time.sleep(0.1)
            assert request("/health") == {"ok": True}
            instance = instance_to_json(generate_instance("small_demo", seed=7))
            solved = request("/solve", {
                "instance": instance,
                "options": {
                    "room_mode": "greedy", "use_objective": False,
                    "retry_without_objective": False, "time_limit_seconds": 8,
                    "workers": 1,
                },
            })
            assert solved["schedule"] and solved["hard_conflicts"] == []
            scored = request("/score", {"instance": instance, "schedule": solved["schedule"]})
            assert "soft_penalty" in scored
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        backup = backup_database(database, directory / "backups")
        restored = directory / "restored.sqlite3"
        restore_database(backup, restored)
        with sqlite3.connect(restored) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        cleanup_database(restored, dry_run=True)
    print("Planora Qt-free API imports, HTTP readiness/solve/score and SQLite backup/restore verified")


if __name__ == "__main__":
    check_runtime()
