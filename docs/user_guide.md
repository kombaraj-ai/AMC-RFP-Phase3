# User Guide

**AMC RFP & Portfolio Insight Orchestrator — Phase 01 (DEV)**

This is the practical, task-oriented companion to [`architecture.md`](architecture.md). It covers
setup, running the system two ways (CLI and API), the mock data you can query against, and
troubleshooting. Examples use `uv` and PowerShell, matching this project's actual dev environment
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
| `BEDROCK_MODEL_ID` | `anthropic.claude-3-5-sonnet-20241022-v2:0` | Bedrock model. Used when the effective provider is Bedrock (always in staging/prod; opt-in in dev). |
| `AWS_REGION` | `us-east-1` | Bedrock region. Used when the effective provider is Bedrock. |
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
   $env:BEDROCK_MODEL_ID = "anthropic.claude-3-5-sonnet-20241022-v2:0"  # or another Bedrock model
   $env:AWS_REGION = "us-east-1"
   ```

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

```powershell
curl.exe -X POST http://localhost:8000/api/v1/rfp `
  -H "Content-Type: application/json" `
  -d '{\"question\": \"Please provide the current risk metrics for the Fixed Income Core Bond Fund (INC2) and its current macroeconomic strategy.\"}'
```

Or with PowerShell's native `Invoke-RestMethod` (handles JSON escaping for you):

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
