"""The hand-built LangGraph StateGraph for the coach agent.

Shape (agreed design — do NOT swap for create_react_agent):

    START -> router --(tools)--> agent <-> ToolNode --> respond -> END
                 \--(chat)------------------------------^

- router: classifies the turn; makes "small talk -> no tool" an assertable branch.
- agent: chat model bound to the runtime-discovered MCP tools.
- ToolNode: executes MCP calls (bearer already baked into the client session).
- respond: final coaching reply; the red-line seam (no diagnosing, no invented
  numbers, no PII echo).

Implemented test-first — driven by the tier-2 stub-behavioral evals, which
inject a deterministic fake ChatModel and assert on node traversal.
"""
