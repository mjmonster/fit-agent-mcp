"""MCP client wiring for Server B — the only place B touches the wire.

Tools are DISCOVERED from Server A at runtime (never hard-coded), over
streamable HTTP with the user's bearer attached to every request. Server B
only HOLDS the token; it cannot mint one (no signing secret here).
"""

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient


async def discover_tools(server_url: str, token: str) -> list[BaseTool]:
    """Connect to Server A and return its tools as LangChain tools.

    The bearer header rides on every MCP request the returned tools make —
    identity travels out-of-band of the model, which never sees the token.
    """
    client = MultiServerMCPClient(
        {
            "fitness": {
                "transport": "streamable_http",
                "url": server_url,
                "headers": {"Authorization": f"Bearer {token}"},
            }
        }
    )
    return await client.get_tools()
