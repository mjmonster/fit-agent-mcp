"""MCP client wiring for Server B.

Uses langchain-mcp-adapters (MultiServerMCPClient) over streamable HTTP with the
per-user bearer attached as a header:

    headers={"Authorization": f"Bearer {settings.token}"}

Tools are DISCOVERED at runtime from Server A — never hard-coded. This module is
the only place Server B touches the wire.

Implemented test-first — driven by the tier-2 stub-behavioral evals.
"""
