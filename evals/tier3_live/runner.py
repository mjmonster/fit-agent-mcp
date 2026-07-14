"""Tier-3 live eval runner (on-demand; never gates CI).

Spins up the REAL Server A, connects the REAL LangGraph coach agent driven by
claude-haiku-4-5, runs every case in cases.yaml, and prints a per-category
scorecard. Mirrors github.com/mjmonster/llm-agent-evals' runner.py.

Usage:
    export ANTHROPIC_API_KEY=...          # the live model
    uv run python evals/tier3_live/runner.py
"""

import asyncio
import contextlib
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from agent_runner import run_one
from harness import load_cases, scorecard

from coach_agent.config import get_settings as coach_settings
from coach_agent.graph import build_graph
from coach_agent.mcp_client import discover_tools
from fitness_mcp.issuer import issue_token
from fitness_mcp.repository import Database

_SECRET = "tier3-runner-secret-at-least-32-bytes-long!"
_SCOPES = [
    "read:profile",
    "read:progress",
    "write:meal_log",
    "write:workout_log",
    "write:weight_log",
]
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextlib.contextmanager
def _serve(db_path: str):
    """Run `python -m fitness_mcp serve` (seeds the DB) on a free port."""
    port = _free_port()
    env = os.environ | {
        "FITNESS_MCP_JWT_SECRET": _SECRET,
        "FITNESS_MCP_DB_PATH": db_path,
        "FITNESS_MCP_HOST": "127.0.0.1",
        "FITNESS_MCP_PORT": str(port),
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "fitness_mcp", "serve"], env=env, cwd=str(_REPO_ROOT)
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"server exited early ({proc.returncode})")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                    break
            except OSError:
                time.sleep(0.25)
        else:
            raise RuntimeError("server did not start within 30s")
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


async def _run(db_path: str, url: str) -> int:
    from langchain_anthropic import ChatAnthropic

    token = issue_token(_SECRET, sub="user_001", scopes=_SCOPES)
    tools = await discover_tools(url, token)
    graph = build_graph(ChatAnthropic(model=coach_settings().model), tools)
    db = Database(db_path)

    results = []
    for case in load_cases(Path(__file__).parent / "cases.yaml"):
        print(f"running {case.id} ...", flush=True)
        results.append(await run_one(graph, case, db, "user_001"))

    print("\n" + scorecard(results))
    return 0 if all(r.passed for r in results) else 1


def main() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "ANTHROPIC_API_KEY is not set — tier-3 evals drive the live "
            "claude-haiku-4-5 model. Set it and re-run."
        )
    db_path = str(_REPO_ROOT / "tier3_evals.db")
    with contextlib.suppress(FileNotFoundError):
        os.remove(db_path)  # fresh seed each run
    with _serve(db_path) as url:
        exit_code = asyncio.run(_run(db_path, url))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
