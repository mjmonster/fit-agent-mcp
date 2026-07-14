"""CLI entry point for Server A: run the server, init/seed the DB, mint demo tokens."""

import argparse

from fitness_mcp.config import get_settings
from fitness_mcp.issuer import issue_token
from fitness_mcp.repository import Database


def _serve() -> None:
    from fitness_mcp.server import mcp

    settings = get_settings()
    Database(settings.db_path).init_db()
    mcp.settings.host = settings.host
    mcp.settings.port = settings.port
    mcp.run(transport="streamable-http")


def _init_db() -> None:
    settings = get_settings()
    Database(settings.db_path).init_db()
    print(f"initialized + seeded {settings.db_path}")


def _issue_token(sub: str, scopes: str) -> None:
    settings = get_settings()
    print(issue_token(settings.jwt_secret, sub=sub, scopes=scopes.split(",")))


def main() -> None:
    parser = argparse.ArgumentParser(prog="fitness-mcp")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("serve", help="Run the MCP server (streamable HTTP)")
    sub.add_parser("init-db", help="Create tables and seed synthetic users (idempotent)")

    issue = sub.add_parser("issue-token", help="Mint a scoped per-user JWT (demo issuer)")
    issue.add_argument("--sub", required=True, help="Synthetic subject, e.g. user_001")
    issue.add_argument("--scopes", required=True, help="Comma-separated scopes")

    args = parser.parse_args()
    if args.command == "serve":
        _serve()
    elif args.command == "init-db":
        _init_db()
    elif args.command == "issue-token":
        _issue_token(args.sub, args.scopes)
