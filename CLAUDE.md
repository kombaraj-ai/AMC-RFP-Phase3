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
- **API**: FastAPI (not built yet — Milestone 8)
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
- [ ] M7 — integration tests (`test_graph_smoke.py`, `test_smc3_high_risk.py`)
      are **written** but have never successfully passed yet (both assert a
      real APPROVED/completed outcome, which the StructuredOutputException
      flakiness below could cause to fail intermittently as-is).
- [ ] M8 — FastAPI REST layer (not started)
- [ ] M9 — docs (`docs/architecture.md`, `docs/user_guide.md`, Postman
      collection) (not started — this CLAUDE.md is a stopgap, not a
      replacement for those)
- [ ] M10 — hardening (ticker-not-found path, forced
      `MAX_COMPLIANCE_ATTEMPTS=1` escalation test, etc.)

### Immediate next step (session paused here on 2026-07-10)

1. **Consider adding a retry for `StructuredOutputException`** before
   running the integration tests - it has now fired on 2 of 3 end-to-end
   attempts (always on `compliance_check`), which will make
   `test_smc3_high_risk.py`/`test_graph_smoke.py` flaky as currently
   written (they assert a real APPROVED/completed outcome, not just "didn't
   crash"). Worth investigating the `Agent(retry_strategy=...)` constructor
   param (`strands.event_loop._retry.ModelRetryStrategy`, seen in the
   `Agent.__init__` signature but not yet explored) before writing a manual
   retry loop.
2. Re-run the low-risk CLI query (see command below) a few times to gauge
   the actual failure rate and confirm at least one clean APPROVED pass
   with a real synthesized report (never actually observed yet).
3. Then run `uv run pytest tests/integration -m integration -k smc3` for
   the high-risk loop-triggering scenario.
4. Then proceed to M8 (FastAPI layer).

Stray background processes from the paused session (`ollama.exe`,
possibly a leftover `python.exe`) may still be running - check `ollama ps`
/ Task Manager; safe to leave running or stop, they hold no unsaved state.

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

### Bug #2 (crash-proofed, but underlying flakiness NOT yet fixed): StructuredOutputException crashes the whole graph

`qwen2.5:7b-instruct` fails to invoke the structured-output tool even when
forced **more often than expected - 2 of 3 end-to-end CLI runs this
session**, always on `compliance_check`. Strands node execution is
fail-fast - the exception propagates all the way out of `graph(...)` as a
**raw Python exception**, not a `FAILED` GraphResult. **Fix applied**:
`cli.py` wraps `graph(question)` in try/except and calls
`workflows.result_extraction.summarize_exception(exc)`, so it degrades to
the safe escalation message instead of crashing - confirmed working.
**Not yet done**: nothing yet reduces *how often* this happens, so every
successful run so far has been luck, not the norm. `api/routes/rfp.py`
(M8) must apply the identical try/except. See "Immediate next step" above
for the planned investigation (an `Agent(retry_strategy=...)` param exists
but hasn't been explored yet).

## Known slow/flaky things in DEV

- Ollama generation on this machine is CPU-only and slow — a single agent
  turn can take 60-140s, and a full low-risk query (quant+qual parallel,
  then compliance, then synthesis) can take 5-10+ minutes end-to-end.
  Integration tests will be slow; don't assume a hang, check `ollama ps`
  and the log's timestamps before concluding something is stuck.
- `qwen2.5:7b-instruct` can occasionally fail structured output generation
  (see Bug #2) — this is a real, if infrequent, model reliability issue to
  keep in mind, not just a one-off fluke.
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
