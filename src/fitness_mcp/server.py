"""The FastMCP server for fitness-mcp (Server A).

THE SECURITY INVARIANT: no tool here accepts a user/subject identifier. The
subject is derived exclusively from the verified JWT bearer (get_access_token),
and every tool runs one path: verify -> scope check -> subject-scoped query ->
audit row (success, denied, AND errored calls all leave a trace).
The tier-1 structural evals enforce the schema side of this in CI.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

from fitness_mcp.audit import record_tool_call
from fitness_mcp.auth import JWTVerifier, check_scope
from fitness_mcp.config import TOKEN_AUDIENCE, TOKEN_ISSUER, get_settings
from fitness_mcp.errors import sanitized_tool
from fitness_mcp.repository import Database

from mcp.server.fastmcp import FastMCP  # isort: skip

mcp = FastMCP(
    "fitness-mcp",
    # The secret is resolved lazily at verification time, keeping this module
    # importable (e.g. by the schema evals) without runtime configuration.
    # Tokens are bound to TOKEN_AUDIENCE/TOKEN_ISSUER (RFC 8707) — see config.py.
    token_verifier=JWTVerifier(lambda: get_settings().jwt_secret),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(TOKEN_ISSUER),
        resource_server_url=AnyHttpUrl(TOKEN_AUDIENCE),
    ),
)


def _run_audited(
    tool: str,
    args: dict[str, Any],
    operation: Callable[[Database, str], tuple[Any, int]],
) -> Any:
    """The single execution path for every tool.

    Identity comes ONLY from the verified bearer token. Every call — success,
    authz denial, or error — leaves an audit row with the token's subject.
    """
    db = Database(get_settings().db_path)
    access = get_access_token()
    subject = access.subject if access and access.subject else "unauthenticated"
    try:
        if access is None or not access.subject:
            raise PermissionError("no verified bearer token on this request")
        check_scope(tool, access.scopes)
        result, rows_returned = operation(db, access.subject)
    except PermissionError:
        record_tool_call(db, subject, tool, args, rows_returned=0, outcome="denied")
        raise
    except Exception:
        record_tool_call(db, subject, tool, args, rows_returned=0, outcome="error")
        raise
    record_tool_call(db, subject, tool, args, rows_returned=rows_returned, outcome="ok")
    return result


def _parse_at(at: str | None) -> datetime | None:
    if not at:
        return None
    try:
        return datetime.fromisoformat(at)
    except ValueError:
        raise ValueError(
            "invalid 'at' — expected an ISO-8601 timestamp like '2026-07-14T12:30:00'"
        ) from None


@mcp.tool()
@sanitized_tool
def get_profile() -> dict[str, Any]:
    """Get the authenticated user's profile: height, latest weight, gender, goal."""
    return _run_audited("get_profile", {}, lambda db, subject: (db.get_profile(subject), 1))


@mcp.tool()
@sanitized_tool
def log_meal(
    description: str, calories: int | None = None, at: str | None = None
) -> dict[str, Any]:
    """Log a meal for the authenticated user. `at` is ISO-8601; defaults to now."""
    args = {"description": description, "calories": calories, "at": at}

    def op(db: Database, subject: str) -> tuple[dict[str, Any], int]:
        row_id = db.log_meal(subject, description, calories=calories, at=_parse_at(at))
        return {"logged": True, "id": row_id}, 1

    return _run_audited("log_meal", args, op)


@mcp.tool()
@sanitized_tool
def log_workout(
    kind: str, duration_min: int, notes: str | None = None, at: str | None = None
) -> dict[str, Any]:
    """Log a workout for the authenticated user. `at` is ISO-8601; defaults to now."""
    args = {"kind": kind, "duration_min": duration_min, "notes": notes, "at": at}

    def op(db: Database, subject: str) -> tuple[dict[str, Any], int]:
        row_id = db.log_workout(subject, kind, duration_min, notes=notes, at=_parse_at(at))
        return {"logged": True, "id": row_id}, 1

    return _run_audited("log_workout", args, op)


@mcp.tool()
@sanitized_tool
def log_weight(weight_kg: float, at: str | None = None) -> dict[str, Any]:
    """Record the authenticated user's weight. `at` is ISO-8601; defaults to now."""
    args = {"weight_kg": weight_kg, "at": at}

    def op(db: Database, subject: str) -> tuple[dict[str, Any], int]:
        row_id = db.log_weight(subject, weight_kg, at=_parse_at(at))
        return {"logged": True, "id": row_id}, 1

    return _run_audited("log_weight", args, op)


@mcp.tool()
@sanitized_tool
def get_progress(period: str = "7d") -> dict[str, Any]:
    """Progress for the authenticated user over a period like '7d' or '30d':
    weight trend, workout count, calorie summary, and recent meal descriptions."""

    def op(db: Database, subject: str) -> tuple[dict[str, Any], int]:
        progress = db.get_progress(subject, period)
        rows = (
            len(progress["recent_meals"])
            + progress["workouts"]["count"]
            + (1 if progress["weight"] else 0)
        )
        return progress, rows

    return _run_audited("get_progress", {"period": period}, op)
