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

Server A (`fitness-mcp`) is implemented and proven by the tier-1 structural evals:
schema invariant, raw-MCP boundary probe (real server, real HTTP, adversarial
client), scope enforcement, and audit assertions — all green, all LLM-free.
Next: Server B (LangGraph agent) + tier-2 stub-behavioral evals.

```bash
# Run Server A locally (set FITNESS_MCP_JWT_SECRET in .env first)
uv run fitness-mcp init-db
uv run fitness-mcp issue-token --sub user_001 --scopes read:profile,read:progress,write:meal_log,write:workout_log,write:weight_log
uv run fitness-mcp serve      # streamable HTTP on 127.0.0.1:8000/mcp
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
uv run pytest -m "not live"   # tiers 1+2 (CI gate)
uv run ruff check . && uv run ruff format --check .
```

---

*To be written as the project lands (acceptance criteria): tools vs skills vs MCP and
why this is MCP; the M×N → M+N rationale; the confused-deputy problem and how
identity-from-token defeats it; the OAuth 2.1 production path.*
