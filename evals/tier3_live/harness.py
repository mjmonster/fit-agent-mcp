"""Tier-3 eval harness — pure scoring logic (no LLM, no I/O).

Loads declarative YAML cases and decides pass/fail for a captured run. The
assertion vocabulary mirrors github.com/mjmonster/llm-agent-evals:
expect_tool, expect_args_contains, forbid_tools, forbid_output_regex — plus
audit_subject_only, this project's confused-deputy invariant.

Kept import-light and side-effect-free so it can gate CI via test_harness.py.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# claude-haiku-4-5 pricing, USD per token (see docs / claude-api model table).
_PRICE_IN = 1.00 / 1_000_000
_PRICE_OUT = 5.00 / 1_000_000


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    input: str
    expect_tool: str | None = None
    expect_args_contains: dict[str, str] | None = None
    forbid_tools: list[str] | None = None
    forbid_output_regex: str | None = None
    audit_subject_only: str | None = None


@dataclass
class RunResult:
    """What one live case run produced — the harness scores against this."""

    tools_called: list[str]
    tool_args: dict[str, dict[str, Any]]  # tool name -> last args it was called with
    output: str
    audit_subjects: set[str]
    latency_ms: float
    input_tokens: int
    output_tokens: int


@dataclass
class CaseResult:
    case: Case
    run: RunResult
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


def load_cases(path: str | Path) -> list[Case]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return [
        Case(
            id=item["id"],
            category=item["category"],
            input=item["input"],
            expect_tool=item.get("expect_tool"),
            expect_args_contains=item.get("expect_args_contains"),
            forbid_tools=item.get("forbid_tools"),
            forbid_output_regex=item.get("forbid_output_regex"),
            audit_subject_only=item.get("audit_subject_only"),
        )
        for item in raw
    ]


def evaluate(case: Case, run: RunResult) -> CaseResult:
    """Check every assertion the case declares; collect all failures."""
    failures: list[str] = []

    if case.expect_tool and case.expect_tool not in run.tools_called:
        failures.append(
            f"expected tool '{case.expect_tool}', got {run.tools_called or 'no tool call'}"
        )

    if case.expect_args_contains:
        args = run.tool_args.get(case.expect_tool or "", {})
        for key, needle in case.expect_args_contains.items():
            value = str(args.get(key, ""))
            if needle.lower() not in value.lower():
                failures.append(f"tool arg '{key}'={value!r} does not contain '{needle}'")

    if case.forbid_tools:
        if "*" in case.forbid_tools:
            if run.tools_called:
                failures.append(f"expected no tool call, got {run.tools_called}")
        else:
            banned = set(case.forbid_tools) & set(run.tools_called)
            if banned:
                failures.append(f"forbidden tool(s) called: {sorted(banned)}")

    if case.forbid_output_regex and re.search(case.forbid_output_regex, run.output):
        failures.append(f"output matched forbidden pattern /{case.forbid_output_regex}/")

    if case.audit_subject_only:
        leaked = run.audit_subjects - {case.audit_subject_only}
        if leaked:
            failures.append(
                f"audit shows non-authenticated subject(s) {sorted(leaked)} — "
                f"expected only '{case.audit_subject_only}'"
            )

    return CaseResult(case=case, run=run, failures=failures)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((pct / 100) * (len(ordered) - 1))))
    return ordered[idx]


def scorecard(results: list[CaseResult]) -> str:
    """Render a per-category pass tally plus latency / token / cost summary."""
    by_cat: dict[str, list[CaseResult]] = {}
    for r in results:
        by_cat.setdefault(r.case.category, []).append(r)

    lines = ["=== tier-3 live evals — claude-haiku-4-5 ===", ""]
    for cat in sorted(by_cat):
        group = by_cat[cat]
        n_pass = sum(r.passed for r in group)
        lines.append(f"{cat:<16} {n_pass}/{len(group)}")

    total_pass = sum(r.passed for r in results)
    total = len(results)
    pct = round(100 * total_pass / total) if total else 0
    lines += ["-" * 40, f"{'TOTAL':<16} {total_pass}/{total}   ({pct}%)"]

    latencies = [r.run.latency_ms for r in results]
    tok_in = sum(r.run.input_tokens for r in results)
    tok_out = sum(r.run.output_tokens for r in results)
    cost = tok_in * _PRICE_IN + tok_out * _PRICE_OUT
    lines.append(
        f"latency  p50 {_percentile(latencies, 50):.0f}ms  p95 {_percentile(latencies, 95):.0f}ms"
    )
    lines.append(f"tokens   in {tok_in:,}  out {tok_out:,}   est cost ${cost:.4f}")

    failed = [r for r in results if not r.passed]
    if failed:
        lines += ["", "FAILURES:"]
        for r in failed:
            lines.append(f"  {r.case.id}  0/1")
            for f in r.failures:
                lines.append(f"      - {f}")
    return "\n".join(lines)
