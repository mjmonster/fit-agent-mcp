"""Tier 1 (structural, LLM-free, CI-gating): THE SECURITY INVARIANT.

No MCP tool may expose a parameter that could carry a user identity. The subject
must be unrepresentable in tool arguments — it comes only from the verified JWT.

These tests introspect the real FastMCP server instance in-process. They are the
RED tests that drive Server A's implementation.
"""

from fitness_mcp.auth import REQUIRED_SCOPES
from fitness_mcp.server import mcp

# Any parameter name that could smuggle an identity through a tool schema.
FORBIDDEN_PARAM_NAMES = {
    "user_id",
    "userid",
    "user",
    "subject",
    "sub",
    "patient_id",
    "account_id",
    "member_id",
    "uid",
    "owner",
    "for_user",
}

# The agreed tool contract (brief's four + log_weight, per grounded decision Q8).
CONTRACT_TOOLS = {
    "get_profile",
    "log_meal",
    "log_workout",
    "log_weight",
    "get_progress",
}


def _all_property_names(schema: dict) -> set[str]:
    """Recursively collect every property name in a JSON schema."""
    names: set[str] = set()
    for key, prop in (schema.get("properties") or {}).items():
        names.add(key.lower())
        if isinstance(prop, dict):
            names |= _all_property_names(prop)
    for branch in ("items", "additionalProperties"):
        if isinstance(schema.get(branch), dict):
            names |= _all_property_names(schema[branch])
    for combiner in ("anyOf", "oneOf", "allOf"):
        for sub in schema.get(combiner) or []:
            if isinstance(sub, dict):
                names |= _all_property_names(sub)
    if isinstance(schema.get("$defs"), dict):
        for sub in schema["$defs"].values():
            if isinstance(sub, dict):
                names |= _all_property_names(sub)
    return names


async def test_contract_tools_are_registered():
    """All five contract tools exist on the server (drives implementation)."""
    tools = await mcp.list_tools()
    registered = {t.name for t in tools}
    missing = CONTRACT_TOOLS - registered
    assert not missing, f"contract tools not registered: {sorted(missing)}"


async def test_every_registered_tool_has_a_scope_mapping():
    """Least privilege is deny-by-default: a tool absent from REQUIRED_SCOPES
    can never be authorized, so registering one unmapped is a wiring bug."""
    tools = await mcp.list_tools()
    unmapped = {t.name for t in tools} - set(REQUIRED_SCOPES)
    assert not unmapped, f"tools registered without a scope mapping: {sorted(unmapped)}"


async def test_no_tool_exposes_a_user_identity_parameter():
    """No registered tool schema contains any identity-shaped parameter."""
    tools = await mcp.list_tools()
    assert tools, "no tools registered — invariant check would be vacuous"
    for tool in tools:
        exposed = _all_property_names(tool.inputSchema or {}) & FORBIDDEN_PARAM_NAMES
        assert not exposed, (
            f"tool '{tool.name}' exposes identity parameter(s) {sorted(exposed)} — "
            "the subject must come from the verified JWT only"
        )
