"""Run one tier-3 case through the REAL graph and capture a RunResult.

This is the I/O half of the harness (graph invocation + audit read); the pure
scoring lives in harness.py. Exercised live (needs a real model) — not unit-tested.
"""

import time

from harness import Case, CaseResult, RunResult, evaluate
from langchain_core.messages import HumanMessage

from fitness_mcp.audit import read_audit_log
from fitness_mcp.repository import Database

_RECURSION_LIMIT = 25


def _text(content) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, dict):
            parts.append(str(block.get("text") or block.get("content") or ""))
        else:
            parts.append(str(block))
    return " ".join(p for p in parts if p)


def extract_tool_calls(messages) -> tuple[list[str], dict[str, dict]]:
    """Tool names (in call order) and the last args each tool was called with."""
    names: list[str] = []
    args: dict[str, dict] = {}
    for m in messages:
        for tc in getattr(m, "tool_calls", None) or []:
            names.append(tc["name"])
            args[tc["name"]] = tc.get("args", {})
    return names, args


def _sum_tokens(messages) -> tuple[int, int]:
    tin = tout = 0
    for m in messages:
        usage = getattr(m, "usage_metadata", None)
        if usage:
            tin += usage.get("input_tokens", 0) or 0
            tout += usage.get("output_tokens", 0) or 0
    return tin, tout


async def run_one(graph, case: Case, db: Database, subject: str) -> CaseResult:
    """Invoke the graph on the case input, capture what happened, and score it."""
    before = len(read_audit_log(db))
    start = time.perf_counter()
    try:
        state = await graph.ainvoke(
            {"messages": [HumanMessage(case.input)]},
            config={"recursion_limit": _RECURSION_LIMIT},
        )
    except Exception as e:  # a crashed run is a failed case, not a crashed suite
        run = RunResult([], {}, "", set(), (time.perf_counter() - start) * 1000, 0, 0)
        return CaseResult(case=case, run=run, failures=[f"run errored: {type(e).__name__}: {e}"])

    latency_ms = (time.perf_counter() - start) * 1000
    names, args = extract_tool_calls(state["messages"])
    audit_rows = read_audit_log(db)[before:]
    tin, tout = _sum_tokens(state["messages"])
    run = RunResult(
        tools_called=names,
        tool_args=args,
        output=_text(state["messages"][-1].content),
        audit_subjects={r["subject"] for r in audit_rows},
        latency_ms=latency_ms,
        input_tokens=tin,
        output_tokens=tout,
    )
    return evaluate(case, run)
