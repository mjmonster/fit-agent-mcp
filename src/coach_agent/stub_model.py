"""Deterministic fake ChatModel for tier-2 evals.

Replays scripted messages (including tool_calls) through the REAL graph, REAL
MCP wire, and REAL Server A — proving the plumbing without any LLM. Mirrors
the offline-by-default convention of github.com/mjmonster/llm-agent-evals.

It also RECORDS the inputs of every call in `self.calls`, so evals can assert
on what actually reached the model (e.g. that the bearer token never does, and
that respond receives tool data as text without tool_use blocks), and RAISES on
overrun instead of silently wrapping — so a graph change that adds a model call
fails the eval loudly rather than replaying responses[0].
"""

from typing import Any

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from pydantic import Field


class StubChatModel(FakeMessagesListChatModel):
    """FakeMessagesListChatModel that records inputs, fails loud on overrun, and
    tolerates tool binding.

    `responses` are returned in order, one per model call — script them to
    match the graph's call sequence (router, agent..., respond).
    """

    calls: list[Any] = Field(default_factory=list)

    def bind_tools(self, tools: Any, **kwargs: Any) -> "StubChatModel":
        # The stub decides tool calls from its script, not from schemas —
        # binding is a no-op so ToolNode wiring can be exercised without an LLM.
        return self

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        if len(self.calls) >= len(self.responses):
            raise AssertionError(
                f"StubChatModel exhausted: {len(self.responses)} scripted responses, "
                f"but call #{len(self.calls) + 1} was made — did the graph wiring change?"
            )
        self.calls.append(input)
        return super().invoke(input, config, **kwargs)
