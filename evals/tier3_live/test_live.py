"""Tier-3 live evals as pytest cases (marker: live; NEVER gates CI).

Runs the real coach agent (claude-haiku-4-5) against Server A, one assertion set
per case. Deselected by `pytest -m "not live"` (CI); skipped if no API key is set
so `pytest -m live` degrades cleanly. Reuses the server + issue fixtures from
evals/conftest.py.
"""

import os
from pathlib import Path

import pytest
from agent_runner import run_one
from harness import load_cases

from coach_agent.config import get_settings
from coach_agent.graph import build_graph
from coach_agent.mcp_client import discover_tools
from fitness_mcp.repository import Database

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="tier-3 needs ANTHROPIC_API_KEY"),
]

CASES = load_cases(Path(__file__).parent / "cases.yaml")


@pytest.fixture(scope="module")
async def coach(server, issue):
    from langchain_anthropic import ChatAnthropic

    tools = await discover_tools(server["url"], issue("user_001"))
    return build_graph(ChatAnthropic(model=get_settings().model), tools)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
async def test_live_case(case, coach, server):
    db = Database(server["db_path"])
    result = await run_one(coach, case, db, "user_001")
    assert result.passed, f"{case.id}: " + "; ".join(result.failures)
