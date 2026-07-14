"""Tier 2 (stub-behavioral, LLM-free, CI-gating): the full plumbing of Server B.

A deterministic StubChatModel replays scripted decisions through the REAL
LangGraph graph, REAL MCP client (runtime discovery + bearer header), and REAL
Server A subprocess. Proves the wiring — token attachment, discovery, the
router's no-tool branch, the agent<->ToolNode loop, the loop cap, and audit —
without any LLM. The stub RECORDS its inputs, so we assert on what actually
reached the model (bearer never does; respond receives tool data as text with
no tool_use blocks). Mirrors the offline-by-default convention of
mjmonster/llm-agent-evals.
"""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from coach_agent.graph import MAX_TOOL_LOOPS, build_graph
from coach_agent.mcp_client import discover_tools
from coach_agent.stub_model import StubChatModel
from fitness_mcp.audit import read_audit_log
from fitness_mcp.repository import Database

EXPECTED_TOOLS = {"get_profile", "log_meal", "log_workout", "log_weight", "get_progress"}


def _has_tool_blocks(messages) -> bool:
    """True if any message carries a tool_use (tool_calls) or is a tool_result."""
    return any(isinstance(m, ToolMessage) or getattr(m, "tool_calls", None) for m in messages)


async def test_tools_are_discovered_at_runtime_not_hardcoded(server, issue):
    tools = await discover_tools(server["url"], issue("user_001"))
    assert {t.name for t in tools} == EXPECTED_TOOLS


async def test_tool_path_end_to_end_with_bearer_and_audit(server, issue):
    """'log my lunch' -> router -> agent -> ToolNode(MCP) -> agent -> respond."""
    token = issue("user_001")
    tools = await discover_tools(server["url"], token)
    stub = StubChatModel(
        responses=[
            AIMessage(content="tools"),  # router verdict
            AIMessage(  # agent decides to call log_meal
                content="",
                tool_calls=[
                    {"name": "log_meal", "args": {"description": "two eggs"}, "id": "call_1"}
                ],
            ),
            AIMessage(content="Meal recorded."),  # agent after tool result: done
            AIMessage(content="Logged your lunch — nice work!"),  # respond
        ]
    )
    graph = build_graph(stub, tools)
    db = Database(server["db_path"])
    before = len(read_audit_log(db))

    state = await graph.ainvoke({"messages": [HumanMessage("log my lunch: two eggs")]})

    tool_messages = [m for m in state["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_messages) == 1
    assert '"logged": true' in str(tool_messages[0].content).lower()

    # The call really hit Server A as user_001 — the bearer rode the MCP request
    # and Server A derived identity from the token. This is the bearer-attachment proof.
    rows = read_audit_log(db)[before:]
    assert [(r["tool"], r["outcome"], r["subject"]) for r in rows] == [
        ("log_meal", "ok", "user_001")
    ]

    # H1 + M1: respond's input (the LAST model call) must carry NO tool_use/tool_result
    # blocks (an unbound model 400s on those) yet MUST contain the tool result as text —
    # proving respond is grounded on tool data, not on a scripted echo.
    respond_input = stub.calls[-1]
    assert not _has_tool_blocks(respond_input)
    assert '"logged": true' in str(respond_input).lower()

    # M1: the per-user JWT must never reach the model in any call.
    assert token not in str(stub.calls)


async def test_small_talk_routes_past_tools_entirely(server, issue):
    """The router's chat branch is structural: no tool can run, no audit row."""
    token = issue("user_001")
    tools = await discover_tools(server["url"], token)
    stub = StubChatModel(
        responses=[
            AIMessage(content="chat"),  # router verdict
            AIMessage(content="Hey! Ready to crush your goals today?"),  # respond
        ]
    )
    graph = build_graph(stub, tools)
    db = Database(server["db_path"])
    before = len(read_audit_log(db))

    state = await graph.ainvoke({"messages": [HumanMessage("hey, how are you?")]})

    assert not [m for m in state["messages"] if isinstance(m, ToolMessage)]
    assert len(read_audit_log(db)) == before  # Server A untouched
    assert state["messages"][-1].content  # but the user still got a reply
    assert token not in str(stub.calls)


async def test_tool_loop_is_capped_and_terminates_gracefully(server, issue):
    """A model that keeps requesting tools is bounded by MAX_TOOL_LOOPS and
    still ends at respond — no GraphRecursionError, no stub overrun."""
    tools = await discover_tools(server["url"], issue("user_001"))
    responses = [AIMessage(content="tools")]  # router
    responses += [  # agent keeps asking for a tool, every time
        AIMessage(content="", tool_calls=[{"name": "get_profile", "args": {}, "id": f"c{i}"}])
        for i in range(MAX_TOOL_LOOPS)
    ]
    responses += [AIMessage(content="Let's try a different approach.")]  # respond after cap
    stub = StubChatModel(responses=responses)
    graph = build_graph(stub, tools)

    state = await graph.ainvoke({"messages": [HumanMessage("do the thing")]})

    tool_messages = [m for m in state["messages"] if isinstance(m, ToolMessage)]
    assert 0 < len(tool_messages) <= MAX_TOOL_LOOPS  # bounded, not runaway
    assert state["messages"][-1].content == "Let's try a different approach."  # reached respond
