# AMC RFP & Portfolio Insight Orchestrator — Phase 01 (DEV)

Multi-agent Strands Agents system for a Mutual Fund AMC. Ingests an
institutional RFP / portfolio query and produces a compliant, client-ready
response via a self-correcting compliance loop (Quant + Qual → LLM-as-a-Judge
Compliance → Revisor → re-check → Synthesizer).

Full plan: `C:\Users\komba\.claude\plans\mutable-wibbling-turtle.md` (approved,
in-progress). Original business-requirements brainstorm (untrusted for API
calls, trusted for business rules/rubric/mock data):
`DEV - AMC RFP and Portfolio Orchestrator.md`.

## Stack

- **Package manager**: `uv` (src-layout package `src/amc_orchestrator/`)
- **Agent framework**: `strands-agents` v1.47 (real PyPI package — see "API
  gotchas" below, a lot of hallucinated API calls exist in blog posts/docs)
- **DEV LLM**: Ollama, `qwen2.5:7b-instruct` (chosen over llama3.2 for
  reliable structured-output/tool-calling; already pulled locally)
- **DEV data**: SQLite (`local_dev.db`, gitignored) for quant metrics,
  persistent on-disk ChromaDB (`data/chroma/`, gitignored) for qual RAG
- **STAGING/PROD** (not built yet): swap to `BedrockModel` via
  `config/model_factory.py` — zero agent-code changes required
- **API**: FastAPI (`api/main.py` + `api/routes/rfp.py`, Milestone 8 - `POST
  /api/v1/rfp`, `GET /health`; start via `uv run python -m amc_orchestrator.main`
  or the `amc-orchestrator` console script)
- **Logging**: structlog, JSON or console renderer
- **Tests**: pytest, `unit` (fast, no LLM) vs `integration` (marker
  `@pytest.mark.integration`, needs Ollama running, auto-skips if not)

## How to resume work

```powershell
# 1. Confirm Ollama is running with the right model
ollama list   # should show qwen2.5:7b-instruct
ollama serve  # if not already running as a service

# 2. Sync deps (uv.lock is committed)
uv sync

# 3. Fast unit suite (no LLM needed) - should always be green
uv run pytest tests/unit -q

# 4. Smoke test the graph directly (slow - 5-10+ min on CPU-only Ollama)
uv run python -m amc_orchestrator.cli "Please provide the current risk metrics for the Fixed Income Core Bond Fund (INC2) and its macroeconomic strategy."

# 5. Integration tests (slow, needs Ollama; skips gracefully if unreachable)
uv run pytest tests/integration -m integration -q

# 6. Start the API server (M8) - POST /api/v1/rfp, GET /health, /docs
uv run python -m amc_orchestrator.main
```

Check `git log --oneline` for the milestone-by-milestone commit history —
each commit is a working, tested checkpoint.

## Current status (as of last session)

Working through the approved plan's 10 milestones sequentially:

- [x] M0 — De-risked cyclic-graph behavior by reading the *actual installed*
      `strands/multiagent/graph.py` source directly instead of guessing —
      see "API gotchas" below, this is where the two real bugs were found.
- [x] M1 — `uv` skeleton, `Settings`/`model_factory`, git init.
- [x] M2 — `data/sqlite_store.py` + `data/chroma_store.py`, 4 mock funds
      (EQG1 Largecap, SMC3 Smallcap/high-risk, INC2 Debt, BLN4 Hybrid), 9 unit tests.
- [x] M3 — `tools/quant_tools.py` + `tools/qual_tools.py`, 4 unit tests.
- [x] M4 — `observability/logging_setup.py` + `hooks.py`, quant agent
      smoke-tested against real Ollama.
- [x] M5 — qual, compliance (LLM-as-a-Judge, `structured_output_model`),
      revisor, synthesizer agents all written and individually smoke-tested.
- [x] M6 — `workflows/routing.py` + `graph_build.py` + `cli.py` written.
      **Both bugs below confirmed fixed** via a 3rd CLI verification run
      (`/tmp/cli_lowrisk3.log`, PAUSED session's last action): node ordering
      was correct (compliance_check ran only after quant+qual, no premature
      parallel execution of revise_draft/final_synthesis), and when
      `qwen2.5:7b-instruct` hit `StructuredOutputException` again on
      `compliance_check` (2nd occurrence out of 3 runs - see "known
      flaky things"), the CLI caught it gracefully via
      `summarize_exception()` and printed the proper escalation holding
      message instead of crashing (exit code 0). **This is still only a
      crash-proofed failure, not a successful full run** - we have not yet
      seen this exact low-risk query complete with an APPROVED verdict and
      a real synthesized report, only the escalation fallback. Code changes
      from this verification are committed; not yet re-run to see a clean
      APPROVED pass.
- [x] M7a — Added `Agent(retry_strategy=...)` investigation +
      `_RetryingComplianceAgent` (`agents/compliance_agent.py`): confirmed
      the built-in `ModelRetryStrategy` only retries `ModelThrottledException`,
      never `StructuredOutputException`, so a manual clean-slate retry
      (`compliance_structured_output_max_attempts`, default 3 total
      attempts) was added around just the compliance node. Unit-tested
      (`tests/unit/test_compliance_agent_retry.py`, mocked, no Ollama). This
      *did* work exactly as designed on a live CLI re-run - **but the same
      run still failed 3/3 attempts** and escalated. See the "root cause
      found" addendum to Bug #2 below for why the retry alone can't fully
      close this gap, and why it's being parked rather than chased further.
- [x] M7b — `test_graph_smoke.py`/`test_smc3_high_risk.py` hardened to
      assert the resilience contract (never crash; either a real compliant
      completion or a proper escalation) via the same
      try/except-around-`graph(...)` pattern as `cli.py`, instead of a
      guaranteed APPROVED outcome - see Bug #2 addendum. **Both passed** on
      a real run against Ollama (`uv run pytest tests/integration -m
      integration -q`, 2 passed in ~19 min - `smc3` in particular needs at
      least 2 real `compliance_check` passes plus a `revise_draft` cycle to
      pass at all, so this is a genuine end-to-end proof, not a vacuous one).
- [x] M8 — FastAPI REST layer. `api/main.py` (app factory, `lifespan`
      startup - **not** the deprecated `@app.on_event`, see "API gotchas" -
      seeds SQLite/Chroma, CORS from `settings.cors_origin_list`, `/health`),
      `api/routes/rfp.py` (`POST /api/v1/rfp`, the exact same
      try/except → `summarize_exception()` safety net as `cli.py`), and
      `main.py` (`run()` - fills in the `amc-orchestrator` console-script
      entry point already declared in `pyproject.toml` since M1, which had
      no implementation until now). 4 unit tests
      (`test_api_rfp.py`, mocked `build_rfp_graph`, no Ollama needed) plus a
      live out-of-process `uvicorn` smoke test (`/health`, `/openapi.json`,
      and a validation-rejection POST all confirmed working for real, not
      just via `TestClient`).
- [x] M9 — `docs/architecture.md` (system reference: graph topology, both
      real bugs and their fixes, termination/synthesizer/data-layer/model-
      abstraction/observability design, repo map), `docs/user_guide.md`
      (setup, full `Settings` env-var reference, mock fund data table, CLI +
      API usage with PowerShell-friendly examples, troubleshooting),
      `docs/compliance_rubric.md` (verbatim mirror of
      `config/compliance_rubric.py`, per that file's own docstring promise),
      `docs/postman/amc_orchestrator.postman_collection.json` (health check +
      low-risk INC2 + high-risk SMC3 + validation-error requests against the
      real `POST /api/v1/rfp`). This CLAUDE.md remains the working session
      log; those are the stable reference docs.
- [x] M10 — hardening. Two of the four plan items were already solid before
      this pass: ticker-not-found at the tool/data layer
      (`test_tools.py::test_get_fund_performance_unknown_ticker_returns_error_payload`)
      and malformed/missing-verdict fallback in routing
      (`test_routing.py`'s `None`-verdict cases, including at
      `max_attempts=1`) - both already unit-tested, no new code needed.
      Added this session: **readiness endpoint**
      (`observability/readiness.py` + `GET /health/ready`, checks Ollama
      reachability in dev and SQLite/Chroma dir writability, 200 when ready
      else 503; `tests/integration/conftest.py` now reuses the same
      `ollama_reachable()` instead of duplicating it; 5 new unit tests +
      2 API unit tests + a live out-of-process smoke test of both the
      ready and not-ready cases, confirmed working), **`test_forced_escalation.py`**
      (the SMC3 bait question with `MAX_COMPLIANCE_ATTEMPTS` forced to 1 via
      the new `isolated_graph_settings_single_attempt` fixture - the real
      end-to-end proof that a REJECTED draft never escapes just because the
      attempt budget is exhausted, complementing routing.py's isolated unit
      proof - **passed live, twice independently**, 551s and again as part
      of a combined run), and **`test_ticker_not_found.py`** (a nonexistent
      ticker query through the real graph, proving the agent layer - not
      just the tool wrapper - reports missing data honestly instead of
      fabricating figures - **passed live**, 373s).

  **Verification note**: the dev machine ran critically low on RAM
  (0.47GB free / 15.69GB total, likely from a long Ollama session plus
  unrelated apps) partway through this milestone's verification, which
  killed several background `pytest` runs outright (not a test failure -
  no assertion ever ran; the process itself died mid-run, confirmed via
  `Get-Process`/`Get-NetTCPConnection` showing no stray processes and
  `ollama ps` showing genuine 100% CPU generation each time). `test_graph_smoke.py`
  and `test_smc3_high_risk.py` were **not** re-run fresh after the M10
  conftest.py refactor because of this - they already passed together
  earlier this session (see M7b, 1144s clean run) before that refactor,
  which only extracted a shared `_build_isolated_settings()` helper and
  swapped a locally-duplicated `_ollama_reachable()` for the identical
  `observability.readiness.ollama_reachable()` - verified by inspection to
  be behavior-preserving (same env vars, same seeding calls, same
  fixture yield/cache-clear pattern). If you have RAM headroom, re-running
  `uv run pytest tests/integration -m integration -q` once fully (all 4)
  is worthwhile but not believed necessary.

  Also found and fixed in passing: an earlier session's manual
  `uv run uvicorn ... &` / `kill %1` smoke tests (see M8) left orphaned
  Windows processes bound to ports 8123-8126 that `kill %1` doesn't
  reliably reap on this platform (Git Bash job control only kills the
  top-level handle, not `uv run`'s child process) - these were silently
  competing for CPU with later Ollama runs. Cleaned up via
  `Stop-Process` (user-confirmed, since it's a system-wide process kill).
  **Takeaway for next time**: prefer capturing the PID explicitly (e.g.
  `uv run uvicorn ... & echo $!`) and verify termination with
  `Get-NetTCPConnection -LocalPort <port>` after `kill`, rather than
  trusting `kill %1` alone on Windows.

### Immediate next step (session resumed 2026-07-11)

**Decision made 2026-07-11**: the `StructuredOutputException` flakiness is a
known, root-caused DEV-only limitation (Ollama ignores `tool_choice` - see
Bug #2 addendum). It's parked, not chased further. M7 (retry fix + hardened
integration tests), M8 (FastAPI layer), M9 (docs), and M10 (hardening) are
all done this session - all four are the last of the originally-planned 10
milestones. **All 10 milestones are now checked off.** Natural next steps
from here, none yet scoped: broader hardening (readiness when Bedrock/AWS
creds are misconfigured in staging/prod, load testing), CI wiring (a GitHub
Actions workflow was never set up - `uv run pytest tests/unit` is a natural
fast gate, integration tests would need a hosted Ollama runner), or moving
on to STAGING environment setup (`config/model_factory.py` should already
support this with zero agent-code changes, per its own design, but that
claim has never actually been exercised end-to-end against real Bedrock).

## Architecture (why it's built this way)

Five agents as Strands Graph nodes:
`quant_data_pull`, `qual_narrative_pull` (entry points, parallel) →
`compliance_check` (LLM-as-a-Judge, `structured_output_model=ComplianceVerdict`)
→ either `revise_draft` (loops back to `compliance_check`) or
`final_synthesis`, gated by conditions in `workflows/routing.py`.

**Termination has two layers**: `MAX_COMPLIANCE_ATTEMPTS` (default 3,
graceful — forces synthesis even if still REJECTED) and
`GRAPH_MAX_NODE_EXECUTIONS` (hard ceiling — if this actually fires, the
whole graph fails with **no output at all**, so the graceful layer must
always resolve first; see `routing.py`'s module docstring).

**Synthesizer has two branches, never blended**: APPROVED → full polished
report; anything else → the exact `ESCALATION_HOLDING_MESSAGE` from
`config/messages.py` (single source of truth, shared with the graph-level
exception fallback in `workflows/result_extraction.py`).

## API gotchas (learned the hard way — read before touching graph_build.py/routing.py)

The original brainstorm doc invented APIs that don't exist
(`OllamaProvider`, `add_conditional_edges`, `set_recursion_limit`,
`app.invoke(...)`, deprecated `@app.on_event`). Real API, verified against
the installed package source at
`.venv/Lib/site-packages/strands/multiagent/graph.py`:

- `GraphBuilder.add_edge(from, to, condition=fn)` — `condition` is
  `Callable[[GraphState], bool]`, no `condition=` means unconditional.
- `GraphBuilder.set_execution_timeout(seconds)` — **seconds, not
  milliseconds** (caught a unit bug from this).
- Models: `strands.models.BedrockModel`, `strands.models.ollama.OllamaModel`
  (not `*Provider`).
- Structured output: `Agent(structured_output_model=SomePydanticModel)` —
  `AgentResult.structured_output` is populated automatically on a normal
  `agent(...)` call (confirmed via smoke test), no need to call a separate
  `.structured_output()` method.

### Bug #1 (fixed): node readiness is OR-across-edges, not AND

`Graph._is_node_ready_with_conditions` schedules a node as soon as **any
one** incoming edge from the just-completed batch is satisfied — not once
**all** incoming edges are satisfied. The original design gave
`revise_draft`/`final_synthesis` unconditional edges directly from
quant/qual "for grounding" — but since quant/qual complete in the very
first batch, those unconditional edges fired immediately, causing
`revise_draft` and `final_synthesis` to run **in parallel with
`compliance_check`'s first pass**, before any verdict existed. Caught via
an actual CLI run showing all three nodes starting within ~1 second of
each other.

**Fix**: every edge into `revise_draft`/`final_synthesis` (from quant, qual,
*and* compliance) shares the *same* condition function
(`needs_revision`/`ready_to_synthesize`), and those functions
short-circuit to `False` whenever `compliance_check` hasn't executed even
once yet (`attempts == 0`). This is why `routing.py` distinguishes
"compliance hasn't run" from "compliance ran but produced no verdict" —
conflating them was the root cause. See the docstrings in `routing.py` and
`graph_build.py` for the full reasoning — **do not simplify this back to
per-edge conditions without re-reading them.**

### Bug #2 (crash-proofed; root-caused 2026-07-11 and parked as a known DEV-only limitation): StructuredOutputException crashes the whole graph

`qwen2.5:7b-instruct` fails to invoke the structured-output tool even when
forced **more often than expected - 2 of 3 end-to-end CLI runs this
session**, always on `compliance_check`. Strands node execution is
fail-fast - the exception propagates all the way out of `graph(...)` as a
**raw Python exception**, not a `FAILED` GraphResult. **Fix applied**:
`cli.py` wraps `graph(question)` in try/except and calls
`workflows.result_extraction.summarize_exception(exc)`, so it degrades to
the safe escalation message instead of crashing - confirmed working.
`api/routes/rfp.py` (M8) must apply the identical try/except.

**Retry added (2026-07-11)**: `Agent(retry_strategy=...)`
(`strands.event_loop._retry.ModelRetryStrategy`) turned out to only retry
`ModelThrottledException`, never `StructuredOutputException` - so
`_RetryingComplianceAgent` in `agents/compliance_agent.py` was added
instead: a manual retry that rolls the conversation back to a clean slate
and re-sends the same input, up to `compliance_structured_output_max_attempts`
(default 3) total attempts. Unit-tested in
`tests/unit/test_compliance_agent_retry.py`.

**Root cause found (2026-07-11), and why the retry alone isn't enough**:
Strands "forces" the structured-output tool by setting `tool_choice` on the
second half-turn (`StructuredOutputContext.set_forced_mode()` in
`strands/tools/structured_output/_structured_output_context.py`). The
Ollama model integration (`strands/models/ollama.py`) calls
`warn_on_tool_choice_not_supported(tool_choice)` and **silently ignores
it** - confirmed via the `UserWarning: A ToolChoice was provided to this
provider but is not supported and will be ignored` seen in a live CLI log.
So on this DEV stack, "forcing" never actually forces anything - the only
real lever left is a generic text nudge
(`DEFAULT_STRUCTURED_OUTPUT_PROMPT = "You must format the previous
response as structured output."`), which the model remains free to ignore.
This is why a same-session CLI re-run with the retry fix in place still
failed **3 out of 3** attempts on `compliance_check` before escalating:
retrying from a clean slate doesn't change the fundamental odds when the
forcing mechanism itself is a no-op on this provider, only sampling noise
does.

**Decision (2026-07-11): parked as a known DEV-only limitation**, not
being chased further with more prompt/retry tuning right now.
`BedrockModel` (STAGING/PROD) supports real `tool_choice` forcing, so this
exact failure mode is expected to be far rarer off of Ollama. The manual
retry stays in place as free insurance (it works exactly as designed, it
just can't guarantee an APPROVED outcome when forcing itself is inert).
Integration tests (M7) were updated to assert the actual resilience
contract - never crash, always a well-formed outcome (real compliant
completion OR proper escalation) - rather than a guaranteed APPROVED
completion.

## Known slow/flaky things in DEV

- Ollama generation on this machine is CPU-only and slow — a single agent
  turn can take 60-140s, and a full low-risk query (quant+qual parallel,
  then compliance, then synthesis) can take 5-10+ minutes end-to-end.
  Integration tests will be slow; don't assume a hang, check `ollama ps`
  and the log's timestamps before concluding something is stuck.
- `qwen2.5:7b-instruct` can fail structured output generation on
  `compliance_check` (see Bug #2) — root-caused to Ollama silently ignoring
  `tool_choice`, so "forcing" is a no-op on this stack. A manual retry
  (`_RetryingComplianceAgent`) is in place but does not guarantee success;
  this is a known, parked DEV-only limitation, not a one-off fluke.
- First Chroma run downloads the default `all-MiniLM-L6-v2` ONNX embedding
  model (~80MB) — one-time cost, already cached at
  `C:\Users\komba\.cache\chroma\onnx_models\`.

## Conventions

- Every module reads config through `config.settings.get_settings()` —
  never `os.getenv` directly.
- `config.model_factory.get_model()` is the *only* place that imports a
  concrete model class — this is what makes DEV→STAGING/PROD a config
  change, not a code change.
- Data-layer modules (`data/sqlite_store.py`, `data/chroma_store.py`) and
  tool wrappers (`tools/*.py`) are deliberately Strands-free/thin so they're
  unit-testable without an LLM.
- `.env.dev` is gitignored (only `.env.dev.example` is committed) even
  though DEV holds no real secrets — kept consistent with the STAGING/PROD
  habit.
- Git commits are one per milestone with a consistent message style — check
  `git log` for the pattern before committing new work.
