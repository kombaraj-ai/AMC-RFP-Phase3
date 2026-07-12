# Architecture

**AMC RFP & Portfolio Insight Orchestrator — Phase 01 (DEV) + Phase 02 (AWS deployment)**

This document describes the system as actually implemented in `src/amc_orchestrator/` (Phase 01)
and the AWS infrastructure that runs it in the cloud, as actually implemented in
`infra/terraform/` (Phase 02). For day-to-day operational notes (how to resume work, known
flakiness, milestone status), see [`CLAUDE.md`](../CLAUDE.md) at the repo root — that file is a
working log; this one is the stable reference.

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
    if settings.effective_model_provider == "ollama":
        return OllamaModel(host=settings.ollama_host, model_id=settings.ollama_model_id, temperature=temperature)
    return BedrockModel(model_id=settings.bedrock_model_id, region_name=settings.aws_region, temperature=temperature)
```

Every agent constructor calls `get_model(settings, temperature=...)` and never imports
`OllamaModel`/`BedrockModel` directly, so switching provider is always a config change, never a
code change to any agent.

**Provider selection is a separate axis from `environment`.** `Settings.model_provider`
(`"ollama"` | `"bedrock"`, default `"ollama"`) is the developer-facing switch; `environment`
still selects which `.env.<environment>` file loads. `Settings.effective_model_provider`
resolves the two:

```python
@property
def effective_model_provider(self) -> Literal["ollama", "bedrock"]:
    if self.environment != "dev":
        return "bedrock"          # STAGING/PROD: compliance requirement, not a preference
    return self.model_provider    # DEV: respects the developer's choice
