"""Boundary error sanitization for MCP tools.

Tools are a system boundary: domain errors we author (authz denials, unknown
subject, input validation) are safe and client-actionable and pass through;
anything else is logged server-side with full traceback + real message, and
the client receives only a stable generic error.
"""

import functools
import logging

from mcp.server.fastmcp.exceptions import ToolError

logger = logging.getLogger(__name__)

# Exceptions we raise deliberately, with messages written for the client.
_SAFE_EXCEPTIONS = (PermissionError, LookupError, ValueError)

_GENERIC_MESSAGE = "INTERNAL: the server could not process this request"


def sanitized_tool(fn):
    """Catch-all for tool bodies: pass domain errors through, sanitize the rest."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except _SAFE_EXCEPTIONS:
            raise
        except Exception as e:
            # Real exception message in the headline + full traceback in the
            # log; the client gets only the generic message.
            logger.exception("tool %s failed: %s", fn.__name__, e)
            raise ToolError(_GENERIC_MESSAGE) from None

    return wrapper
