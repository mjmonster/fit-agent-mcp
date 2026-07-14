"""Tier 1 (structural, LLM-free, CI-gating): the confused-deputy boundary probe.

Speaks RAW MCP over real streamable HTTP to the real server process — no agent,
no LLM. A maximally adversarial client tries every avenue the protocol offers
to reach another user's data and must fail structurally:

- no bearer            -> request rejected
- user_001 bearer      -> only user_001 data, ever
- smuggled user_id arg -> rejected (no such parameter exists)
- missing scope        -> tool call denied
- audit                -> every row's subject is the token's subject
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from fitness_mcp.audit import read_audit_log
from fitness_mcp.issuer import issue_token
from fitness_mcp.repository import Database

SECRET = "boundary-probe-secret-at-least-32-bytes-long"
ALL_SCOPES = [
    "read:profile",
    "read:progress",
    "write:meal_log",
    "write:workout_log",
    "write:weight_log",
]

# Seeded heights (repository._seed) — used to tell users' data apart.
HEIGHT_USER_001 = 178.0
HEIGHT_USER_002 = 165.0


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """The REAL server: `python -m fitness_mcp serve` as a subprocess."""
    db_path = str(tmp_path_factory.mktemp("boundary") / "probe.db")
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
        cwd=str(Path(__file__).resolve().parents[2]),
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


def _token(sub: str, scopes: list[str] | None = None) -> str:
    return issue_token(SECRET, sub=sub, scopes=scopes if scopes is not None else ALL_SCOPES)


async def _call(url: str, token: str | None, tool: str, args: dict):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with (
        create_mcp_http_client(headers=headers) as http_client,
        streamable_http_client(url, http_client=http_client) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        return await session.call_tool(tool, args)


def _text(result) -> str:
    return " ".join(c.text for c in result.content if hasattr(c, "text"))


async def test_request_without_bearer_is_rejected(server):
    with pytest.raises(BaseException):  # noqa: B017 — any failure is fine; success is the bug
        await _call(server["url"], None, "get_profile", {})


async def test_bearer_subject_selects_the_data_not_anything_else(server):
    result_1 = await _call(server["url"], _token("user_001"), "get_profile", {})
    result_2 = await _call(server["url"], _token("user_002"), "get_profile", {})
    assert not result_1.isError and not result_2.isError
    assert result_1.structuredContent["height_cm"] == HEIGHT_USER_001
    assert result_2.structuredContent["height_cm"] == HEIGHT_USER_002


async def test_smuggled_user_id_argument_cannot_reach_other_user(server):
    """The confused-deputy attempt itself: pass user_id although no schema has it."""
    result = await _call(server["url"], _token("user_001"), "get_profile", {"user_id": "user_002"})
    if result.isError:
        # Rejected outright — and the error must not leak user_002's data.
        assert str(HEIGHT_USER_002) not in _text(result)
    else:
        # If the server tolerates unknown args, the subject must still win.
        assert result.structuredContent["height_cm"] == HEIGHT_USER_001


async def test_progress_is_scoped_to_bearer_subject(server):
    poisoned_owner = await _call(server["url"], _token("user_001"), "get_progress", {})
    other = await _call(server["url"], _token("user_002"), "get_progress", {})
    own_meals = {m["description"] for m in poisoned_owner.structuredContent["recent_meals"]}
    other_meals = {m["description"] for m in other.structuredContent["recent_meals"]}
    assert own_meals and other_meals
    assert not own_meals & other_meals  # zero overlap between subjects


async def test_token_without_write_scope_cannot_log(server):
    read_only = _token("user_002", scopes=["read:profile"])
    result = await _call(server["url"], read_only, "log_meal", {"description": "should be denied"})
    assert result.isError
    assert "write:meal_log" in _text(result)


async def test_audit_rows_carry_the_token_subject_only(server):
    db = Database(server["db_path"])
    before = len(read_audit_log(db))
    await _call(server["url"], _token("user_001"), "get_profile", {})
    await _call(server["url"], _token("user_001"), "log_weight", {"weight_kg": 81.7})
    rows = read_audit_log(db)
    assert len(rows) == before + 2  # exactly one row per successful tool call
    assert all(r["subject"] == "user_001" for r in rows[before:])
