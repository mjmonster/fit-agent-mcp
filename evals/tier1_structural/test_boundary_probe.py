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

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from fitness_mcp.audit import read_audit_log
from fitness_mcp.repository import Database

# Seeded heights (repository._seed) — used to tell users' data apart.
HEIGHT_USER_001 = 178.0
HEIGHT_USER_002 = 165.0


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


async def test_bearer_subject_selects_the_data_not_anything_else(server, issue):
    result_1 = await _call(server["url"], issue("user_001"), "get_profile", {})
    result_2 = await _call(server["url"], issue("user_002"), "get_profile", {})
    assert not result_1.isError and not result_2.isError
    assert result_1.structuredContent["height_cm"] == HEIGHT_USER_001
    assert result_2.structuredContent["height_cm"] == HEIGHT_USER_002


async def test_smuggled_user_id_argument_cannot_reach_other_user(server, issue):
    """The confused-deputy attempt itself: pass user_id although no schema has it."""
    result = await _call(server["url"], issue("user_001"), "get_profile", {"user_id": "user_002"})
    if result.isError:
        # Rejected outright — and the error must not leak user_002's data.
        assert str(HEIGHT_USER_002) not in _text(result)
    else:
        # If the server tolerates unknown args, the subject must still win.
        assert result.structuredContent["height_cm"] == HEIGHT_USER_001


async def test_progress_is_scoped_to_bearer_subject(server, issue):
    poisoned_owner = await _call(server["url"], issue("user_001"), "get_progress", {})
    other = await _call(server["url"], issue("user_002"), "get_progress", {})
    own_meals = {m["description"] for m in poisoned_owner.structuredContent["recent_meals"]}
    other_meals = {m["description"] for m in other.structuredContent["recent_meals"]}
    assert own_meals and other_meals
    assert not own_meals & other_meals  # zero overlap between subjects


def _minimal_args(schema: dict) -> dict:
    """Synthesize the smallest valid arguments for a tool from its schema."""
    fillers = {"string": "x", "integer": 1, "number": 1.0, "boolean": True}
    properties = schema.get("properties") or {}
    return {
        name: fillers.get(properties.get(name, {}).get("type"), "x")
        for name in schema.get("required", [])
    }


async def test_every_tool_is_scope_gated(server, issue):
    """A zero-scope bearer must be denied by EVERY tool, discovered dynamically —
    a future tool that forgets the authz path fails this eval automatically."""
    headers = {"Authorization": f"Bearer {issue('user_001', scopes=[])}"}
    async with (
        create_mcp_http_client(headers=headers) as http_client,
        streamable_http_client(server["url"], http_client=http_client) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        tools = (await session.list_tools()).tools
        assert tools, "no tools discovered — gate check would be vacuous"
        for tool in tools:
            result = await session.call_tool(tool.name, _minimal_args(tool.inputSchema or {}))
            assert result.isError, f"tool '{tool.name}' ran without any scope"
            assert "scope" in _text(result), f"tool '{tool.name}' not denied by scope check"


async def test_token_without_write_scope_cannot_log(server, issue):
    read_only = issue("user_002", scopes=["read:profile"])
    result = await _call(server["url"], read_only, "log_meal", {"description": "should be denied"})
    assert result.isError
    assert "write:meal_log" in _text(result)


async def test_invalid_at_argument_rejected_with_actionable_message(server, issue):
    result = await _call(
        server["url"],
        issue("user_001"),
        "log_meal",
        {"description": "lunch", "at": "next tuesday"},
    )
    assert result.isError
    assert "ISO-8601" in _text(result)  # authored guidance, not a raw parser error


async def test_audit_rows_carry_the_token_subject_only(server, issue):
    db = Database(server["db_path"])
    before = len(read_audit_log(db))
    await _call(server["url"], issue("user_001"), "get_profile", {})
    await _call(server["url"], issue("user_001"), "log_weight", {"weight_kg": 81.7})
    rows = read_audit_log(db)
    assert len(rows) == before + 2  # exactly one row per tool call
    assert all(r["subject"] == "user_001" for r in rows[before:])
    assert all(r["outcome"] == "ok" for r in rows[before:])


async def test_denied_and_errored_calls_are_audited(server, issue):
    """An attacker probing scopes or triggering errors must leave a trace."""
    db = Database(server["db_path"])
    before = len(read_audit_log(db))
    read_only = issue("user_001", scopes=["read:profile", "read:progress"])
    await _call(server["url"], read_only, "log_meal", {"description": "should be denied"})
    await _call(server["url"], read_only, "get_progress", {"period": "99999d"})
    rows = read_audit_log(db)[before:]
    assert [r["outcome"] for r in rows] == ["denied", "error"]
    assert all(r["subject"] == "user_001" for r in rows)
