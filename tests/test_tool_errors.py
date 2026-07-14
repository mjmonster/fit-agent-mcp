"""Boundary sanitization: tools must never leak internal exception details
to the MCP client; domain errors (authz, lookup, validation) pass through.

Written RED before errors.py existed (security boundary — mandatory TDD).
"""

import sqlite3

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from fitness_mcp.errors import sanitized_tool


@sanitized_tool
def _boom_internal():
    raise sqlite3.OperationalError("no such table: users")


@sanitized_tool
def _boom_permission():
    raise PermissionError("missing required scope 'read:profile' for tool 'get_profile'")


@sanitized_tool
def _boom_lookup():
    raise LookupError("unknown subject 'user_999'")


@sanitized_tool
def _boom_value():
    raise ValueError("invalid period 'next tuesday' — expected '<days>d', e.g. '7d'")


@sanitized_tool
def _fine(x: int) -> int:
    return x * 2


def test_internal_exception_is_replaced_with_generic_message():
    with pytest.raises(ToolError) as exc_info:
        _boom_internal()
    message = str(exc_info.value)
    assert "no such table" not in message  # nothing internal leaks
    assert "sqlite" not in message.lower()
    assert "INTERNAL" in message  # stable, generic error code


def test_internal_exception_is_logged_with_real_details(caplog):
    with caplog.at_level("ERROR"), pytest.raises(ToolError):
        _boom_internal()
    assert "no such table: users" in caplog.text  # real message in the log headline
    assert "OperationalError" in caplog.text  # full traceback recorded


@pytest.mark.parametrize(
    ("fn", "exc_type", "fragment"),
    [
        (_boom_permission, PermissionError, "read:profile"),
        (_boom_lookup, LookupError, "user_999"),
        (_boom_value, ValueError, "period"),
    ],
)
def test_domain_errors_pass_through_unchanged(fn, exc_type, fragment):
    with pytest.raises(exc_type, match=fragment):
        fn()


def test_successful_calls_are_untouched():
    assert _fine(21) == 42
