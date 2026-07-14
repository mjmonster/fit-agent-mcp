"""CLI entry point for Server B: the chat interface.

The user brings a token minted by `fitness-mcp issue-token`; this process only
presents it. The live model (claude-haiku-4-5) needs ANTHROPIC_API_KEY.
"""

import argparse
import asyncio

from langchain_core.messages import HumanMessage

from coach_agent.config import get_settings
from coach_agent.graph import build_graph
from coach_agent.mcp_client import discover_tools


async def _chat(token: str | None) -> None:
    from langchain_anthropic import ChatAnthropic  # imported here: needs ANTHROPIC_API_KEY

    settings = get_settings()
    bearer = token or settings.token
    if not bearer:
        raise SystemExit(
            "no user token — pass --token or set COACH_AGENT_TOKEN "
            "(mint one with: fitness-mcp issue-token --sub user_001 --scopes ...)"
        )

    tools = await discover_tools(settings.server_url, bearer)
    print(f"discovered {len(tools)} tools from {settings.server_url}")
    graph = build_graph(ChatAnthropic(model=settings.model), tools)

    print("coach ready — type 'exit' to quit")
    messages: list = []
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text or text.lower() in {"exit", "quit"}:
            break
        state = await graph.ainvoke({"messages": [*messages, HumanMessage(text)]})
        messages = state["messages"]
        print(f"coach> {messages[-1].content}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="coach-agent")
    sub = parser.add_subparsers(dest="command", required=True)

    chat = sub.add_parser("chat", help="Talk to the coach (uses COACH_AGENT_TOKEN)")
    chat.add_argument("--token", help="Per-user JWT (overrides COACH_AGENT_TOKEN)")

    args = parser.parse_args()
    if args.command == "chat":
        asyncio.run(_chat(args.token))