```

DEV defaults to Ollama (free, fully local) but can opt into Bedrock per-run
(`MODEL_PROVIDER=bedrock` + AWS credentials) for use cases where CPU-only local generation is
too slow - without needing a separate environment or any code change. STAGING/PROD always use
Bedrock regardless of `model_provider`, since that constraint is about where the system is
deployed, not a runtime preference. See [`user_guide.md`](user_guide.md) for how to switch it.

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
currently serve a request": whether Ollama is reachable over TCP
(`settings.ollama_host`) **only when `effective_model_provider == "ollama"`** — this check is
skipped entirely when Bedrock is the active provider, in DEV or otherwise, since pinging a local
Ollama port would be meaningless there; and in every environment, whether the SQLite/Chroma data
directories are writable. It returns `200 {"ready": true, ...}` when every check passes, `503 {"ready": false,
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

## Phase 02 — AWS deployment infrastructure

Everything above describes the application as it runs today (DEV, local-first). Phase 02 adds
the AWS infrastructure to run it on **Amazon Bedrock AgentCore** instead — provisioned entirely
by modular Terraform under `infra/terraform/`, one root module per environment
(`environments/{dev,staging,prod}/`), zero manual console steps. Full operational detail (exact
apply commands, variable reference, troubleshooting) lives in
[`infra/terraform/README.md`](../infra/terraform/README.md); this section covers the shape of it
and why it's built this way, in the same spirit as the rest of this document.

**This phase is infra-only.** It provisions AWS resources; it does not change any code under
`src/amc_orchestrator/`. The app still runs exactly as described above (SQLite/Chroma,
`sqlite_store.py`/`chroma_store.py`) until a separate, not-yet-started follow-on task builds an
AgentCore-compliant entrypoint, swaps the data layer to the resources below, and containerizes
the app for ECR.

### What gets provisioned

| Concern | Resource(s) | Module |
|---|---|---|
| Agent execution | `aws_bedrockagentcore_agent_runtime` (container-based, `PUBLIC` network mode) | `agentcore-runtime` |
| Tool exposure | `aws_bedrockagentcore_gateway` + one `gateway_target` per tool, IAM-auth'd | `agentcore-gateway` |
| Conversation memory | `aws_bedrockagentcore_memory` + a semantic strategy scoped per session | `agentcore-memory` |
| Quant metrics | DynamoDB, `PAY_PER_REQUEST`, `ticker` as the sole key — mirrors `sqlite_store.py`'s schema | `dynamodb` |
| Qual vector store | OpenSearch Serverless collection (`VECTORSEARCH`) + its security/access policies | `opensearch-serverless`, `opensearch-access-policy` |
| Qual RAG | Bedrock Knowledge Base + S3 data source, backed by the collection above | `knowledge-base`, `s3-kb-docs` |
| Tool compute | Stub Lambda functions behind the Gateway targets (placeholder logic — see below) | `lambda-tools` |
| Container registry | ECR repo for the runtime's image (Terraform never builds/pushes into it) | `ecr` |
| Access control | One IAM role per AWS-service consumer (runtime, gateway, lambda, knowledge base) | `iam` |
| Observability | Log groups, a CloudWatch dashboard, Lambda-error/DynamoDB-throttle alarms | `observability` |

### Three architectural decisions worth knowing before touching this code

1. **`PUBLIC` network mode, not `VPC`.** `aws_bedrockagentcore_agent_runtime` in `VPC` mode
   creates ENIs that AWS locks with an "agentic_ai" owner and never releases, so
   `terraform destroy` hangs forever on the resulting VPC/subnet/ENI cycle — a confirmed,
   AWS-side, "not planned" limitation
   ([terraform-provider-aws#45099](https://github.com/hashicorp/terraform-provider-aws/issues/45099)),
   not something a smarter Terraform config can route around. Every module here uses `PUBLIC`
   instead; access to DynamoDB/OpenSearch is scoped by IAM and the OpenSearch data-access policy,
   not network isolation. This mirrors how `effective_model_provider` elsewhere in this system
   is a deliberate, documented trade-off rather than an unexamined default — see "Model provider
   abstraction" above for the same pattern applied to a different decision.
2. **The vector index is created by a second Terraform provider, in a second apply pass.**
   `hashicorp/aws` has no resource for an OpenSearch Serverless *index* (only the collection and
   its policies) — confirmed against AWS's own Terraform deployment walkthrough for OpenSearch
   Serverless, which stops at the collection. `modules/opensearch-index` uses the
   `opensearch-project/opensearch` community provider instead, signed specifically for AOSS
   (`aws_signature_service = "aoss"`, not the provider's `"es"` default), against the collection's
   real endpoint — which only exists after a first apply. `modules/knowledge-base` depends on that
   index existing too (the Bedrock Knowledge Base resource references it by name, it doesn't
   create it). Both are gated behind `enable_knowledge_base` (default `false`) for exactly this
   reason — see the README's "three phases" section.
3. **`modules/iam` and the OpenSearch data-access policy would otherwise form a cycle.** IAM's
   role policies need the collection's ARN to scope their `aoss:*` statements; the collection's
   data-access policy needs those same roles' ARNs as its `Principal` list. Resolved by splitting
   the access policy into its own `modules/opensearch-access-policy`, applied after both `iam` and
   `opensearch-serverless` — a deliberate module boundary, not an accident of ordering.

### The app-code follow-on: AgentCore entrypoint + DynamoDB/Knowledge Base data layer

The gap called out above — no entrypoint, no Dockerfile, no cloud-backed data layer — is closed.
Scope was deliberately kept smaller than it could have been: agents still call
`get_fund_performance`/`search_fund_commentary` as regular in-process `@tool` functions, exactly
as in Phase 01, just repointed at DynamoDB/a Bedrock Knowledge Base instead of SQLite/Chroma.

- **`config/settings.py`**: `data_backend`/`effective_data_backend` mirror
  `model_provider`/`effective_model_provider` exactly (see "Model provider abstraction" above) —
  DEV can opt in, STAGING/PROD always resolve to `"aws"`.
- **`data/dynamodb_store.py`** — same `ensure_seeded`/`fetch_fund_performance` shape as
  `sqlite_store.py`, converting DynamoDB's `Decimal` to `float` before returning so
  `tools/quant_tools.py`'s `json.dumps(row)` keeps working unchanged.
- **`data/knowledge_base_store.py`** — calls Bedrock's managed `Retrieve` API against the
  Knowledge Base Terraform already provisions, rather than hand-rolling raw OpenSearch k-NN
  queries plus our own embedding calls; the KB resource exists specifically to do that
  end-to-end. `ensure_seeded` here is a deliberate no-op (KB ingestion is an S3-upload +
  `start_ingestion_job` operation, not safe to run implicitly on every app startup).
- **`data/quant_store.py`/`data/qual_store.py`** — thin facades dispatching on
  `effective_data_backend`, the only place that chooses between the local and AWS store. Only 4
  existing files were touched to call the facade instead of the concrete store directly
  (`tools/quant_tools.py`, `tools/qual_tools.py`, `cli.py`, `api/main.py`) —
  `sqlite_store.py`/`chroma_store.py` themselves are untouched.
- **`runtime_entrypoint.py`** — `bedrock_agentcore.runtime.BedrockAgentCoreApp`,
  `@app.entrypoint` reading `payload["prompt"]`, reusing `build_rfp_graph` and
  `summarize_result`/`summarize_exception` exactly as `cli.py`/`api/routes/rfp.py` already do — no
  new translation logic, the same never-crash resilience contract. Implements the HTTP contract
  AgentCore Runtime requires (`POST /invocations`, `GET /ping`), confirmed against Strands' own
  AgentCore deployment guide.
- **`Dockerfile`** (repo root) — `linux/arm64` (AgentCore Runtime runs on Graviton, not optional),
  `uv`-based. No `environments/.env.*` file is baked into the image — Terraform's
  `agent_runtime_artifact.environment_variables` sets real process environment variables
  directly, and `Settings` reads those with no env file needed.

**Confirmed working end-to-end, not just unit-tested**: a real local `uv run python -m uvicorn
amc_orchestrator.runtime_entrypoint:app` smoke test — `GET /ping` healthy, a missing-`prompt`
payload correctly rejected, and one real `POST /invocations` call against real Ollama actually
completing (`succeeded=true`, a real compliant synthesized report). `docker build --platform
linux/arm64` itself was not verified in that session (Docker Desktop's daemon wasn't running) —
flagged as unverified rather than assumed working; worth doing before trusting the image builds.

### What's still a placeholder

`modules/lambda-tools` creates real, invokable Lambda functions wired into the Gateway, but their
handler code is still a trivial stub (`return {"status": "not_implemented", ...}`) — real
Gateway-routed tool logic and wiring AgentCore Memory into the graph (so conversation state
persists cross-turn) were explicitly deferred, a separate and larger follow-on, not part of the
work described just above. `aws_bedrockagentcore_agent_runtime` itself is still gated behind
`enable_agent_runtime` (default `false`) until a real image built from the new `Dockerfile` is
pushed to the ECR repo `modules/ecr` creates — Terraform deliberately never runs `docker build`.

### Testing the deployed Runtime: Streamlit's SigV4-backed Runtime mode

`src/amc_orchestrator/ui/streamlit_app.py` (see "Running via the Streamlit UI" in
[`user_guide.md`](user_guide.md)) has a sidebar "Target" radio with two modes: `Local API server`
(the pre-existing thin HTTP client over `POST /api/v1/rfp`) and `Deployed AgentCore Runtime
(AWS)`. Runtime mode calls `boto3`'s `invoke_agent_runtime` directly, SigV4-signed, with no local
server involved at all — it uses whatever AWS credentials are already active in the environment
(the same ones used for `terraform apply`), takes an AWS region + Agent Runtime ARN instead of an
API base URL, and shows a live status badge via `bedrock-agentcore-control`'s
`get_agent_runtime` (the runtime id is parsed from the ARN's last path segment). Both modes return
the identical `RfpOutcome` JSON shape (`runtime_entrypoint.py`'s `invoke()` and the API route both
return `dataclasses.asdict(outcome)`), so `render_result` needed no changes to handle either.

A genuine Streamlit widget-lifecycle bug was found and fixed while wiring this up, reproduced in
an isolated script before touching the real file to rule out anything else being the cause: a
`key`-bound widget (e.g. `st.text_input(..., key="aws_region")`, no explicit `value=`) only
reliably shows a pre-populated `st.session_state[key]` as its *displayed* value if the widget is
instantiated on the **same script run** where that default was first set. Since Local mode is the
default target, the Runtime-only widgets only render for the first time on a **later** rerun
(after the user switches modes) — Streamlit rendered them blank instead of picking up the
already-correct session-state value, which surfaced as a real, user-facing `ValueError: Invalid
endpoint: https://bedrock-agentcore-control..amazonaws.com` (empty region) the first time a real
Runtime ARN was entered. Fixed by passing `value=` explicitly on all three affected `text_input`s
(the API base URL field included, defensively, even though it wasn't observed broken — it only
"worked" by coincidence of being the default-rendered branch).

Verified via Playwright driving headless Chromium against the real running Streamlit app (no
`chromium-cli` in this environment, so Playwright was installed standalone into the scratchpad and
driven via a small Node script): default state unchanged, mode switch shows the right fields,
entering the real deployed Runtime ARN shows a genuine "Runtime READY" badge, and submitting the
INC2 example query in Runtime mode returned a real synthesized report (Approved, 1 compliance
attempt, 8.3s) rendered correctly via the existing result view.

### Environment lifecycle: teardown and cost control

`terraform destroy` on a dev environment that has actually been used (a pushed ECR image, ingested
S3 documents, ingested OpenSearch vector documents) hits AWS's and the OpenSearch community
provider's standard "won't delete non-empty resources" safety checks — the ECR repo and S3 bucket
refuse deletion with real AWS "not empty" errors, and `opensearch_index` has its own
`force_destroy` check. `modules/ecr` (`force_delete = true`), `modules/s3-kb-docs`
(`force_destroy = true`), and `modules/opensearch-index` (`force_destroy = true`) now set these
flags so any future destroy of these shared modules — dev, staging, or prod, since all three
environments share the same modules — won't hit the same blocker.

**Why a plain `terraform apply` to add those flags doesn't retroactively fix an in-progress
destroy**: `terraform destroy` deletes using each resource's *last-applied state*, not the
freshly-edited `.tf` config — a code change to a destroy-relevant flag needs an `apply` to land in
state before a subsequent `destroy` will honor it. On dev, an `apply` at that point would have
*recreated* the ~30 resources already destroyed earlier in the same run (`enable_agent_runtime`/
`enable_knowledge_base` were still `true` in tfvars), and a `-target`-scoped apply for just the 3
resources hit unrelated pre-existing schema drift on the OpenSearch index's `mappings.fields` that
would have forced a destroy+recreate instead of a clean in-place flag update. Dev was actually
torn down by clearing the blocking content directly via AWS APIs instead of fighting Terraform's
incremental-apply semantics: `ecr batch-delete-image` (all pushed digests), S3
`delete_object_versions` (versioning was on, so a plain `delete_object` wouldn't have been enough),
and a direct SigV4-signed `DELETE` HTTP call to the AOSS collection endpoint's index path
(confirmed AOSS's REST API surface is genuinely limited — `_delete_by_query` 404'd, `_search`
403'd, but `_cat/indices`/`_count`/a direct index `DELETE` all worked). A re-`plan`/`apply` after
that succeeded clean with the new flags now in state for good.

## Repository map

```
src/amc_orchestrator/
├── main.py                        # amc-orchestrator console script → uvicorn launcher
├── cli.py                         # direct graph invocation (pre-API smoke testing)
├── runtime_entrypoint.py          # AgentCore Runtime entrypoint (BedrockAgentCoreApp, /invocations, /ping)
├── config/
│   ├── settings.py                # Settings(BaseSettings), get_settings() cached singleton
│   ├── model_factory.py           # get_model() — only place that imports OllamaModel/BedrockModel
│   ├── compliance_rubric.py       # single source of truth for the rubric text
│   └── messages.py                # ESCALATION_HOLDING_MESSAGE, shared safe-fallback text
├── data/
│   ├── sqlite_store.py            # quant data (SQLite, DEV local backend)
│   ├── dynamodb_store.py          # quant data (DynamoDB, aws backend)
│   ├── quant_store.py             # facade: dispatches sqlite_store vs dynamodb_store
│   ├── chroma_store.py            # qual data (persistent Chroma, DEV local backend)
│   ├── knowledge_base_store.py    # qual data (Bedrock Knowledge Base Retrieve API, aws backend)
│   └── qual_store.py              # facade: dispatches chroma_store vs knowledge_base_store
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

`Dockerfile` lives at the repo root (sibling to `src/`, `infra/`) — builds the image
`runtime_entrypoint.py` runs inside, pushed to the ECR repo `infra/terraform/modules/ecr` creates.

```
infra/terraform/
├── bootstrap/                     # one-time: S3 state bucket, its own local state
├── modules/                       # reusable, environment-agnostic (see table above)
│   ├── iam/  ecr/  s3-kb-docs/  dynamodb/
│   ├── opensearch-serverless/  opensearch-access-policy/  opensearch-index/
│   ├── knowledge-base/  lambda-tools/
│   ├── agentcore-memory/  agentcore-gateway/  agentcore-runtime/
│   └── observability/
└── environments/
    ├── dev/       # cheapest defaults: no CMKs, single-AZ OpenSearch, short retention
    ├── staging/   # mirrors prod's security posture (CMKs, HA) for pre-prod validation
    └── prod/      # full HA + longest retention + deletion protection everywhere
```
