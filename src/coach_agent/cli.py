"""CLI entry point for Server B: the chat interface.

The user brings a token minted by `fitness-mcp issue-token`; this process only
presents it. The live model (claude-haiku-4-5) needs ANTHROPIC_API_KEY.
"""

import argparse
import asyncio
import logging

from langchain_core.messages import HumanMessage
from langgraph.errors import GraphRecursionError

from coach_agent.config import get_settings
from coach_agent.graph import build_graph
from coach_agent.mcp_client import discover_tools

logger = logging.getLogger(__name__)

# Backstop for the in-graph MAX_TOOL_LOOPS cap: bound total super-steps so a
# wiring bug can't spin forever.
RECURSION_LIMIT = 25


async def _chat(token: str | None) -> None:
    from langchain_anthropic import ChatAnthropic  # imported here: needs ANTHROPIC_API_KEY

    settings = get_settings()
    bearer = token or settings.token
    if not bearer:
        raise SystemExit(
            "no user token — pass --token or set COACH_AGENT_TOKEN "
            "(mint one with: fitness-mcp issue-token --sub user_001 --scopes ...)"
        )

    try:
        tools = await discover_tools(settings.server_url, bearer)
    except Exception as e:
        logger.exception("tool discovery failed: %s", e)
        raise SystemExit(
            f"could not reach the fitness-mcp server at {settings.server_url}. "
            "Is it running (fitness-mcp serve), and is your token valid/unexpired?"
        ) from None

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
        # Per-turn boundary: one transient failure must not kill the session
        # or leak internals to the user; the history is preserved for retry.
        try:
            state = await graph.ainvoke(
                {"messages": [*messages, HumanMessage(text)]},
                config={"recursion_limit": RECURSION_LIMIT},
            )
            messages = state["messages"]
            print(f"coach> {messages[-1].content}")
        except GraphRecursionError:
            logger.warning("graph hit recursion limit on input: %r", text)
            print("coach> Sorry, I got stuck on that — could you rephrase?")
        except Exception as e:
            logger.exception("turn failed: %s", e)
            print("coach> Something went wrong on my end. Please try again.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="coach-agent")
    sub = parser.add_subparsers(dest="command", required=True)

    chat = sub.add_parser("chat", help="Talk to the coach (uses COACH_AGENT_TOKEN)")
    chat.add_argument(
        "--token",
        help="Per-user JWT (overrides COACH_AGENT_TOKEN). Prefer the env var — "
        "an argv token is visible in the process list and shell history.",
    )

    args = parser.parse_args()
    if args.command == "chat":
        if args.token:
            print(
                "warning: passing --token puts your JWT in the process list and shell "
                "history; prefer COACH_AGENT_TOKEN for anything but throwaway demos."
            )
        asyncio.run(_chat(args.token))
