"""The FastMCP server for fitness-mcp (Server A).

THE SECURITY INVARIANT: no tool here accepts a user/subject identifier. The
subject is derived exclusively from the verified JWT bearer (get_access_token),
and every tool runs: verify -> scope check -> subject-scoped query -> audit row.
The tier-1 structural evals enforce the schema side of this in CI.
"""

from datetime import datetime
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

from fitness_mcp.audit import record_tool_call
from fitness_mcp.auth import JWTVerifier, check_scope
from fitness_mcp.config import get_settings
from fitness_mcp.repository import Database

from mcp.server.fastmcp import FastMCP  # isort: skip

# Static OAuth metadata for the demo. In production these come from the real
# authorization server (see README: OAuth 2.1 path).
_DEMO_ISSUER = "http://127.0.0.1:8000"
_DEMO_RESOURCE = "http://127.0.0.1:8000/mcp"

mcp = FastMCP(
    "fitness-mcp",
    # The secret is resolved lazily at verification time, keeping this module
    # importable (e.g. by the schema evals) without runtime configuration.
    token_verifier=JWTVerifier(lambda: get_settings().jwt_secret),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(_DEMO_ISSUER),
        resource_server_url=AnyHttpUrl(_DEMO_RESOURCE),
    ),
)


def _db() -> Database:
    return Database(get_settings().db_path)


def _authorized_subject(tool: str) -> str:
    """The ONLY source of identity for every tool: the verified bearer token.

    Raises PermissionError when unauthenticated or missing the tool's scope.
    """
    access = get_access_token()
    if access is None or not access.subject:
        raise PermissionError("no verified bearer token on this request")
    check_scope(tool, access.scopes)
    return access.subject


def _parse_at(at: str | None) -> datetime | None:
    return datetime.fromisoformat(at) if at else None


@mcp.tool()
def get_profile() -> dict[str, Any]:
    """Get the authenticated user's profile: height, latest weight, gender, goal."""
    subject = _authorized_subject("get_profile")
    db = _db()
    profile = db.get_profile(subject)
    record_tool_call(db, subject, "get_profile", {}, rows_returned=1)
    return profile


@mcp.tool()
def log_meal(
    description: str, calories: int | None = None, at: str | None = None
) -> dict[str, Any]:
    """Log a meal for the authenticated user. `at` is ISO-8601; defaults to now."""
    subject = _authorized_subject("log_meal")
    db = _db()
    row_id = db.log_meal(subject, description, calories=calories, at=_parse_at(at))
    args = {"description": description, "calories": calories, "at": at}
    record_tool_call(db, subject, "log_meal", args, rows_returned=1)
    return {"logged": True, "id": row_id}


@mcp.tool()
def log_workout(
    kind: str, duration_min: int, notes: str | None = None, at: str | None = None
) -> dict[str, Any]:
    """Log a workout for the authenticated user. `at` is ISO-8601; defaults to now."""
    subject = _authorized_subject("log_workout")
    db = _db()
    row_id = db.log_workout(subject, kind, duration_min, notes=notes, at=_parse_at(at))
    args = {"kind": kind, "duration_min": duration_min, "notes": notes, "at": at}
    record_tool_call(db, subject, "log_workout", args, rows_returned=1)
    return {"logged": True, "id": row_id}


@mcp.tool()
def log_weight(weight_kg: float, at: str | None = None) -> dict[str, Any]:
    """Record the authenticated user's weight. `at` is ISO-8601; defaults to now."""
    subject = _authorized_subject("log_weight")
    db = _db()
    row_id = db.log_weight(subject, weight_kg, at=_parse_at(at))
    record_tool_call(db, subject, "log_weight", {"weight_kg": weight_kg, "at": at}, rows_returned=1)
    return {"logged": True, "id": row_id}


@mcp.tool()
def get_progress(period: str = "7d") -> dict[str, Any]:
    """Progress for the authenticated user over a period like '7d' or '30d':
    weight trend, workout count, calorie summary, and recent meal descriptions."""
    subject = _authorized_subject("get_progress")
    db = _db()
    progress = db.get_progress(subject, period)
    rows = (
        len(progress["recent_meals"])
        + progress["workouts"]["count"]
        + (1 if progress["weight"] else 0)
    )
    record_tool_call(db, subject, "get_progress", {"period": period}, rows_returned=rows)
    return progress
