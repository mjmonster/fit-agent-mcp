"""Deterministic fake ChatModel for tier-2 evals.

Replays scripted messages (including tool_calls) through the REAL graph, REAL
MCP wire, and REAL Server A — proving the plumbing without any LLM. Mirrors
the offline-by-default convention of github.com/mjmonster/llm-agent-evals.
"""

from typing import Any

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel


class StubChatModel(FakeMessagesListChatModel):
    """FakeMessagesListChatModel that tolerates tool binding.

    `responses` are returned in order, one per model call — script them to
    match the graph's call sequence (router, agent..., respond).
    """

    def bind_tools(self, tools: Any, **kwargs: Any) -> "StubChatModel":
        # The stub decides tool calls from its script, not from schemas —
        # binding is a no-op so ToolNode wiring can be exercised without an LLM.
        return self
