"""Demo token issuer (stands in for an OAuth 2.1 authorization server).

Mints HS256 JWTs {sub, scopes, iat, exp} for synthetic users. Lives beside
Server A — they share the signing secret. Server B only ever HOLDS tokens;
it can never mint or forge one.
"""

import time
from collections.abc import Sequence

import jwt as pyjwt

DEFAULT_TTL_SECONDS = 3600


def issue_token(
    secret: str,
    sub: str,
    scopes: Sequence[str],
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    """Mint a scoped, expiring JWT for one synthetic subject."""
    if not sub:
        raise ValueError("sub must be a non-empty subject id (e.g. 'user_001')")
    now = int(time.time())
    claims = {"sub": sub, "scopes": list(scopes), "iat": now, "exp": now + ttl_seconds}
    return pyjwt.encode(claims, secret, algorithm="HS256")
