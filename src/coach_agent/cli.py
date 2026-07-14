"""CLI entry point for Server B: the chat interface."""

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(prog="coach-agent")
    sub = parser.add_subparsers(dest="command", required=True)

    chat = sub.add_parser("chat", help="Talk to the coach (uses COACH_AGENT_TOKEN)")
    chat.add_argument("--token", help="Per-user JWT (overrides COACH_AGENT_TOKEN)")

    args = parser.parse_args()
    raise NotImplementedError(f"'{args.command}' is not implemented yet (scaffold)")
