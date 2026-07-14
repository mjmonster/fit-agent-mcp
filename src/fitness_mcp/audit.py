"""Audit log: one row per tool call.

The subject column is ALWAYS the verified caller passed in by the tool layer —
args are stored verbatim as data (they may contain attacker-controlled text)
and are never parsed for identity.
"""

import json
from datetime import datetime
from typing import Any

from fitness_mcp.repository import Database


def record_tool_call(
    db: Database,
    subject: str,
    tool: str,
    args: dict[str, Any],
    rows_returned: int,
) -> None:
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO audit_log (subject, tool, args_json, at, rows_returned) "
            "VALUES (:subject, :tool, :args_json, :at, :rows_returned)",
            {
                "subject": subject,
                "tool": tool,
                "args_json": json.dumps(args, ensure_ascii=False, default=str),
                "at": datetime.now().isoformat(timespec="seconds"),
                "rows_returned": rows_returned,
            },
        )


def read_audit_log(db: Database) -> list[dict[str, Any]]:
    """Full audit trail, oldest first (used by the tier-1 audit evals)."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, subject, tool, args_json, at, rows_returned FROM audit_log ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]
