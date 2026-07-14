"""Deterministic fake ChatModel for tier-2 evals.

Replays scripted tool-call decisions through the REAL graph, REAL MCP wire, and
REAL Server A — proving the plumbing (token attachment, discovery, audit)
without any LLM. Mirrors the offline-by-default convention of
github.com/mjmonster/llm-agent-evals.

Implemented test-first alongside graph.py.
"""
