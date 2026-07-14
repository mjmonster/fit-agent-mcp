"""Auth spine: issuer → verifier roundtrip, rejection paths, per-tool scope checks.

This is a mandatory-TDD surface (auth/security): these tests were written RED
before auth.py / issuer.py were implemented.
"""

import time

import jwt as pyjwt
import pytest

from fitness_mcp.auth import REQUIRED_SCOPES, JWTVerifier, check_scope
from fitness_mcp.issuer import issue_token

SECRET = "test-secret"


def make_verifier(secret: str = SECRET) -> JWTVerifier:
    return JWTVerifier(lambda: secret)


async def test_mint_verify_roundtrip_preserves_subject_and_scopes():
    token = issue_token(SECRET, sub="user_001", scopes=["read:profile", "write:meal_log"])
    access = await make_verifier().verify_token(token)
    assert access is not None
    assert access.subject == "user_001"
    assert set(access.scopes) == {"read:profile", "write:meal_log"}


async def test_expired_token_rejected():
    token = issue_token(SECRET, sub="user_001", scopes=["read:profile"], ttl_seconds=-10)
    assert await make_verifier().verify_token(token) is None


async def test_wrong_secret_signature_rejected():
    token = issue_token("some-other-secret", sub="user_001", scopes=["read:profile"])
    assert await make_verifier().verify_token(token) is None


async def test_malformed_token_rejected():
    assert await make_verifier().verify_token("not-a-jwt-at-all") is None


async def test_token_without_sub_claim_rejected():
    now = int(time.time())
    token = pyjwt.encode({"scopes": ["read:profile"], "exp": now + 60}, SECRET, algorithm="HS256")
    assert await make_verifier().verify_token(token) is None


def test_issue_token_rejects_empty_subject():
    with pytest.raises(ValueError, match="sub"):
        issue_token(SECRET, sub="", scopes=["read:profile"])


@pytest.mark.parametrize("tool", sorted(REQUIRED_SCOPES))
def test_check_scope_denies_token_missing_the_scope(tool):
    with pytest.raises(PermissionError, match=REQUIRED_SCOPES[tool]):
        check_scope(tool, [])


def test_check_scope_allows_token_with_the_scope():
    check_scope("get_profile", ["read:profile"])  # must not raise


def test_check_scope_denies_unknown_tool_by_default():
    with pytest.raises(PermissionError):
        check_scope("some_future_tool", ["read:profile", "write:meal_log"])
