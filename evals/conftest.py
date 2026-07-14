"""Shared eval fixtures: the REAL Server A as a subprocess + token minting.

Used by tier-1 (boundary probe, audit) and tier-2 (stub-behavioral) evals.
No LLM anywhere in these fixtures.
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from fitness_mcp.issuer import issue_token

SECRET = "eval-fixture-secret-at-least-32-bytes-long!"
ALL_SCOPES = [
    "read:profile",
    "read:progress",
    "write:meal_log",
    "write:workout_log",
    "write:weight_log",
]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def server(tmp_path_factory):
    """The REAL server: `python -m fitness_mcp serve` as a subprocess."""
    db_path = str(tmp_path_factory.mktemp("evals") / "evals.db")
    port = _free_port()
    env = os.environ | {
        "FITNESS_MCP_JWT_SECRET": SECRET,
        "FITNESS_MCP_DB_PATH": db_path,
        "FITNESS_MCP_HOST": "127.0.0.1",
        "FITNESS_MCP_PORT": str(port),
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "fitness_mcp", "serve"],
        env=env,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"server exited early with code {proc.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                    break
            except OSError:
                time.sleep(0.25)
        else:
            raise RuntimeError("server did not start listening within 30s")
        yield {"url": f"http://127.0.0.1:{port}/mcp", "db_path": db_path}
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture(scope="session")
def issue():
    """Callable minting a scoped JWT for a synthetic subject."""

    def _issue(sub: str, scopes: list[str] | None = None) -> str:
        return issue_token(SECRET, sub=sub, scopes=scopes if scopes is not None else ALL_SCOPES)

    return _issue
