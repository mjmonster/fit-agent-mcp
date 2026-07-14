"""Tier 2 (stub-behavioral, LLM-free, CI-gating): the full plumbing of Server B.

A deterministic StubChatModel replays scripted decisions through the REAL
LangGraph graph, REAL MCP client (runtime discovery + bearer header), and REAL
Server A subprocess. Proves the wiring — token attachment, discovery, the
router's no-tool branch, the agent<->ToolNode loop, audit — without any LLM.
Mirrors the offline-by-default convention of mjmonster/llm-agent-evals.
"""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from coach_agent.graph import build_graph
from coach_agent.mcp_client import discover_tools
from coach_agent.stub_model import StubChatModel
from fitness_mcp.audit import read_audit_log
from fitness_mcp.repository import Database

EXPECTED_TOOLS = {"get_profile", "log_meal", "log_workout", "log_weight", "get_progress"}


async def test_tools_are_discovered_at_runtime_not_hardcoded(server, issue):
    tools = await discover_tools(server["url"], issue("user_001"))
    assert {t.name for t in tools} == EXPECTED_TOOLS


async def test_tool_path_end_to_end_with_bearer_and_audit(server, issue):
    """'log my lunch' -> router -> agent -> ToolNode(MCP) -> agent -> respond."""
    tools = await discover_tools(server["url"], issue("user_001"))
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
            AIMessage(content="Logged your lunch: two eggs. Nice protein!"),  # respond
        ]
    )
    graph = build_graph(stub, tools)
    db = Database(server["db_path"])
    before = len(read_audit_log(db))

    state = await graph.ainvoke({"messages": [HumanMessage("log my lunch: two eggs")]})

    tool_messages = [m for m in state["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_messages) == 1
    # Adapter tool messages carry content blocks (list) — stringify to inspect.
    assert '"logged": true' in str(tool_messages[0].content).lower()
    assert "two eggs" in state["messages"][-1].content  # respond's final reply

    rows = read_audit_log(db)[before:]  # the call really hit Server A, as user_001
    assert [(r["tool"], r["outcome"], r["subject"]) for r in rows] == [
        ("log_meal", "ok", "user_001")
    ]


async def test_small_talk_routes_past_tools_entirely(server, issue):
    """The router's chat branch is structural: no tool can run, no audit row."""
    tools = await discover_tools(server["url"], issue("user_001"))
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
