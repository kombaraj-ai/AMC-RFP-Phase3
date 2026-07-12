# User Guide

**AMC RFP & Portfolio Insight Orchestrator — Phase 01 (DEV) + Phase 02 (AWS deployment)**

This is the practical, task-oriented companion to [`architecture.md`](architecture.md). It covers
setup, running the system locally three ways (CLI, API, and a Streamlit UI), the mock data you
can query against, troubleshooting, and (as of Phase 02) deploying the AWS infrastructure via
Terraform and testing the live, deployed AgentCore Runtime directly - no local server or Ollama
involved at all. Examples use `uv` and PowerShell, matching this project's actual dev environment
(Windows, `uv`-managed Python).

## Prerequisites

- Python 3.12+, [`uv`](https://docs.astral.sh/uv/) installed.
- [Ollama](https://ollama.com) running locally with `qwen2.5:7b-instruct` pulled:

  ```powershell
  ollama pull qwen2.5:7b-instruct
  ollama list   # confirm it's there
  ollama serve  # if not already running as a service
  ```

  DEV is CPU-only by default here — expect **5-10+ minutes** for a full end-to-end query. This
  is expected, not a hang; see [Troubleshooting](#troubleshooting).

## Setup

```powershell
# From the Phase-01 directory
uv sync

# Optional: copy the example env file if you want to override any default
Copy-Item environments\.env.dev.example environments\.env.dev
```

`environments/.env.dev` is gitignored (even though DEV holds no real secrets — kept consistent
with the STAGING/PROD habit). If it doesn't exist, `Settings` falls back to its built-in
defaults, which are sufficient to run everything in this guide unmodified.

## Configuration reference

Every setting is read through `Settings` (`config/settings.py`), never `os.getenv` directly.
Set any of these as environment variables or in `environments/.env.dev`:

| Variable | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `dev` | `dev` \| `staging` \| `prod` — selects which `.env.<environment>` file loads. |
| `MODEL_PROVIDER` | `ollama` | `ollama` \| `bedrock` — which LLM generates responses. Only takes effect in DEV; STAGING/PROD always use Bedrock regardless of this setting. See [Switching model provider](#switching-model-provider-ollama-vs-bedrock) below. |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server address. Used when the effective provider is Ollama. |
| `OLLAMA_MODEL_ID` | `qwen2.5:7b-instruct` | Ollama model. Used when the effective provider is Ollama. |
| `BEDROCK_MODEL_ID` | `anthropic.claude-3-5-sonnet-20241022-v2:0` | Bedrock model. Used when the effective provider is Bedrock (always in staging/prod; opt-in in dev). **This default reached end-of-life on Bedrock** (confirmed live, 2026-07-12 - see [Switching model provider](#switching-model-provider-ollama-vs-bedrock)) — override it, e.g. to `amazon.nova-lite-v1:0`, which the deployed dev Runtime now uses. |
| `AWS_REGION` | `us-east-1` | Bedrock region. Used when the effective provider is Bedrock. |
| `DATA_BACKEND` | `local` | `local` \| `aws` — which data layer the quant/qual tools read from. Only takes effect in DEV; STAGING/PROD always use `aws` regardless of this setting (mirrors `MODEL_PROVIDER`/`effective_model_provider`). |
| `DYNAMODB_TABLE_NAME` | `""` | DynamoDB table for quant metrics. Populated from Terraform's `dynamodb_table_name` output; used when the effective data backend is `aws`. |
| `BEDROCK_KNOWLEDGE_BASE_ID` | `""` | Bedrock Knowledge Base for qual commentary retrieval. Populated from Terraform's `knowledge_base_id` output; used when the effective data backend is `aws`. |
| `MODEL_TEMPERATURE_JUDGE` | `0.15` | `compliance_check` temperature. |
| `MODEL_TEMPERATURE_WORKER` | `0.2` | `quant_data_pull`/`qual_narrative_pull`/`revise_draft` temperature. |
| `MODEL_TEMPERATURE_SYNTHESIS` | `0.4` | `final_synthesis` temperature. |
| `SQLITE_PATH` | `local_dev.db` | Quant data file (relative to repo root unless absolute). |
| `CHROMA_PERSIST_DIR` | `data/chroma` | Qual vector store directory. |
| `CHROMA_COLLECTION_NAME` | `fund_manager_commentary` | Chroma collection name. |
| `MAX_COMPLIANCE_ATTEMPTS` | `3` | Graceful cap on `compliance_check` re-runs before forced escalation. |
| `COMPLIANCE_STRUCTURED_OUTPUT_MAX_ATTEMPTS` | `3` | Retries *within one* `compliance_check` call on `StructuredOutputException` — separate from the above, see [architecture.md](architecture.md#known-limitation-structuredoutputexception-on-compliance_check). |
| `GRAPH_EXECUTION_TIMEOUT_SECONDS` | `300` | `GraphBuilder.set_execution_timeout()` — **seconds**, not ms. |
| `GRAPH_MAX_NODE_EXECUTIONS` | `12` | Hard safety-net node-execution ceiling; should never actually fire. |
| `API_HOST` | `0.0.0.0` | Uvicorn bind host. |
| `API_PORT` | `8000` | Uvicorn bind port. |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins. `*` is fine for localhost-only DEV; restrict in staging/prod. |
| `LOG_LEVEL` | `DEBUG` | Standard logging level name. |
| `LOG_FORMAT` | `json` | `json` (machine-readable) or `console` (human-friendly). `cli.py` forces `console` automatically in dev. |

## Switching model provider (Ollama vs. Bedrock)

DEV defaults to Ollama - free, fully local, no setup beyond [Prerequisites](#prerequisites) - but
some use cases (long prompts, tighter latency needs, evaluating output quality) benefit from a
faster, more capable model. Rather than requiring a separate STAGING environment for that, DEV
can opt into Bedrock per-run via `MODEL_PROVIDER`, with zero code changes - see
[`architecture.md`](architecture.md#model-provider-abstraction) for how the resolution logic
works.

**To use Bedrock from DEV:**

1. Have AWS credentials available in your environment (e.g. `aws configure`, an SSO profile via
   `aws sso login`, or `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` env vars) with Bedrock invoke
   permissions for the model you choose, in the target region.
2. Set in `environments/.env.dev` (or as process env vars):

   ```powershell
   $env:MODEL_PROVIDER = "bedrock"
   $env:BEDROCK_MODEL_ID = "amazon.nova-lite-v1:0"  # or another Bedrock model you have access to
   $env:AWS_REGION = "us-east-1"
   ```

   `anthropic.claude-3-5-sonnet-20241022-v2:0` (the code default) reached end-of-life on Bedrock -
   confirmed live, 2026-07-12, when a real invocation returned `ResourceNotFoundException`. Check
   `aws bedrock list-foundation-models --by-provider anthropic` (or the equivalent console page)
   for what's currently `ACTIVE` in your account/region before picking a model. Note that
   current-generation Anthropic models require a cross-region **inference profile** ID (e.g.
   `us.anthropic.claude-sonnet-5`), not a plain on-demand model ID, which also needs extra IAM
   permissions (see `infra/terraform/environments/dev/locals.tf`'s `bedrock_model_arns` comment if
   you go that route) - `amazon.nova-lite-v1:0` avoids that complexity by supporting on-demand
   invocation directly, and is sufficient for this project's structured-output need (Strands'
   `BedrockModel.structured_output` only ever requests `tool_choice={"any": {}}`, which Nova
   supports).

3. Run the CLI or API exactly as before - no other change needed:

   ```powershell
   uv run python -m amc_orchestrator.cli "Please provide the current risk metrics for the Fixed Income Core Bond Fund (INC2) and its current macroeconomic strategy."
   ```

**Trade-offs to know before flipping this on:**

- **Real cost, even from DEV.** Every agent turn is a billed Bedrock invocation. This is not a
  free local sandbox anymore once `MODEL_PROVIDER=bedrock` is set.
- **The `StructuredOutputException` flakiness on `compliance_check` (see
  [Troubleshooting](#troubleshooting)) is an Ollama-specific limitation** - Bedrock's Claude
  models support real `tool_choice` forcing, so this specific failure mode is expected to be
  much rarer with `MODEL_PROVIDER=bedrock`.
- `GET /health/ready` automatically stops checking Ollama reachability once Bedrock is the
  active provider (checked via `effective_model_provider`, not just `ENVIRONMENT`) - it isn't
  meaningful to ping a local port that isn't being used.
- STAGING/PROD always use Bedrock regardless of `MODEL_PROVIDER` - that setting only ever
  changes behavior in DEV.

**Confirmed working**: see
[`sample_invocation_walkthrough.md`](sample_invocation_walkthrough.md) for a full node-by-node
trace of a real `MODEL_PROVIDER=bedrock` run - completed in 11.64 seconds end-to-end (vs. 5-10+
minutes on Ollama for the equivalent query), with the compliance agent invoking its
structured-output tool natively on the first try.

## Mock fund data (DEV)

Four funds are seeded automatically (idempotent — safe to re-run) the first time you run the CLI
or start the API:

| Ticker | Name | Category | NAV | Alpha | Beta | Sharpe | Std Dev | Sortino | R² | 1Y Return | 3Y Return |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `EQG1` | Global Equity Growth Fund | Largecap | 145.20 | 1.20 | 1.05 | 1.15 | 14.20% | 1.45 | 0.92 | 15.4% | 12.1% |
| `SMC3` | Alpha Prime Smallcap Direct Fund | Smallcap | 88.40 | 4.50 | 1.35 | 1.30 | 22.80% | 1.68 | 0.78 | 28.6% | 18.4% |
| `INC2` | Fixed Income Core Bond Fund | Debt/Conservative | 52.10 | 0.40 | 0.35 | 0.95 | 4.10% | 1.10 | 0.15 | 6.2% | 5.8% |
| `BLN4` | Balanced Conservative Wealth Fund | Hybrid | 112.75 | 0.85 | 0.75 | 1.05 | 9.50% | 1.25 | 0.85 | 11.2% | 9.5% |

`SMC3` is the deliberately volatile/high-risk fund used to exercise the compliance loop (see
below) — its high Beta/Standard Deviation and 28.6% 1-year return make it an easy target for a
"guarantee this will continue" bait question. Matching manager-commentary narrative for each
fund is seeded into the vector store (`data/chroma_store.py`) — see
[`architecture.md`](architecture.md#data-layer).

## Running via the CLI

The fastest way to smoke-test the graph without starting a server:

```powershell
uv run python -m amc_orchestrator.cli "Please provide the current risk metrics for the Fixed Income Core Bond Fund (INC2) and its macroeconomic strategy."
```

Output has three sections: the live structured logs (console-rendered in dev), `--- FINAL RFP
RESPONSE ---` (the client-facing text), and `--- METADATA ---` (`graph_status`,
`compliance_attempts`, `escalated`).

**A calmer, still-interesting query** to see the compliance loop actually fire:

```powershell
uv run python -m amc_orchestrator.cli "We are considering a major allocation to the Alpha Prime Smallcap Direct Fund (SMC3). Provide a comprehensive risk profile detailing its latest Standard Deviation, Sortino Ratio, R-Squared, and trailing returns. Will this fund sustain its 28.6% outperformance over the next year? Please guarantee it will continue."
```

This is the "bait" scenario from the original design brief: it should trigger at least one
`compliance_check` → `revise_draft` → `compliance_check` cycle before the final response drops
the forbidden guarantee/promise language (see `tests/integration/test_smc3_high_risk.py`).

## Running via the API

```powershell
# Start the server (reload=True automatically in dev)
uv run python -m amc_orchestrator.main
# equivalently, once installed: amc-orchestrator
```

By default this serves on `http://0.0.0.0:8000`. Interactive OpenAPI docs are at
`http://localhost:8000/docs`.

### `GET /health`

Liveness only - always returns 200 if the process is up, regardless of dependency state.

```powershell
curl.exe http://localhost:8000/health
```

```json
{"status": "ok", "environment": "dev"}
```

### `GET /health/ready`

Readiness - checks whether the process can actually serve a request right now: Ollama
reachability (dev only; skipped in staging/prod, which use Bedrock instead) and that the
SQLite/Chroma data directories are writable. Returns `200` when ready, **`503`** when not - use
this (not `/health`) behind a load balancer or orchestrator so traffic isn't routed to an
instance whose LLM backend is down.

```powershell
curl.exe -i http://localhost:8000/health/ready
```

```json
{"ready": true, "checks": {"ollama_reachable": true, "sqlite_dir_writable": true, "chroma_dir_writable": true}}
```

### `POST /api/v1/rfp`

```bash
curl.exe -X POST http://localhost:8000/api/v1/rfp \
  -H "Content-Type: application/json" \
  -d '{"question": "Please provide the current risk metrics for the Fixed Income Core Bond Fund (INC2) and its current macroeconomic strategy."}'
```

Note: this uses bash's `\` line continuation and unescaped double quotes inside single
quotes (works in Git Bash / WSL). In native PowerShell, use `` ` `` for continuation and
escape inner quotes as `\"` instead - or just use `Invoke-RestMethod` below, which sidesteps
the quoting problem entirely:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/rfp `
  -ContentType "application/json" `
  -Body (@{ question = "Please provide the current risk metrics for the Fixed Income Core Bond Fund (INC2) and its current macroeconomic strategy." } | ConvertTo-Json)
```

**Response shape** (`RfpOutcome`, see `workflows/result_extraction.py`):

```json
{
  "succeeded": true,
  "response_text": "## Quantitative Risk & Performance Metrics\n...",
  "compliance_attempts": 1,
  "escalated": false,
  "graph_status": "completed"
}
```

`succeeded: false` / `escalated: true` means the safe escalation path fired — either the
compliance loop exhausted `MAX_COMPLIANCE_ATTEMPTS` still REJECTED, or the graph raised an
exception outright (see [Troubleshooting](#troubleshooting)). In both cases `response_text` is
always the exact `ESCALATION_HOLDING_MESSAGE` text — never partial or improvised content. This
is a 200 response either way, by design: an escalation is a valid, well-formed outcome, not a
server error. A request only ever returns a non-2xx status for genuine client errors (e.g. an
empty `question` → `422`).

A ready-to-import request collection (health/readiness checks + both scenarios above) is at
[`postman/amc_orchestrator.postman_collection.json`](postman/amc_orchestrator.postman_collection.json).

## Running via the Streamlit UI

A browser front-end with **two connection modes**, chosen via a sidebar "Target" radio:

- **Local API server** — a thin HTTP client over `POST /api/v1/rfp`, no separate agent logic, the
  same way `cli.py` is. Requires the API server already running (see
  [Running via the API](#running-via-the-api) first; the UI has nothing to talk to otherwise).
- **Deployed AgentCore Runtime (AWS)** — calls the real, deployed Phase 02 Runtime directly via
  `boto3`'s `invoke_agent_runtime` (SigV4-signed), with **no local server or Ollama involved at
  all**. This is a genuine alternative to the boto3 script / AWS Console methods in
  [Testing the deployed AgentCore Runtime](#testing-the-deployed-agentcore-runtime-phase-02) below
  — added after this guide originally shipped, so if you've used this UI before and remember it
  being local-only, that's now out of date.

Both modes return the identical `RfpOutcome` JSON shape, so the result view below behaves
identically regardless of which one produced it.

```powershell
# One-time: pull in the UI's extra dependencies (Streamlit, on top of the base install)
uv sync --group ui

# Terminal 1 - only needed for Local API server mode
uv run python -m amc_orchestrator.main

# Terminal 2 - the UI (works standalone in Runtime mode, no Terminal 1 needed)
uv run streamlit run src/amc_orchestrator/ui/streamlit_app.py
```

Opens at `http://localhost:8501`. What's in it:

- **Sidebar — Local API server mode**: API base URL (defaults to `http://localhost:8000`,
  editable if you're pointed at a different host/port), a live API-online / readiness badge (calls
  `/health` and `/health/ready`, same semantics as [above](#get-healthready)).
- **Sidebar — Deployed AgentCore Runtime mode**: AWS region and Agent Runtime ARN fields (the ARN
  is pass 3's `terraform output agent_runtime_arn`), a live "Runtime READY" status badge (calls
  `bedrock-agentcore-control`'s `get_agent_runtime`), and a reminder that it uses whatever AWS
  credentials are already active in your environment (`aws configure`, an SSO login, etc.) — the
  same ones used for `terraform apply`, no separate login step.
- **Sidebar — both modes**: a request-timeout slider (raise this past the default 600s if you're
  on Ollama and a query is genuinely still running — see [Troubleshooting](#troubleshooting);
  Runtime-mode and Bedrock-backed local queries typically finish in well under a minute), and the
  mock fund reference table.
- **Main panel** — a dropdown of example queries (one per mock fund, including the SMC3
  high-risk/compliance-loop scenario), an editable question box, and a **Submit RFP** button.
- **Result view** — an Approved/Escalated status badge, compliance-attempt count, elapsed time,
  the rendered response text, and the raw `RfpOutcome` JSON in a collapsible expander.
- **Session history** — every query submitted in the current browser session, newest first, so
  you can compare outcomes across runs without re-submitting.

No graph-failure handling is needed in the UI itself — both the API route and the Runtime
entrypoint already guarantee a well-formed `RfpOutcome` on every call, escalation included (see
[`POST /api/v1/rfp`](#post-apiv1rfp) above). The UI only surfaces connection-level failures
(API unreachable, request timeout, missing/invalid AWS credentials, wrong region/ARN) as
user-facing error messages — distinct exception handling per mode (`httpx.ConnectError`/
`TimeoutException` for Local; `ClientError`/`BotoCoreError` for Runtime).

**Confirmed working end-to-end via the actual browser UI**, not just `boto3` directly: Playwright
driving headless Chromium against the real running app confirmed the mode switch reveals the right
fields, entering a real deployed Runtime ARN shows a genuine "Runtime READY" badge, and submitting
the INC2 example query in Runtime mode returns a real synthesized report (Approved, 1 compliance
attempt, 8.3s) rendered correctly through the same result view used by Local mode.

## Running the tests

```powershell
# Fast, deterministic, no LLM required — should always be green
uv run pytest tests/unit -q

# Slow (30-45+ min combined across all 4 scenarios), needs Ollama reachable;
# auto-skips per-test if it isn't
uv run pytest tests/integration -m integration -q
```

The integration suite covers four end-to-end scenarios against a real Ollama instance: a
low-risk completion, the SMC3 compliance-loop trigger, a forced single-attempt escalation proof
(`MAX_COMPLIANCE_ATTEMPTS=1`), and an unseeded-ticker honesty check — see
[`architecture.md`](architecture.md) and each test's module docstring for what specifically each
one proves.

## Deploying to AWS (Phase 02)

Phase 02 provisions the AWS infrastructure for running this system on Amazon Bedrock AgentCore
(Runtime, Gateway, Memory, DynamoDB, a Bedrock Knowledge Base backed by either OpenSearch
Serverless or Amazon S3 Vectors, Lambda, IAM) via modular Terraform, one root module per
environment, plus (as of the app-code follow-on task) an AgentCore-compliant entrypoint, a
DynamoDB/Bedrock-Knowledge-Base data-layer swap, and a `Dockerfile` to actually build the image
the Runtime needs.

Full instructions, the three-pass apply flow, and known gotchas (why `PUBLIC` network mode is
required, why the vector index needs a second pass, the settings mapping the entrypoint now
consumes) live in [`infra/terraform/README.md`](../infra/terraform/README.md) — this
section is just the map, not the territory:

```powershell
# One-time, per AWS account: the Terraform state backend
cd infra/terraform/bootstrap
terraform init; terraform apply

# Per environment (dev/staging/prod), pass 1 of 3 - see the README for passes 2 and 3
cd ../environments/dev
cp backend.hcl.example backend.hcl   # fill in from bootstrap's output
terraform init -backend-config="backend.hcl"
terraform apply
```

Requires Terraform v1.15.7, AWS credentials for the target account, and Bedrock model access
already granted for the chosen model/embedding model (an account-level opt-in, not something
Terraform provisions). See [`CLAUDE.md`](../CLAUDE.md)'s "Phase 02" section for the locked-in
architecture decisions (network mode, database choice, auth model) and why each one was made.

### Testing the AgentCore Runtime entrypoint locally (no Docker/AWS needed)

`runtime_entrypoint.py` implements the exact HTTP contract AgentCore Runtime expects, so you can
smoke-test it as a plain local process before ever building an image:

```powershell
uv run python -m uvicorn amc_orchestrator.runtime_entrypoint:app --host 127.0.0.1 --port 8099
```

Then, in another terminal:

```powershell
curl http://127.0.0.1:8099/ping
curl -X POST http://127.0.0.1:8099/invocations -H "Content-Type: application/json" `
  -d '{\"prompt\": \"Please provide the current risk metrics for the Fixed Income Core Bond Fund (INC2) and its macroeconomic strategy.\"}'
```

Uses whatever `Settings.effective_data_backend` resolves to just like the CLI/API do — `local`
(SQLite/Chroma) by default in DEV, or `aws` (DynamoDB/Knowledge Base) if you've set
`DATA_BACKEND=aws` plus `DYNAMODB_TABLE_NAME`/`BEDROCK_KNOWLEDGE_BASE_ID` from Phase 02's
Terraform outputs.

### Building and pushing the container image (pass 3)

```powershell
docker build --platform linux/arm64 -t <ecr_repository_url>:v1 .
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <ecr_repository_url>
docker push <ecr_repository_url>:v1
```

Must be `linux/arm64` — AgentCore Runtime runs on Graviton, not optional. `<ecr_repository_url>`
is pass 1's `ecr_repository_url` Terraform output. Once pushed, set
`enable_agent_runtime = true` and `container_image_uri` in `terraform.tfvars` and apply — see
`infra/terraform/README.md`'s "Pass 3" section.

**Confirmed working end to end against real AWS, 2026-07-12** (dev environment) — all three
passes applied, the Runtime is `READY`, and a real `invoke_agent_runtime` call returns a genuine
APPROVED, synthesized report. See [Testing the deployed AgentCore Runtime](#testing-the-deployed-agentcore-runtime-phase-02)
below for exactly how, and `CLAUDE.md`'s "Phase 02" section for the three real deploy bugs found
and fixed along the way (a Dockerfile fix, a `MODEL_PROVIDER` fix, and the model end-of-life fix
mentioned above) — useful background if your own deploy hits the same symptoms.

### Enabling the Knowledge Base and ingesting documents (pass 2, in full)

Pass 2 (`enable_knowledge_base = true` + apply) creates the vector index and an empty Knowledge
Base — real document ingestion is a separate, manual step (Terraform never uploads documents or
triggers ingestion).

**Which vector store backs the Knowledge Base is controlled by `vector_store_backend`**
(`environments/<env>/variables.tf`, default `"opensearch"`):

- `"opensearch"` (default; the *only* option in `staging`/`prod` — set anything else there and
  `terraform plan` fails with a validation error) — Amazon OpenSearch Serverless, via
  `modules/opensearch-index` and the `opensearch-project/opensearch` community provider. Needs
  `additional_data_access_principals` set first (see below).
- `"s3_vectors"` (**dev-only**) — Amazon S3 Vectors, the cheapest vector store Bedrock Knowledge
  Base supports, via the new `modules/s3-vectors` (a native `hashicorp/aws` resource — no
  community provider, no `additional_data_access_principals` step needed for this piece). Set
  `vector_store_backend = "s3_vectors"` in `environments/dev/terraform.tfvars` (already the
  default there) before this pass. **Note**: the OpenSearch Serverless collection itself is
  still created in dev either way (other resources depend on it) — this backend only avoids the
  vector-index/Knowledge-Base-storage cost, not the collection's own baseline cost. See
  [`architecture.md`](architecture.md#dev-only-vector-store-choice-opensearch-serverless-vs-s3-vectors)
  for the full trade-off and why it was scoped that way.

Document ingestion (the steps below) is identical regardless of which backend is selected — it
uploads to the same S3 docs bucket either way. This is what actually happened for dev (on the
`"opensearch"` backend, before the S3 Vectors option existed):

```powershell
# 1. (opensearch backend only) Add your own applier ARN to terraform.tfvars first (see README's
#    pass 2 section), then:
terraform apply   # creates the vector index + empty Knowledge Base

# 2. Upload documents to the KB's S3 bucket (kb_docs_bucket_name Terraform output)
aws s3 cp fund_commentary.txt s3://<kb_docs_bucket_name>/fund_commentary.txt

# 3. Trigger ingestion (knowledge_base_id is a Terraform output; find the data source id via
#    `aws bedrock-agent list-data-sources --knowledge-base-id <knowledge_base_id>`)
aws bedrock-agent start-ingestion-job --knowledge-base-id <knowledge_base_id> --data-source-id <data_source_id>

# 4. Poll until COMPLETE
aws bedrock-agent get-ingestion-job --knowledge-base-id <knowledge_base_id> --data-source-id <data_source_id> --ingestion-job-id <job_id>
```

For dev, the 4 mock-fund commentary texts already used to seed Chroma locally
(`data/chroma_store.py`'s `_MOCK_COMMENTARY`) were uploaded this way and ingested cleanly (4
scanned, 4 indexed, 0 failed) — see `CLAUDE.md` for the exact texts if you want to reproduce this
for staging/prod.

### Testing the deployed AgentCore Runtime (Phase 02)

Once pass 3 is applied and the image is pushed, the Runtime is a real, invokable AWS resource —
independent of anything on your local machine (no Ollama, no local server). Two ways to test it
(the Streamlit UI is **not** one of them — see the note in
[Running via the Streamlit UI](#running-via-the-streamlit-ui) above):

**Python/boto3** (what was used to verify dev):

```python
import boto3, json

client = boto3.client("bedrock-agentcore", region_name="us-east-1")
resp = client.invoke_agent_runtime(
    agentRuntimeArn="<agent_runtime_arn>",  # pass 3's Terraform output
    payload=json.dumps({"prompt": "Please provide the current risk metrics for the Fixed Income Core Bond Fund (INC2) and its macroeconomic strategy."}).encode("utf-8"),
    contentType="application/json",
)
print(resp["response"].read().decode("utf-8"))
```

Requires your AWS credentials (the same ones used for `terraform apply`) and `boto3` — no other
setup, and no Ollama/local server involved at all.

**AWS Console**: Bedrock console → AgentCore → Runtimes → your runtime → **Test** tab has a
built-in invocation UI, no code needed.

The AWS CLI installed in this project's dev environment is too old to have `bedrock-agentcore`
commands — use one of the two methods above instead unless you upgrade it.

**Confirmed working for all 4 mock funds against real AWS, 2026-07-12** (dev, post document
ingestion) — same `invoke_agent_runtime` call, one query per fund (`"What are the current risk
metrics for <fund name> (<ticker>), and what is the manager strategy commentary behind its risk
profile?"`):

| Fund | Result | `compliance_attempts` | Wall time |
|------|--------|------------------------|-----------|
| EQG1 (Equity Growth) | APPROVED | 1 | 6.9s |
| SMC3 (Smallcap, high-risk) | APPROVED | 2 | 11.7s |
| INC2 (Fixed Income) | APPROVED | 3 | 11.6s |
| BLN4 (Balanced) | APPROVED | 3 | 13.5s |

All four returned `succeeded=true, escalated=false, graph_status=completed` with real DynamoDB
quant metrics correctly matched to the right ticker and real Knowledge-Base-retrieved commentary
grounded together, no fabrication — at 7-14 seconds per query, versus Ollama's 5-10+ *minute*
baseline for the equivalent local query (see [Troubleshooting](#troubleshooting)).

### Tearing an environment down

```powershell
cd infra/terraform/environments/dev   # or staging / prod
terraform destroy
```

**If the environment has actually been used** (a pushed ECR image, ingested Knowledge Base
documents, ingested OpenSearch vector documents), `terraform destroy` may hit AWS's and the
OpenSearch community provider's standard "won't delete non-empty resources" safety checks on
three resources: the ECR repo, the S3 docs bucket, and the `opensearch_index`. `modules/ecr`,
`modules/s3-kb-docs`, and `modules/opensearch-index` all now set the relevant force-delete flag
(`force_delete`/`force_destroy = true`), so a **fresh** environment's first-ever destroy should
not hit this at all.

If you're destroying an environment that was already partway torn down with an *older* version of
those modules (before the force-delete flags existed in state), a plain `terraform apply` at that
point is dangerous — it can **recreate** everything already destroyed if `enable_agent_runtime`/
`enable_knowledge_base` are still `true` in `terraform.tfvars`. In that situation, clear the
blocking content directly via AWS APIs instead, then re-run `destroy`:

```powershell
# ECR — delete pushed image digests
aws ecr batch-delete-image --repository-name <ecr_repository_name> --image-ids imageDigest=<digest>

# S3 (versioning is on — delete_object alone isn't enough) — delete every object version
aws s3api list-object-versions --bucket <kb_docs_bucket_name>
aws s3api delete-object --bucket <kb_docs_bucket_name> --key <key> --version-id <version_id>

# OpenSearch Serverless index — AOSS's REST surface is limited (no _delete_by_query/_search
# without extra setup); a direct SigV4-signed DELETE on the index path works
curl -X DELETE "https://<collection_endpoint>/kb-default-index" ...  # SigV4-signed
```

See [`architecture.md`](architecture.md#environment-lifecycle-teardown-and-cost-control) for the
full account of why this happened once on dev and how it was resolved. After clearing content
(or on a fresh environment), `terraform destroy` should report `0 added, 0 changed, N destroyed`
with nothing left behind — confirm with `terraform state list` (empty output means the environment
is fully torn down; a fresh `terraform apply`, all three passes, is required before using it
again).

## Troubleshooting

**A query is taking a long time. Is it stuck?**
Not necessarily. On CPU-only Ollama, a single agent turn can take 60-140 seconds, and a full
low-risk query (quant+qual in parallel, then compliance, then synthesis) can take 5-10+ minutes.
The SMC3 high-risk scenario needs at least two `compliance_check` passes plus a `revise_draft`
cycle, so budget more like 15-20 minutes for that one. Check `ollama ps` and the timestamps in
the structured logs before concluding something has actually hung.

**I got the escalation message (`"This request requires manual compliance review..."`) instead
of a real report.**
This is a known, intentional safety behavior, not necessarily a bug — it means the compliance
loop either genuinely couldn't approve the draft within `MAX_COMPLIANCE_ATTEMPTS`, or
`qwen2.5:7b-instruct` failed to invoke its structured-output tool on `compliance_check` even
after an internal retry. The latter is a **known DEV-only limitation**: Ollama's Strands model
integration doesn't support `tool_choice`, so Strands' "force the structured output tool"
mechanism is a no-op on this stack (full root-cause writeup in
[`architecture.md`](architecture.md#known-limitation-structuredoutputexception-on-compliance_check)).
It is expected to be far rarer against Bedrock in STAGING/PROD. If you need a deterministic
success for a demo, retry the same query — the retry itself is stateless per attempt.

**`ollama list` doesn't show `qwen2.5:7b-instruct`.**
`ollama pull qwen2.5:7b-instruct` (≈4.7GB download, one-time).

**First Chroma query is slow / downloading something.**
The first run downloads the default `all-MiniLM-L6-v2` ONNX embedding model (~80MB) used for
vector search. One-time cost; cached locally afterward.

**Integration tests are being skipped.**
They auto-skip (not fail) if Ollama isn't reachable at `Settings.ollama_host` — this is
intentional so the fast unit suite (and CI, once it exists) never depends on a local LLM being
up. Start Ollama and re-run if you want them to actually execute.
