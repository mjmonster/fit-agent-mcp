"""JWT verification + per-tool scope checks for Server A.

THE SECURITY INVARIANT lives here: the subject used for every DB query comes
from the verified token's `sub` claim only — never from tool arguments, never
from anything the model asserts.
"""

from collections.abc import Callable, Sequence

import jwt as pyjwt
from mcp.server.auth.provider import AccessToken, TokenVerifier

# Scope map: tool -> required scope. Single source of truth; unknown tools are
# denied by default (least privilege).
REQUIRED_SCOPES: dict[str, str] = {
    "get_profile": "read:profile",
    "log_meal": "write:meal_log",
    "log_workout": "write:workout_log",
    "log_weight": "write:weight_log",
    "get_progress": "read:progress",
}


class JWTVerifier(TokenVerifier):
    """Stateless HS256 verifier. The secret is provided lazily so the server
    module stays importable without runtime configuration."""

    def __init__(self, secret_provider: Callable[[], str]) -> None:
        self._secret_provider = secret_provider

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = pyjwt.decode(
                token,
                self._secret_provider(),
                algorithms=["HS256"],
                options={"require": ["sub", "exp"]},
            )
        except pyjwt.InvalidTokenError:
            return None
        subject = claims["sub"]
        return AccessToken(
            token=token,
            client_id=subject,
            subject=subject,
            scopes=list(claims.get("scopes", [])),
            expires_at=int(claims["exp"]),
        )


def check_scope(tool: str, scopes: Sequence[str]) -> None:
    """Deny unless the token carries the tool's required scope.

    Unknown tools are denied outright — a new tool must be added to
    REQUIRED_SCOPES deliberately, never granted by omission.
    """
    required = REQUIRED_SCOPES.get(tool)
    if required is None:
        raise PermissionError(f"tool '{tool}' has no scope mapping — denied by default")
    if required not in scopes:
        raise PermissionError(f"missing required scope '{required}' for tool '{tool}'")
