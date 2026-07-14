# fit-agent-mcp

Demo project: a health-data **MCP server with per-user authorization** (`fitness-mcp`)
plus a **LangGraph coach agent** that consumes it as an MCP host (`coach-agent`).

```
User ──► coach-agent (HOST + MCP client, LangGraph) ──MCP/streamable-HTTP──► fitness-mcp (SERVER + SQLite + authz)
                                    │                                              ▲
                              bearer JWT per request                 subject derived from token ONLY
```

**The security invariant:** the user's identity never comes from the model. No tool
accepts a `user_id` — cross-user access is *unrepresentable* in the tool schemas, and
the subject is derived exclusively from the verified JWT. Enforced in CI by structural,
LLM-free evals.

## Status

Both services are implemented and proven by LLM-free CI gates:

- **Tier 1 (structural):** schema invariant (no identity params, recursive),
  raw-MCP boundary probe against the real server (no bearer / cross-user
  bearers / smuggled `user_id` / zero-scope token), audit assertions including
  denied and errored calls.
- **Tier 2 (stub-behavioral):** a deterministic stub model driven through the
  REAL LangGraph graph + REAL MCP wire + REAL Server A — proves runtime tool
  discovery, bearer attachment, the router's no-tool branch, the tool loop,
  and audit, with zero LLM calls.
- **Tier 3 (live-behavioral, on-demand — never gates CI):** the real coach agent
  (`claude-haiku-4-5`) against the real server, scored by a declarative YAML
  harness (`evals/tier3_live/`) that mirrors
  [mjmonster/llm-agent-evals](https://github.com/mjmonster/llm-agent-evals) —
  routing, direct + stored prompt-injection, and red-line cases, with a
  per-category scorecard. The harness's *scoring* logic is unit-tested and gates
  CI; only the live model runs are on-demand.

Next: Claude Desktop stdio demo, README teaching sections.

```bash
# Terminal 1 — Server A (set FITNESS_MCP_JWT_SECRET in .env first)
uv run fitness-mcp init-db
uv run fitness-mcp serve      # streamable HTTP on 127.0.0.1:8000/mcp

# Terminal 2 — talk to the coach (needs ANTHROPIC_API_KEY for the live model)
TOKEN=$(uv run fitness-mcp issue-token --sub user_001 --scopes read:profile,read:progress,write:meal_log,write:workout_log,write:weight_log)
uv run coach-agent chat --token "$TOKEN"
```

## Layout

- `src/fitness_mcp/` — Server A: MCP server, SQLite, JWT verify + scopes, audit, demo issuer
- `src/coach_agent/` — Server B: LangGraph host, MCP client (runtime tool discovery)
- `evals/tier1_structural/` — LLM-free invariant proofs (CI gate)
- `evals/tier2_stub/` — deterministic stub-model runs through the real graph + wire (CI gate)
- `evals/tier3_live/` — live-LLM routing/injection/red-line cases (on-demand, never gates)

## Development

```bash
uv sync --dev            # install
uv run pytest -m "not live"   # unit + tier 1 + tier 2 + tier-3 scoring logic (CI gate)
uv run ruff check . && uv run ruff format --check .

# Tier-3 live evals (needs ANTHROPIC_API_KEY; spins up Server A itself)
uv run python evals/tier3_live/runner.py   # prints the scorecard
uv run pytest -m live                       # same cases as pytest
```

---

*To be written as the project lands (acceptance criteria): tools vs skills vs MCP and
why this is MCP; the M×N → M+N rationale; the confused-deputy problem and how
identity-from-token defeats it; the OAuth 2.1 production path.*
