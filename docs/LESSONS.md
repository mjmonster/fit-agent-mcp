# Lessons log

Compounding, append-only record of issues we diagnosed and fixed — symptom, root
cause, fix, and the generalizable lesson. Newest first. Do NOT rewrite past
entries or re-read this whole file every session; a periodic job distills the
recurring themes into docs/PRECODE-CHECKLIST.md.

## 003 — Unbound model over tool_use history → 400; the eval was blind to it  ·  2026-07-14  ·  area: src/coach_agent/graph.py, evals/tier2_stub

- **Symptom:** the LangGraph `respond` node crashed on **every tool-path turn**
  (e.g. "log my lunch" → router → agent → ToolNode → agent → respond). Small talk
  worked, so the agent looked half-alive. Would have been an Anthropic HTTP 400
  in production; caught in review before it shipped.
- **Root cause:** two layers. (1) Runtime logic + infra adapter: `respond` called
  an **unbound** model (`model.invoke`, no tools) over a history containing
  `tool_use`/`tool_result` blocks. `langchain-anthropic` faithfully serializes
  `AIMessage.tool_calls` → `tool_use` blocks and `ToolMessage` → `tool_result`
  blocks, and the Anthropic Messages API **rejects those blocks when no `tools`
  are declared** (the manual agentic-loop always passes `tools=` on every
  follow-up call — that's why). (2) Test design: the tier-2 stub-behavioral eval
  used a fake ChatModel that **ignored its inputs** and returned scripted
  messages, so `respond` never fed real `tool_use` blocks to anything that would
  validate them — a green CI gate over a dead main flow. The one "respond works"
  assertion was tautological (asserted the stub's own scripted text).
- **Fix:** `respond` now runs over a **scrubbed history** — `_for_responder()`
  drops tool-call-only assistant turns and converts `ToolMessage`s to plain-text
  notes, so no `tool_use`/`tool_result` block reaches the unbound model and the
  tool data is still available as text. The stub now **records every call's
  input** and the evals assert respond's input has no tool blocks but does carry
  the tool data (plus: the bearer JWT never reaches the model). Commit on PR #2.
- **Lesson / prevention:** (a) An unbound LLM call over a history that contains
  tool_use/tool_result blocks is a provider-level error — either declare the
  tools, or strip the blocks before the call. Any node that re-invokes the model
  over accumulated agent state is suspect. (b) **A stub/fake that ignores its
  inputs cannot prove behavior — only plumbing.** If an eval's fake returns fixed
  output regardless of what it's handed, assert on the *inputs it received*, not
  just the outputs it produced; otherwise the gate is green while the real path is
  broken. Prefer input-recording fakes for any "did we feed the model the right
  thing (and never the secret)" claim.
- **Links:** PR #2 · src/coach_agent/graph.py (`_for_responder`) · src/coach_agent/stub_model.py · evals/tier2_stub/test_graph_wiring.py

## 002 — Regex-validated numeric input still crashed on magnitude  ·  2026-07-14  ·  area: src/fitness_mcp/repository.py

- **Symptom:** `get_progress(period="9000000d")` crashed the tool call with an
  unhandled `OverflowError` (`date value out of range`; even bigger values hit
  "Python int too large to convert to C int"). Client-controllable, DoS-flavored,
  and the raw message leaked to the client until 001's fix landed.
- **Root cause:** runtime logic. `_parse_period` validated the SHAPE of the
  input (`^(\d+)d$`) but not its BOUNDS. `datetime.now() - timedelta(days=huge)`
  then overflowed. A regex pass reads as "validated" but says nothing about
  magnitude.
- **Fix:** bound the parsed value (1–365 days) with an authored, client-facing
  `ValueError` ("data can only be retrieved for the past year"); parametrized
  tests cover 366d, 9000000d, and the C-int-overflow value
  (`src/fitness_mcp/repository.py`, `tests/test_repository.py`).
- **Lesson / prevention:** shape validation is not bounds validation. Every
  numeric that enters arithmetic — especially date math — needs an explicit
  min/max, even (especially) when a regex already "validated" it. When writing
  a validator for `\d+`-style input, write the huge-value test in the same
  breath.
- **Links:** commit fc093d6 · PR #1 · src/fitness_mcp/repository.py

## 001 — FastMCP returns raw exception strings to MCP clients  ·  2026-07-14  ·  area: src/fitness_mcp/server.py

- **Symptom:** any exception raised inside an MCP tool body (e.g.
  `sqlite3.OperationalError: no such table: users`) was returned verbatim to the
  client in the `isError` tool result — leaking backend type, schema state, and
  internal messages.
- **Root cause:** infra adapter (framework default). The MCP SDK's FastMCP tool
  wrapper does `raise ToolError(f"Error executing tool {name}: {e}")` and the
  low-level server serializes `str(e)` into the response. There is no built-in
  boundary sanitization — the framework's default is to leak.
- **Fix:** `sanitized_tool` decorator on every tool: authored domain errors
  (`PermissionError`/`LookupError`/`ValueError`) pass through; everything else
  is logged server-side with real message + traceback and replaced with a
  generic `INTERNAL` message (`src/fitness_mcp/errors.py`, applied in
  `server.py`; tests in `tests/test_tool_errors.py`).
- **Lesson / prevention:** never assume a framework sanitizes errors at the
  boundary — verify what actually reaches the wire by reading the framework's
  error path or testing with a deliberate internal failure. Any new MCP tool
  (or handler in any framework) gets the boundary catch-all from day one; the
  "safe pass-through" exception list must be explicit and authored.
- **Links:** commit fc093d6 · PR #1 · src/fitness_mcp/errors.py
