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
- **DEV LLM**: `MODEL_PROVIDER` env var, default `ollama` (`qwen2.5:7b-instruct`,
  chosen over llama3.2 for reliable structured-output/tool-calling; already
  pulled locally). Can opt into `bedrock` per-run instead (needs AWS
  credentials, real cost) for use cases where local CPU-only generation is
  too slow — see `Settings.effective_model_provider` in "Conventions"
  below and `docs/user_guide.md`'s "Switching model provider" section.
- **DEV data**: SQLite (`local_dev.db`, gitignored) for quant metrics,
  persistent on-disk ChromaDB (`data/chroma/`, gitignored) for qual RAG
- **STAGING/PROD** (not built yet): always `BedrockModel` via
  `config/model_factory.py` regardless of `MODEL_PROVIDER` — zero
  agent-code changes required, only `ENVIRONMENT` + AWS credentials
- **API**: FastAPI (`api/main.py` + `api/routes/rfp.py`, Milestone 8 - `POST
  /api/v1/rfp`, `GET /health`, `GET /health/ready`; start via `uv run python
  -m amc_orchestrator.main` or the `amc-orchestrator` console script)
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
milestones. **All 10 milestones are now checked off.**

**Post-M10 addition (same session, 2026-07-11)**: DEV can now opt into
Bedrock per-run instead of Ollama (`MODEL_PROVIDER=bedrock` +
`Settings.effective_model_provider` - see "Conventions" below), for use
cases where local CPU-only Ollama generation is too slow. This directly
mitigates the Bug #2 flakiness for whoever opts in (Bedrock/Claude
supports real `tool_choice` forcing), without waiting on a full STAGING
environment. Unit-tested (`test_settings.py`, `test_model_factory.py`,
`test_readiness.py`'s new dev+bedrock case) and live-smoke-tested
(`/health/ready` confirmed to skip its Ollama check when
`MODEL_PROVIDER=bedrock`).

**Verified against real Bedrock, 2026-07-11**: the user ran the CLI with
`MODEL_PROVIDER=bedrock` (`anthropic.claude-3-5-sonnet-20241022-v2:0`,
`us-east-1`) against the INC2 low-risk query - `graph_status=completed`,
`compliance_attempts=1`, `escalated=False`, **11.64 seconds total**
(vs. 5-10+ minutes on Ollama). `compliance_check` returned
`stop_reason=tool_use` - Claude invoked `ComplianceVerdict` natively, no
forced-retry needed at all, confirming the Bug #2 root-cause fix in
practice, not just in theory. Full node-by-node trace, timing table, and
analysis: [`docs/sample_invocation_walkthrough.md`](docs/sample_invocation_walkthrough.md).

Natural next steps from here, none yet scoped: broader hardening
(readiness when Bedrock/AWS creds are misconfigured, load testing), CI
wiring (a GitHub Actions workflow was never set up - `uv run pytest
tests/unit` is a natural fast gate, integration tests would need a hosted
Ollama runner or `MODEL_PROVIDER=bedrock` with CI-provisioned AWS
credentials), or a full STAGING environment setup exercised end-to-end.

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
  concrete model class — this is what makes switching provider (DEV's
  Ollama/Bedrock toggle, or DEV→STAGING/PROD) a config change, not a code
  change. **Provider selection is `Settings.model_provider`
  (`"ollama"`/`"bedrock"`, default `"ollama"`), resolved through
  `Settings.effective_model_provider`** — DEV respects `model_provider`
  (so a run can opt into Bedrock without a separate environment, e.g. when
  local Ollama generation is too slow for a given use case); STAGING/PROD
  always force `"bedrock"` regardless of it. Never branch on `environment`
  directly for provider decisions — always go through
  `effective_model_provider` (see `observability/readiness.py` for the
  other real consumer, which skips its Ollama-reachability check
  accordingly).
- Data-layer modules (`data/sqlite_store.py`, `data/chroma_store.py`) and
  tool wrappers (`tools/*.py`) are deliberately Strands-free/thin so they're
  unit-testable without an LLM.
- `.env.dev` is gitignored (only `.env.dev.example` is committed) even
  though DEV holds no real secrets — kept consistent with the STAGING/PROD
  habit.
- Git commits are one per milestone with a consistent message style — check
  `git log` for the pattern before committing new work.

## Phase 02 — Deployment to Amazon Bedrock AgentCore

Started 2026-07-11, session in progress (not yet committed to git as of the
last session - see "Uncommitted work" below). Full detail:
`infra/terraform/README.md` (infra) and `docs/architecture.md`'s "Phase 02"
section (app-code). Plan file (currently holds the app-code follow-on
plan, the most recent of two plans this phase used - the original
Terraform-only plan's content lives on in this log, not in that file):
`C:\Users\komba\.claude\plans\calm-sprouting-nebula.md`.

### Current status (as of last session, 2026-07-11)

- [x] Terraform (`infra/terraform/`) - all modules written, `fmt`/`validate`
      clean on all 3 environments.
- [x] Bootstrap (state bucket) applied to real AWS.
- [x] Dev pass 1 (`enable_knowledge_base=false`, `enable_agent_runtime=false`)
      applied to real AWS and **live-verified** resource-by-resource (not
      just `terraform state list`) - IAM, ECR, DynamoDB, OpenSearch
      collection, S3, both Lambda stubs (real `invoke`), Gateway + targets
      (`READY`), Memory + strategy (`ACTIVE`), CloudWatch dashboard/alarms.
      Two real bugs found via live AWS checks and fixed: OpenSearch
      name-length overflow, double-prefixed CloudWatch alarm names.
- [x] App-code follow-on task (entrypoint, DynamoDB/Knowledge-Base data-layer
      swap, Dockerfile) - written and verified: 64 unit tests pass, a real
      local `uvicorn` + real Ollama end-to-end `/invocations` call
      succeeded.
- [x] `docker build`/`push`, `enable_agent_runtime = true` + apply, and a
      live end-to-end `invoke_agent_runtime` smoke test - all done and
      **live-verified against real AWS, 2026-07-12**. Three real bugs found
      and fixed along the way (see below); the first two would have blocked
      *every* invocation of the deployed Runtime, not just this smoke test.
      Pass 2 (`enable_knowledge_base = true`), staging/prod applies, real
      document ingestion, and the deferred Gateway-routed tools / AgentCore
      Memory graph integration remain **not done**.

**Real bugs found live this session, all fixed and re-verified, 2026-07-12**:
1. **Dockerfile missing README.md**: `pyproject.toml` declares `readme =
   "README.md"`, but the Dockerfile only `COPY`'d `pyproject.toml`/`uv.lock`
   before `uv sync --no-install-project` - hatchling's build backend fails
   without the readme file present even for that no-install-project pass.
   Fixed by adding `README.md` to that `COPY` line. First-ever real `docker
   build` of this Dockerfile - this was always going to fail, no prior
   session had actually run it.
2. **Deployed dev Runtime defaulted to Ollama, unreachable from AWS**:
   `Settings.effective_model_provider` deliberately respects `model_provider`
   (default `"ollama"`) whenever `environment == "dev"`, so a *local* dev
   run can opt into Bedrock - but the *deployed* Runtime container also sets
   `ENVIRONMENT=dev` (same env-var name, different purpose), and
   `infra/terraform/environments/dev/main.tf`'s `agentcore_runtime` module
   never set `MODEL_PROVIDER`. Every invocation failed with `ConnectError:
   All connection attempts failed` (trying to reach `localhost:11434`
   inside the container). Fixed by hardcoding `MODEL_PROVIDER = "bedrock"`
   in that module's `environment_variables` - staging/prod don't need this
   since `environment != "dev"` already forces Bedrock for them via
   `effective_model_provider`.
3. **`bedrock_model_id` (`anthropic.claude-3-5-sonnet-20241022-v2:0`) had
   reached end-of-life** on Bedrock (a real `invoke_agent_runtime` call
   returned `ResourceNotFoundException`) - confirmed via
   `bedrock:ListFoundationModels`/`GetFoundationModel` that current-gen
   Anthropic models on this account now require `INFERENCE_PROFILE`
   invocation, not `ON_DEMAND`. Rather than wire up the extra
   inference-profile IAM ARNs, switched `bedrock_model_id` to
   `amazon.nova-lite-v1:0` instead (user's choice) - `ON_DEMAND`-invokable,
   no profile complexity, cheaper. Verified it's sufficient for this
   project's structured-output need: `strands/models/bedrock.py`'s
   `BedrockModel.structured_output` only ever requests
   `tool_choice={"any": {}}` (force *some* tool use - never a named-tool
   force, since only one tool spec is ever passed), and Nova supports
   `"any"` tool choice via the Converse API. `locals.tf`'s
   `bedrock_model_arns` and both the runtime/KB IAM policies were updated
   to the new model ARN.

**Live end-to-end proof, 2026-07-12** (`invoke_agent_runtime` against
`arn:aws:bedrock-agentcore:us-east-1:766354255780:runtime/amc_orchestrator_dev_agent_runtime-X1c5y89vze`,
the INC2 low-risk query): `succeeded=true, graph_status=completed,
compliance_attempts=3, escalated=true` - a well-formed graceful escalation,
not a crash, and the *expected* outcome given `enable_knowledge_base` is
still `false` (no commentary data exists yet for `qual_narrative_pull` to
retrieve, so REJECTED verdicts are honest, not a bug). This proves the
Runtime, its IAM role, DynamoDB self-seeding (`runtime_entrypoint.py`'s
`lifespan` hook), and real Bedrock invocation all genuinely work in AWS -
a real APPROVED completion is expected once pass 2 lands.

### Immediate next step (resume here)

1. Pass 2: `enable_knowledge_base = true` in
   `infra/terraform/environments/dev/terraform.tfvars` (after adding the
   applier's principal to `additional_data_access_principals`), apply -
   creates the vector index + real Bedrock Knowledge Base. Real document
   ingestion (S3 upload + `start_ingestion_job`) is a further, separate
   step after that - needed before a real APPROVED completion is possible
   end-to-end.
2. Re-run the same `invoke_agent_runtime` smoke test after pass 2 +
   ingestion to confirm a real compliant synthesized report, not just the
   escalation path.
3. Staging/prod applies (all three real bugs above are dev-tfvars-only
   fixes so far - `environments/staging/`/`environments/prod/` still
   reference the same end-of-life Claude model ID and will need the same
   `bedrock_model_id`/IAM update before their eventual first apply,
   though they don't have the `MODEL_PROVIDER` issue since
   `environment != "dev"` already forces Bedrock for them).
4. The deliberately-deferred Gateway-routed tools / AgentCore Memory graph
   integration.
5. **Uncommitted work**: `git status` shows the Terraform/app-code files
   from this phase plus this session's Dockerfile/dev-tfvars fixes, not yet
   committed (Phase 01's convention is one commit per milestone - worth
   committing in logical chunks rather than one giant commit, but wasn't
   asked to do so yet this session).

Provisions every AWS resource the deployed system needs (AgentCore
Runtime/Gateway/Memory, ECR, DynamoDB, OpenSearch Serverless + Bedrock
Knowledge Base, Lambda tool stubs, IAM, observability) via modular
Terraform (`infra/terraform/`), one root module per environment
(`environments/{dev,staging,prod}/`), Terraform v1.15.7. Confirmed all
required resource types exist natively in `hashicorp/aws` (no
CloudFormation/awscc needed) by reading the provider's actual source docs,
following this project's own M0 precedent of verifying against real
sources instead of guessing from blog posts.

**Scope is Terraform/infra only.** The app-code changes needed to actually
run in AgentCore — an AgentCore-compliant HTTP entrypoint, swapping
`data/sqlite_store.py`/`data/chroma_store.py` for DynamoDB/OpenSearch, a
real Dockerfile — are a separate, not-yet-started follow-on task. This
also means the `.env.staging.example`/`.env.prod.example` comments
guessing "Snowflake/Redshift" and "Amazon OpenSearch" as the eventual
data-layer swap target are now stale/wrong — the actual target is
DynamoDB + OpenSearch Serverless, fixed in those files as part of this
milestone.

**Locked-in architecture decisions** (see `infra/terraform/README.md` for
the full reasoning on each):
- Single AWS account; dev/staging/prod isolated by naming + separate
  Terraform state, not separate AWS accounts.
- AgentCore Runtime network mode `PUBLIC`, not `VPC` — `VPC` mode hits a
  confirmed open AWS bug (ENIs get locked, `terraform destroy` hangs
  forever; `terraform-provider-aws` issue #45099, closed "not planned").
- DynamoDB (pay-per-request) replaces SQLite for quant metrics.
- Gateway/Runtime auth is AWS IAM (SigV4), not Cognito/JWT.
- `aws_bedrockagentcore_agent_runtime` needs a container image that
  doesn't exist yet at infra-build time — Terraform creates the ECR repo
  only; the runtime resource is applied in a documented later pass once an
  image is pushed out-of-band. Terraform never runs `docker build`.
- OpenSearch Serverless has no native Terraform vector-index resource in
  `hashicorp/aws` (confirmed against AWS's own "Deploy Amazon OpenSearch
  Serverless with Terraform" blog, which stops at collection+policies) —
  index creation uses the `opensearch-project/opensearch` community
  provider instead, signed for AOSS specifically
  (`aws_signature_service = "aoss"`, not its "es" default).
- A dependency cycle surfaced during build: `modules/iam` needs the
  OpenSearch collection's ARN to scope its role policies, but the
  collection's data-access policy needs those same roles' ARNs as its
  `Principal` list. Fixed by splitting the data-access policy into its own
  `modules/opensearch-access-policy`, applied after both `modules/iam` and
  `modules/opensearch-serverless` — worth knowing before "simplifying" the
  module list back down.
- Every environment applies in up to three passes (`enable_knowledge_base`
  and `enable_agent_runtime` variables, both default `false`) because a
  handful of resources genuinely can't exist before their prerequisites
  do — see `infra/terraform/README.md`'s "three phases" section before
  assuming a single `terraform apply` should create everything.

**Verified so far**: `terraform fmt -recursive -check` clean and
`terraform validate` (no AWS credentials needed) passes on `bootstrap/`
and all three `environments/*` root modules — confirms every resource
argument used against the real provider schema (provider resolved to
`hashicorp/aws` v6.54.0, `opensearch-project/opensearch` v2.3.2,
`hashicorp/archive` v2.8.0).

**Real `terraform plan` run against the user's AWS account (dev, pass 1),
2026-07-11**: 21 resources planned to add, 0 to change/destroy — the
overall graph and module wiring is sound. Caught one real bug `validate`
couldn't: `aws_opensearchserverless_collection`/`_security_policy`/
`_access_policy` names are capped at 32 characters by AWS, and
`amc-orchestrator-dev-kb-vectors` plus the `-enc`/`-net`/`-data` policy
suffixes exceeded it (35-36 chars). Fixed in
`modules/opensearch-serverless/main.tf`: `collection_name` is now built
with a guaranteed-safe budget (27 chars, leaving room for the longest
`-data` suffix) and a short suffix (`-vec` not `-kb-vectors`); if
`name_prefix` is long enough that this would still overflow (e.g.
`staging`'s longer name), a 6-char hash of the untruncated name is
appended rather than naively `substr()`-truncating — a naive truncation
risks two environments colliding if truncation cuts off the exact part
that made them different. Re-`validate`d clean after the fix; **not yet
re-`plan`ned** against real AWS to confirm this specific error is fully
resolved (the next natural verification step, before applying for real).

**Pass 1 applied to real AWS (dev), 2026-07-11 - fully live-verified, not
just planned**: IAM roles (trust policies confirmed correctly scoped per
service principal), ECR (empty, scan-on-push on), DynamoDB (`ACTIVE`,
`PAY_PER_REQUEST`), OpenSearch Serverless collection (`ACTIVE`, name fits
the 32-char limit after the fix above), S3 docs bucket, both Lambda tool
stubs (real `invoke` calls returned the expected placeholder JSON),
AgentCore Gateway + both targets (`READY`), AgentCore Memory + semantic
strategy (`ACTIVE`), CloudWatch dashboard/alarms - all confirmed via live
`aws`/`boto3` calls against the account, not just `terraform state list`.
Found and fixed one more real bug this way: the two Lambda-error alarms
were double-prefixed (`modules/observability/main.tf` re-prepending
`name_prefix` onto `each.value`, which was already the fully-prefixed
Lambda function name) - `terraform plan` after the fix showed exactly
`2 to add, 0 to change, 2 to destroy`, applied clean.

**App-code follow-on task done, 2026-07-11** (the work this unblocked):
an AgentCore Runtime entrypoint, a DynamoDB/Bedrock-Knowledge-Base data-layer
swap, and a Dockerfile - closing the gap that had `enable_agent_runtime`
gated off. Scope deliberately kept smaller than it could have been (user
confirmed): agents still call `get_fund_performance`/`search_fund_commentary`
as regular in-process `@tool` functions, just repointed at DynamoDB/a
Bedrock Knowledge Base instead of SQLite/Chroma - the Gateway's Lambda
targets stay placeholders and AgentCore Memory stays unused by the graph,
both a separate, larger follow-on.

- `config/settings.py`: `data_backend`/`effective_data_backend` added,
  mirroring `model_provider`/`effective_model_provider` exactly (DEV can
  opt in, STAGING/PROD always use `"aws"`).
- New `data/dynamodb_store.py`, `data/knowledge_base_store.py` (calls
  Bedrock's managed `Retrieve` API against the Knowledge Base Terraform
  already built, not hand-rolled OpenSearch k-NN + our own embedding
  calls), and thin dispatch facades `data/quant_store.py`/`data/qual_store.py`
  - only 4 existing files touched to call the facade instead of the
  concrete store (`tools/quant_tools.py`, `tools/qual_tools.py`, `cli.py`,
  `api/main.py`); `sqlite_store.py`/`chroma_store.py` themselves untouched.
- New `src/amc_orchestrator/runtime_entrypoint.py`
  (`bedrock_agentcore.runtime.BedrockAgentCoreApp`, `@app.entrypoint`),
  reusing `build_rfp_graph`/`summarize_result`/`summarize_exception`
  exactly as `cli.py`/`api/routes/rfp.py` already do - no new translation
  logic, same resilience contract.
- New repo-root `Dockerfile` - `linux/arm64` (AgentCore Runtime requires
  Graviton), `uv`-based, matching Strands' own AgentCore deployment guide's
  pattern.
- `infra/terraform/modules/agentcore-runtime` + all three `environments/*/main.tf`:
  added `BEDROCK_KNOWLEDGE_BASE_ID` to the runtime's `environment_variables`.

**Verified for real, not just unit-tested**: `uv run python -m pytest
tests/unit -q` - **64 passed**. Then a live local smoke test:
`uv run python -m uvicorn amc_orchestrator.runtime_entrypoint:app` really
running, `GET /ping` returning `Healthy`, a missing-`prompt` payload
correctly rejected, and **one real end-to-end `POST /invocations` call
against real Ollama actually completing** (`succeeded=true,
escalated=false, graph_status=completed`, a real compliant synthesized
report for the INC2 query) - proof the entrypoint genuinely works through
the real AgentCore HTTP contract, not just through mocks. `docker build
--platform linux/arm64 ...` was **not verified** - Docker Desktop's daemon
wasn't running on this machine this session; the Dockerfile itself is
unverified by an actual build, flagged rather than assumed working.

**Environment quirk found, worth knowing**: on this machine, `uv run
pytest ...` (the `.exe` console-script launcher) misresolves
`amc_orchestrator` imports to a sibling `Phase-01` directory for some
(not all) test modules - a pre-existing, unrelated launcher issue, not
caused by any code here. `uv run python -m pytest ...` does not have this
problem and resolves correctly every time - **use that form, not
`uv run pytest`, on this machine.**

Natural next step: push a real image to the ECR repo pass 1 already
created, set `enable_agent_runtime = true` (and `container_image_uri`),
apply - the first real, invokable AgentCore Runtime. Real AWS action
(image push + apply), should be confirmed with the user first, not
auto-run.
