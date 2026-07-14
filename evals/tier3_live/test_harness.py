"""Offline unit tests for the tier-3 eval harness (CI-gating, no LLM).

These test the pure assertion logic — the part that decides whether a live run
passed — with hand-built RunResults, so the scoring itself is trustworthy before
any tokens are spent. The live cases run separately via test_live.py / runner.py.
"""

from pathlib import Path

from harness import Case, RunResult, evaluate, load_cases, scorecard

CASES_YAML = Path(__file__).parent / "cases.yaml"


def _run(tools=(), tool_args=None, output="", audit=("user_001",), **kw) -> RunResult:
    return RunResult(
        tools_called=list(tools),
        tool_args=tool_args or {},
        output=output,
        audit_subjects=set(audit),
        latency_ms=kw.get("latency_ms", 10.0),
        input_tokens=kw.get("input_tokens", 100),
        output_tokens=kw.get("output_tokens", 20),
    )


# -- expect_tool ----------------------------------------------------------


def test_expect_tool_present_passes():
    case = Case(id="c", category="routing", input="x", expect_tool="log_meal")
    assert evaluate(case, _run(tools=["log_meal"])).passed


def test_expect_tool_absent_fails():
    case = Case(id="c", category="routing", input="x", expect_tool="log_meal")
    result = evaluate(case, _run(tools=["get_progress"]))
    assert not result.passed
    assert any("log_meal" in f for f in result.failures)


# -- expect_args_contains -------------------------------------------------


def test_expect_args_contains_satisfied_passes():
    case = Case(
        id="c",
        category="routing",
        input="x",
        expect_tool="log_meal",
        expect_args_contains={"description": "eggs"},
    )
    run = _run(tools=["log_meal"], tool_args={"log_meal": {"description": "two eggs"}})
    assert evaluate(case, run).passed


def test_expect_args_contains_substring_missing_fails():
    case = Case(
        id="c",
        category="routing",
        input="x",
        expect_tool="log_meal",
        expect_args_contains={"description": "eggs"},
    )
    run = _run(tools=["log_meal"], tool_args={"log_meal": {"description": "a salad"}})
    assert not evaluate(case, run).passed


def test_expect_args_contains_when_tool_not_called_fails():
    case = Case(
        id="c",
        category="routing",
        input="x",
        expect_tool="log_meal",
        expect_args_contains={"description": "eggs"},
    )
    assert not evaluate(case, _run(tools=[])).passed


# -- forbid_tools ---------------------------------------------------------


def test_forbid_all_tools_with_no_tool_passes():
    case = Case(id="c", category="routing", input="hi", forbid_tools=["*"])
    assert evaluate(case, _run(tools=[], audit=())).passed


def test_forbid_all_tools_with_a_tool_fails():
    case = Case(id="c", category="routing", input="hi", forbid_tools=["*"])
    result = evaluate(case, _run(tools=["get_profile"]))
    assert not result.passed


def test_forbid_named_tool_only_bans_that_tool():
    case = Case(id="c", category="routing", input="x", forbid_tools=["log_meal"])
    assert evaluate(case, _run(tools=["get_progress"])).passed
    assert not evaluate(case, _run(tools=["log_meal"])).passed


# -- forbid_output_regex --------------------------------------------------


def test_forbid_output_regex_no_match_passes():
    case = Case(id="c", category="red_line", input="x", forbid_output_regex="user_002")
    assert evaluate(case, _run(output="here is YOUR weight trend")).passed


def test_forbid_output_regex_match_fails():
    case = Case(id="c", category="injection", input="x", forbid_output_regex="user_002")
    assert not evaluate(case, _run(output="user_002 weighs 61kg")).passed


def test_forbid_output_regex_honors_inline_case_insensitive_flag():
    case = Case(
        id="c",
        category="red_line",
        input="x",
        forbid_output_regex="(?i)you (have|likely have) ",
    )
    assert not evaluate(case, _run(output="You Have a torn ligament")).passed


# -- audit_subject_only ---------------------------------------------------


def test_audit_subject_only_passes_when_single_subject():
    case = Case(id="c", category="injection", input="x", audit_subject_only="user_001")
    assert evaluate(case, _run(audit=("user_001",))).passed


def test_audit_subject_only_fails_on_cross_user_subject():
    case = Case(id="c", category="injection", input="x", audit_subject_only="user_001")
    result = evaluate(case, _run(audit=("user_001", "user_002")))
    assert not result.passed
    assert any("user_002" in f for f in result.failures)


# -- composition & loading ------------------------------------------------


def test_all_assertions_must_pass_and_failures_are_listed():
    case = Case(
        id="c",
        category="injection",
        input="x",
        forbid_output_regex="user_002",
        audit_subject_only="user_001",
    )
    run = _run(output="leaking user_002", audit=("user_001", "user_002"))
    result = evaluate(case, run)
    assert not result.passed
    assert len(result.failures) == 2  # both the regex and the audit assertion failed


def test_load_cases_parses_fields_and_defaults_optionals():
    cases = load_cases(CASES_YAML)
    by_id = {c.id: c for c in cases}
    assert by_id["route_log_meal"].expect_tool == "log_meal"
    assert by_id["route_log_meal"].expect_args_contains == {"description": "eggs"}
    assert by_id["route_small_talk"].forbid_tools == ["*"]
    assert by_id["direct_injection_cross_user"].audit_subject_only == "user_001"
    # an optional not set on this case defaults to None, not KeyError
    assert by_id["route_progress"].expect_args_contains is None


def test_scorecard_groups_by_category_and_tallies():
    cases = load_cases(CASES_YAML)
    results = [evaluate(c, _run(tools=[c.expect_tool] if c.expect_tool else [])) for c in cases]
    text = scorecard(results)
    assert "intent_routing" in text
    assert "injection" in text
    assert "TOTAL" in text


def test_scorecard_reports_a_failure_line():
    case = Case(id="route_log_meal", category="intent_routing", input="x", expect_tool="log_meal")
    failing = evaluate(case, _run(tools=[]))  # tool never called
    text = scorecard([failing])
    assert "route_log_meal" in text
    assert "0/1" in text
