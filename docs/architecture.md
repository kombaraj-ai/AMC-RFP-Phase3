# Architecture

**AMC RFP & Portfolio Insight Orchestrator — Phase 01 (DEV)**

This document describes the system as actually implemented in `src/amc_orchestrator/`. For
day-to-day operational notes (how to resume work, known flakiness, milestone status), see
[`CLAUDE.md`](../CLAUDE.md) at the repo root — that file is a working log; this one is the
stable reference.

## The problem

Institutional investors and wealth managers send AMCs (Asset Management Companies) RFPs and
portfolio queries that require synthesizing three things that normally live in disjointed
systems: exact quantitative fund metrics, qualitative fund-manager narrative, and strict
regulatory compliance review — a process that manually takes days. This system automates that
synthesis end-to-end, with a self-correcting compliance loop instead of a single-pass pipeline,
so a non-compliant draft gets revised and re-checked automatically rather than escaping to the
client.

## High-level flow

Five agents run as nodes in a [Strands Agents](https://strandsagents.com) `Graph`:

```
quant_data_pull ──┬───────────────────────────────────┬─────────────┐
                   │                                     │             │
qual_narrative_pull┴──► compliance_check ──(needs_revision)──► revise_draft
                   │           │                                       │
                   │           └──(ready_to_synthesize)──► final_synthesis
                   │                                       ▲           ▲
                   └───────────────────────────────────────┴───────────┘
                          (quant + qual also feed revise_draft/
                           final_synthesis directly as grounding)

                   revise_draft ──(unconditional loop-back)──► compliance_check
```

`quant_data_pull` and `qual_narrative_pull` are the graph's entry points and run in parallel.
Everything downstream is gated by `compliance_check`'s verdict via the condition functions in
`workflows/routing.py`.

## The five agents

| Node name             | Module                          | Role                                                              | Temp |
|------------------------|----------------------------------|---------------------------------------------------------------------|------|
| `quant_data_pull`      | `agents/quant_agent.py`         | Pulls exact fund metrics via the `get_fund_performance` tool.       | 0.2  |
| `qual_narrative_pull`  | `agents/qual_agent.py`          | Retrieves manager commentary via the `search_fund_commentary` tool (RAG). | 0.2  |
| `compliance_check`     | `agents/compliance_agent.py`    | LLM-as-a-Judge; scores the draft against the compliance rubric, returns a structured `ComplianceVerdict`. | 0.15 |
| `revise_draft`         | `agents/revisor_agent.py`       | Rewrites a REJECTED draft per the verdict's `suggested_edits` — never touches the numbers. | 0.2  |
| `final_synthesis`      | `agents/synthesizer_agent.py`   | Produces the final client-facing text — two branches, never blended. | 0.4  |

Temperatures are deliberately low for the judge/workers (consistency, less-flaky output) and
higher for the synthesizer (prose quality). All temperatures are configurable via `Settings`
(see [`user_guide.md`](user_guide.md)).

### `compliance_check`: LLM-as-a-Judge

Rather than a free-text critique, the compliance agent is built with
`Agent(structured_output_model=ComplianceVerdict)` (`schemas/compliance.py`):

```python
class ComplianceVerdict(BaseModel):
    status: Literal["APPROVED", "REJECTED"]
    violations: list[str]
    suggested_edits: str
    evaluated_text: str  # verbatim echo of the exact text judged
```

`evaluated_text` is a **mechanical copy task, not a summarization task** — on the first pass the
agent synthesizes a draft from quant+qual and judges that; on a re-check it judges the Revisor's
latest rewrite verbatim. Echoing the judged text back lets `final_synthesis` use the exact
compliant wording on the APPROVED path without having to reconstruct it, and lets `revise_draft`
know precisely what it's revising on the REJECTED path.

The rubric itself lives in one place, `config/compliance_rubric.py`, and is rendered into both
the agent's system prompt and [`compliance_rubric.md`](compliance_rubric.md) so they can't drift
apart. See that file for the five rules (no guarantees, mandatory past-performance disclaimer,
promissory-language flags, forward-looking-statement framing, risk contextualization).

### `final_synthesis`: two branches, never blended

The synthesizer's system prompt is explicit that it must check the compliance verdict's `status`
field exactly and pick one of exactly two branches:

- **APPROVED** → a full, structured client report (Quantitative Risk & Performance Metrics /
  Manager Strategy Commentary / Compliance Disclosures sections), built only from data already
  present in its context.
- **Anything else** (REJECTED, or a missing/malformed verdict) → respond with **exactly** the
  text of `ESCALATION_HOLDING_MESSAGE` (`config/messages.py`) and nothing else — no partial
  report, no meta-commentary.

This is the system's core safety invariant: unapproved content must never reach a client framed
as if it were compliant.

## Graph wiring (`workflows/graph_build.py`, `workflows/routing.py`)

Every downstream consumer gets a **direct edge** to the actual source of the data it needs
(quant, qual) rather than chaining through an intermediary, so `revise_draft` and
`final_synthesis` always have raw grounding straight from source — never a paraphrase —
regardless of how many times the compliance loop has run.

```python
builder.add_edge(quant, compliance)                                   # unconditional
builder.add_edge(qual, compliance)                                    # unconditional
builder.add_edge(quant, revisor, condition=needs_revision)
builder.add_edge(qual, revisor, condition=needs_revision)
builder.add_edge(compliance, revisor, condition=needs_revision)
builder.add_edge(quant, synthesizer, condition=ready_to_synthesize)
builder.add_edge(qual, synthesizer, condition=ready_to_synthesize)
builder.add_edge(compliance, synthesizer, condition=ready_to_synthesize)
builder.add_edge(revisor, compliance)                                  # unconditional loop-back
```

`needs_revision`/`ready_to_synthesize` (`workflows/routing.py`) count how many times
`compliance_check` has appeared in `state.execution_order` and inspect the latest
`ComplianceVerdict`:

- `needs_revision`: `False` if compliance hasn't run yet, `False` if `attempts >= max_attempts`,
  otherwise `True` iff the verdict is missing or `REJECTED`.
- `ready_to_synthesize`: `False` if compliance hasn't run yet, otherwise `not needs_revision`.

**Why all three incoming edges into `revise_draft`/`final_synthesis` share the same condition
function** (this was a real bug, found empirically): Strands' `Graph._is_node_ready_with_conditions`
schedules a node as soon as **any one** incoming edge from the just-completed batch is
satisfied — OR-semantics, not AND. `quant_data_pull`/`qual_narrative_pull` complete in the very
first batch. If their edges into `revise_draft`/`final_synthesis` were unconditional ("for
grounding"), those nodes would become ready immediately, running in parallel with
`compliance_check`'s *first* pass, before any verdict exists. The fix: every edge into those two
nodes — from quant, qual, *and* compliance — carries the identical condition function, and that
function short-circuits to `False` whenever `compliance_check` has not executed even once
(`attempts == 0`). Caught via a CLI run that showed all three nodes starting within ~1 second of
each other; see `routing.py`'s and `graph_build.py`'s module docstrings for the full account —
**do not simplify this back to per-edge conditions without re-reading them.**

## Termination — two layers

1. **Graceful (primary)**: `MAX_COMPLIANCE_ATTEMPTS` (default 3, `Settings.max_compliance_attempts`).
   Once `compliance_check` has run this many times, `needs_revision` forces `False` and
   `ready_to_synthesize` forces `True` — control routes to `final_synthesis` **even if the
   verdict is still REJECTED**, which then emits the escalation message per its second branch.
2. **Hard safety net**: `GraphBuilder.set_max_node_executions(settings.graph_max_node_executions)`
   (default 12). If this actually fires, the **whole graph fails with no output at all** — a
   Strands SDK requirement for cyclic graphs, not a design choice. The graceful layer must always
   resolve first; the hard ceiling exists only as a backstop against a routing-logic bug, not as
   a normal exit path.

`reset_on_revisit(True)` is set so `compliance_check` (and any node) starts with a clean executor
state on each re-entry, meaning each re-evaluation judges the current draft fresh rather than
accumulating conversation history across loop iterations.

## Known limitation: `StructuredOutputException` on `compliance_check`

`qwen2.5:7b-instruct` on Ollama occasionally fails to invoke its structured-output tool even
after Strands "forces" it. Strands node execution is fail-fast, so this exception propagates all
the way out of `graph(...)` as a raw Python exception, not a `FAILED` `GraphResult`.

**Two layers of mitigation, in order:**

1. **`_RetryingComplianceAgent`** (`agents/compliance_agent.py`) — a manual retry that, on
   `StructuredOutputException`, rolls the agent's conversation back to a clean slate and re-sends
   the same input, up to `Settings.compliance_structured_output_max_attempts` (default 3) total
   attempts, before letting the exception propagate.
2. **Graph-level try/except** — both `cli.py` and `api/routes/rfp.py` wrap `graph(question)` and
   call `workflows.result_extraction.summarize_exception(exc)` on failure, degrading to the same
   `ESCALATION_HOLDING_MESSAGE` a REJECTED-after-retries verdict would produce. Callers never see
   a raw exception or a 500.

**Root cause**: Strands "forces" the structured-output tool via `tool_choice`. Ollama's Strands
model integration (`strands/models/ollama.py`) explicitly does not support `tool_choice` and
silently ignores it (`UserWarning: A ToolChoice was provided to this provider but is not
supported and will be ignored`) — so on this DEV stack, "forcing" never actually forces
anything; only a generic text nudge remains as leverage, and the model is free to ignore that
too. This was confirmed to fail 3/3 attempts in one live run even with the retry above in place.
**This is treated as a known, parked DEV-only limitation**, not something actively being chased
further — `BedrockModel` (STAGING/PROD) supports real `tool_choice` forcing, so this exact
failure mode is expected to be far rarer there. See `CLAUDE.md`'s "Bug #2" section for the full
investigation log.

## Data layer

Two plain, Strands-free modules — unit-testable without an LLM, and shaped so a later
STAGING/PROD swap only needs to preserve their function signatures:

- **`data/sqlite_store.py`** — `fund_performance` table (ticker, fund_name, fund_category, nav,
  alpha, beta, sharpe_ratio, standard_deviation, sortino_ratio, r_squared, returns_1y,
  returns_3y). `ensure_seeded()` is insert-if-missing against a persistent file (not
  delete-and-recreate), safe to call from the CLI, the API's `lifespan`, and tests alike. Four
  mock funds are seeded — see [`user_guide.md`](user_guide.md) for the full data.
- **`data/chroma_store.py`** — a persistent on-disk ChromaDB collection of fund-manager
  commentary, seeded with deterministic IDs (`ensure_seeded()` upserts, never duplicates).
  `search_commentary()` does a vector similarity query.

Both are wrapped by thin `@tool`-decorated functions (`tools/quant_tools.py`,
`tools/qual_tools.py`) that agents call — the wrappers add nothing but the tool boundary, so all
real logic stays unit-tested at the data-layer level.

## Model provider abstraction

`config/model_factory.py` is the **only** module that imports a concrete Strands model class:

```python
def get_model(settings: Settings, *, temperature: float) -> Model:
    if settings.is_local_llm:            # environment == "dev"
        return OllamaModel(host=settings.ollama_host, model_id=settings.ollama_model_id, temperature=temperature)
    return BedrockModel(model_id=settings.bedrock_model_id, region_name=settings.aws_region, temperature=temperature)
```

Every agent constructor calls `get_model(settings, temperature=...)` and never imports
`OllamaModel`/`BedrockModel` directly, so promoting DEV → STAGING/PROD is a config change
(`ENVIRONMENT=staging` + AWS credentials), not a code change to any agent.

## Observability

- **`observability/logging_setup.py`** — structlog configured once per process
  (`configure_logging`), JSON renderer in non-dev environments, a human-friendly console
  renderer in dev. `bind_trace_context()`/`clear_trace_context()` thread a `trace_id`/`request_id`
  pair through `contextvars` so every log line for one request — across every agent and tool call
  — carries the same correlation IDs, without any agent code having to pass them explicitly.
- **`observability/hooks.py`** — `LoggingHookProvider`, attached to every agent, logs
  invocation-start/-complete and tool-call-start/-complete as structured events, purely via
  Strands hooks (`BeforeInvocationEvent`, `AfterInvocationEvent`, `BeforeToolCallEvent`,
  `AfterToolCallEvent`) — zero business-logic changes required to get per-node timing and
  tool-call visibility.

## API layer (Milestone 8)

`api/main.py` builds the FastAPI app via `create_app()`: `lifespan` (not the deprecated
`@app.on_event`) seeds SQLite/Chroma on startup, CORS is read from
`settings.cors_origin_list`, `GET /health` reports liveness, and `GET /health/ready` reports
readiness (see below). `api/routes/rfp.py` exposes `POST /api/v1/rfp`, applying the **exact
same** try/except → `summarize_exception()` pattern as `cli.py` — this is deliberate, not
incidental: without it, a flaky `compliance_check` would surface to HTTP callers as an unhandled
500 instead of the intended graceful escalation. See [`user_guide.md`](user_guide.md) for
request/response shapes and examples.

### Readiness vs. liveness (Milestone 10)

`GET /health` only answers "is the process alive" — it always returns 200. `GET /health/ready`
(`observability/readiness.py`) answers the more useful operational question, "can this process
currently serve a request": in DEV, whether Ollama is reachable over TCP
(`settings.ollama_host`); in every environment, whether the SQLite/Chroma data directories are
writable. It returns `200 {"ready": true, ...}` when every check passes, `503 {"ready": false,
...}` otherwise — an orchestrator should route traffic away from an instance failing readiness,
distinct from `/health`, which should keep reporting the process itself is fine. The Ollama
reachability check is also reused (not duplicated) by
`tests/integration/conftest.py` to auto-skip integration tests when Ollama isn't up.

## Result translation (`workflows/result_extraction.py`)

Both the CLI and the API need to translate Strands' internal `GraphResult` shape (`NodeResult`
wrapping `AgentResult`, `execution_order` as `GraphNode` objects, etc.) into something
caller-friendly. `RfpOutcome` (a frozen dataclass) is that shared translation target:

```python
@dataclass(frozen=True)
class RfpOutcome:
    succeeded: bool
    response_text: str
    compliance_attempts: int
    escalated: bool
    graph_status: str
```

`summarize_result(result)` builds this from a real `GraphResult`; `summarize_exception(exc)`
builds the safe-escalation equivalent when `graph(...)` raised outright. Both `cli.py` and
`api/routes/rfp.py` call whichever applies and never touch Strands-internal types directly.

## Repository map

```
src/amc_orchestrator/
├── main.py                        # amc-orchestrator console script → uvicorn launcher
├── cli.py                         # direct graph invocation (pre-API smoke testing)
├── config/
│   ├── settings.py                # Settings(BaseSettings), get_settings() cached singleton
│   ├── model_factory.py           # get_model() — only place that imports OllamaModel/BedrockModel
│   ├── compliance_rubric.py       # single source of truth for the rubric text
│   └── messages.py                # ESCALATION_HOLDING_MESSAGE, shared safe-fallback text
├── data/
│   ├── sqlite_store.py            # quant data (SQLite dev, Snowflake/Redshift-shaped staging+)
│   └── chroma_store.py            # qual data (persistent Chroma dev, OpenSearch-shaped staging+)
├── tools/
│   ├── quant_tools.py             # @tool get_fund_performance
│   └── qual_tools.py              # @tool search_fund_commentary
├── schemas/
│   └── compliance.py              # ComplianceVerdict
├── agents/
│   ├── quant_agent.py  qual_agent.py  compliance_agent.py  revisor_agent.py  synthesizer_agent.py
├── observability/
│   ├── logging_setup.py  hooks.py
│   └── readiness.py                # check_readiness() — GET /health/ready backing logic
├── workflows/
│   ├── routing.py                 # needs_revision / ready_to_synthesize condition functions
│   ├── graph_build.py             # build_rfp_graph(settings)
│   └── result_extraction.py       # RfpOutcome, summarize_result, summarize_exception
└── api/
    ├── main.py                    # create_app(), lifespan, CORS, /health, /health/ready
    └── routes/rfp.py              # POST /api/v1/rfp
```
