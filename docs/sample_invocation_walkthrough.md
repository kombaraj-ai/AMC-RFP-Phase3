# Phase1 - Sample Invocation Walkthrough

A detailed, step-by-step trace of one real end-to-end run through the RFP graph, annotated
against [`architecture.md`](architecture.md). This is the **first confirmed successful run
against AWS Bedrock** (`MODEL_PROVIDER=bedrock`, see the "Switching model provider" section of
[`user_guide.md`](user_guide.md)) - source log: `Sample-Invocation.txt` at the repo root.

## Run metadata

| | |
|---|---|
| Command | `uv run python -m amc_orchestrator.cli "Please provide the current risk metrics for the Fixed Income Core Bond Fund (INC2) and its current macroeconomic strategy."` |
| Model provider | `bedrock` (`effective_model_provider`) |
| Model | `anthropic.claude-3-5-sonnet-20241022-v2:0` |
| Region | `us-east-1` |
| `trace_id` / `request_id` | `2650e30d-9641-4467-8b2d-4195a87221ef` (same value - the CLI seeds `request_id` from `trace_id` when none is supplied) |
| Graph status | `completed` |
| Compliance attempts | `1` (APPROVED on the first pass - no `revise_draft` cycle needed) |
| Escalated | `False` |
| **Total wall-clock time** | **11.64 seconds**, start to final response |

For scale: the equivalent low-risk query on Ollama (`qwen2.5:7b-instruct`, CPU-only) has taken
**5-10+ minutes** in prior sessions (see CLAUDE.md's "Known slow/flaky things"). This run is a
concrete illustration of why the DEV model-provider toggle exists.

## The client prompt

> Please provide the current risk metrics for the Fixed Income Core Bond Fund (INC2) and its
> current macroeconomic strategy.

This is the exact string passed as `graph(question)` - it becomes the "Original Task:" line in
every downstream agent's input (see `workflows/graph_build.py`'s `_build_node_input` format,
documented in `architecture.md`).

## Execution flow

```
t=+0.00s  quant_data_pull ─┐   (parallel entry points)
          qual_narrative_pull ─┘
                │                    │
   t=+2.22s  get_fund_performance    │
   t=+2.93s      │        search_fund_commentary
   t=+3.50s  quant_data_pull done    │
   t=+4.81s      │        qual_narrative_pull done
                  └──────────┬───────┘
   t=+4.81s          compliance_check starts
   t=+9.52s          ComplianceVerdict tool call (native tool_use, not forced)
   t=+9.52s          compliance_check done → APPROVED
   t=+9.52s          final_synthesis starts (APPROVED branch)
   t=+11.64s         final_synthesis done → FINAL RESPONSE
```

`quant_data_pull` and `qual_narrative_pull` are the graph's two entry points and ran genuinely in
parallel (both started within 1ms of each other). `compliance_check` only started once **both**
had finished (it started at +4.81s, immediately after the slower of the two - `qual_narrative_pull`
- completed at +4.81s), matching the unconditional-edge join behavior described in
`architecture.md`. `revise_draft` never ran, because `compliance_check` returned `APPROVED` on
its first and only pass.

## Step-by-step agent trace

### 1. `quant_data_pull` — Quantitative Analyst Agent

**Purpose** (`agents/quant_agent.py`): pull exact numerical fund metrics via the
`get_fund_performance` tool - never estimate or recall figures from memory.

**Started**: +0.00s · **Duration**: 3502 ms · **Stop reason**: `end_turn`

**Reasoning** (model's own `<thinking>` block, verbatim from the log):
> The User has asked for risk metrics for the Fixed Income Core Bond Fund (INC2) and its current
> macroeconomic strategy. The risk metrics can be obtained using the `get_fund_performance` tool,
> but the macroeconomic strategy is not something that can be retrieved using the available
> tools. I will first retrieve the risk metrics for the fund and then inform the User that I
> cannot provide information on the macroeconomic strategy.

**Tool called**: `get_fund_performance` (ticker inferred as `INC2` from the request and the
returned figures; exact call arguments aren't captured at the current log verbosity - see
`observability/hooks.py`, which logs `tool_name` but not the full tool-use payload).
Tool call itself took **6 ms** (+2.217s → +2.223s).

**Output**:
> Here are the current risk metrics for the Fixed Income Core Bond Fund (INC2):
>
> - NAV (Net Asset Value): $52.10
> - Alpha: 0.4
> - Beta: 0.35
> - Sharpe Ratio: 0.95
> - Standard Deviation: 4.1
> - Sortino Ratio: 1.1
> - R-Squared: 0.15
> - 1-year trailing return: 6.2%
> - 3-year trailing return: 5.8%
>
> Regarding the current macroeconomic strategy of the fund, I cannot provide information on that
> as it is not something that can be retrieved using the available tools.

Every figure matches the seeded mock data for `INC2` in `data/sqlite_store.py` exactly (NAV
52.10, Alpha 0.40, Beta 0.35, Sharpe 0.95, Std Dev 4.10%, Sortino 1.10, R² 0.15, 1Y 6.2%, 3Y
5.8%) - no fabrication. The agent also correctly declined to answer the macro-strategy half of
the question, since that's out of scope for its one tool - exactly per its system prompt's rule
"Do not comment on compliance, strategy, or narrative - that is not your job."

### 2. `qual_narrative_pull` — Qualitative Strategy Agent

**Purpose** (`agents/qual_agent.py`): retrieve fund-manager commentary/macro outlook via the
`search_fund_commentary` RAG tool and synthesize it into a narrative - never invent positions not
returned by the tool.

**Started**: +0.00s (parallel with `quant_data_pull`) · **Duration**: 4805 ms · **Stop reason**:
`end_turn`

**Reasoning**:
> The User has asked for the current risk metrics and macroeconomic strategy for the Fixed
> Income Core Bond Fund (INC2). However, the tools available do not provide risk metrics, only
> qualitative commentary. I will first search for the macroeconomic strategy and any related
> commentary that might indirectly touch on risk metrics.

**Tool called**: `search_fund_commentary` (query text not captured at current log verbosity;
based on the result, it matched the seeded `doc_inc2` commentary in `data/chroma_store.py`). Tool
call took **~582 ms** (+2.926s → +3.508s) - the slowest single tool call in this run, consistent
with a vector similarity search plus (first-run) embedding model overhead versus the near-instant
SQLite lookup.

**Output**:
> The Fixed Income Core Bond Fund (INC2) has been actively managing its duration risk in
> response to recent central bank updates. The fund's exceptionally low Beta of 0.35 indicates
> its role as a defensive asset during periods of equity market corrections, serving as a stable
> foundation in a diversified portfolio. The fund's strategy is focused on maintaining a
> conservative approach to mitigate risks associated with interest rate fluctuations and market
> volatility.

This is a faithful synthesis of the seeded `doc_inc2` commentary - no invented strategic
positions.

### 3. `compliance_check` — Chief Compliance Officer Agent (LLM-as-a-Judge)

**Purpose** (`agents/compliance_agent.py`): on a first pass (no `revise_draft` input yet),
synthesize a draft from quant + qual, then judge it against the five-rule compliance rubric
(`docs/compliance_rubric.md`), returning a structured `ComplianceVerdict` - never free text.

**Started**: +4.81s (immediately after both `quant_data_pull` and `qual_narrative_pull`
completed) · **Duration**: 4713 ms · **Stop reason**: `tool_use`

**Reasoning**:
> I need to synthesize the provided quantitative and qualitative information into a coherent
> narrative for the User. I will ensure that the narrative adheres to the compliance rubric by
> avoiding any guarantee of future returns, including the necessary disclaimers, and framing any
> forward-looking statements appropriately.

**Self-synthesized draft** (the text it then judged - this becomes `ComplianceVerdict.evaluated_text`):
> "The Fixed Income Core Bond Fund (INC2) has been actively managing its duration risk in
> response to recent central bank updates. The fund's exceptionally low Beta of 0.35 indicates
> its role as a defensive asset during periods of equity market corrections, serving as a stable
> foundation in a diversified portfolio. The fund's strategy is focused on maintaining a
> conservative approach to mitigate risks associated with interest rate fluctuations and market
> volatility.
>
> The current risk metrics for the Fixed Income Core Bond Fund (INC2) are as follows:
>
> - NAV (Net Asset Value): $52.10
> - Alpha: 0.4
> - Beta: 0.35
> - Sharpe Ratio: 0.95
> - Standard Deviation: 4.1
> - Sortino Ratio: 1.1
> - R-Squared: 0.15
> - 1-year trailing return: 6.2%
> - 3-year trailing return: 5.8%
>
> Past performance is not indicative of future results. The fund's current macroeconomic
> strategy is focused on maintaining a conservative approach to mitigate risks associated with
> interest rate fluctuations and market volatility. We anticipate that this strategy will
> continue to provide stability and potentially attractive returns in the current economic
> environment."

Note how the rubric is visibly satisfied here: the mandatory disclaimer ("Past performance is not
indicative of future results") is present per **Rule 2**, and the forward-looking sentence is
explicitly hedged ("**We anticipate** that this strategy will continue...") rather than stated as
a certainty, per **Rule 4** - no guarantee/promise language per **Rule 1/3**.

**Tool called**: `ComplianceVerdict` - the structured-output tool, not a business tool (see
`schemas/compliance.py`). Call took **<1 ms** (+9.518s → +9.519s).

**Verdict** (not printed as raw text by the CLI, but inferable from the graph metadata):
`status: APPROVED`. This is confirmed by `compliance_attempts=1` and `escalated=False` in the
final metadata - if it had been `REJECTED`, `needs_revision` would have routed to `revise_draft`
for a second `compliance_check` pass (see `workflows/routing.py`), which did not happen here.

**Notable technical detail**: `stop_reason=tool_use` here means Claude on Bedrock invoked the
`ComplianceVerdict` tool **natively, on its own**, without Strands needing to fall back to its
"forced" second turn. This is the concrete payoff of the DEV model-provider toggle: Bedrock
supports real `tool_choice` forcing (and in this case didn't even need it), which is exactly the
mechanism Ollama's Strands integration silently ignores - the root cause of the
`StructuredOutputException` flakiness documented in CLAUDE.md's "Bug #2". This run needed zero
internal retries from `_RetryingComplianceAgent`.

### 4. `revise_draft` — Revisor Agent (not triggered this run)

Per `workflows/routing.py`, `needs_revision` only routes here when `compliance_check` returns
`REJECTED` (or a missing/malformed verdict) and the attempt budget isn't exhausted. Since the
verdict was `APPROVED` on the first pass, this node never executed - `ready_to_synthesize`
resolved `True` immediately instead.

### 5. `final_synthesis` — Client Reporting & Communications Agent

**Purpose** (`agents/synthesizer_agent.py`): produce the final client-facing answer. Two
branches, never blended - `APPROVED` yields a full structured report; anything else yields the
exact `ESCALATION_HOLDING_MESSAGE`.

**Started**: +9.52s · **Duration**: 2118 ms · **Stop reason**: `end_turn`

**Branch taken**: APPROVED → full report, built from the quant figures, the qual/compliance
narrative, and the disclaimer - exactly the three required sections (Quantitative Risk &
Performance Metrics / Manager Strategy Commentary / Compliance Disclosures), with no new claims
introduced beyond what earlier nodes provided.

## Final client-facing response

```
### Quantitative Risk & Performance Metrics

The Fixed Income Core Bond Fund (INC2) presents the following quantitative metrics:

- NAV (Net Asset Value): $52.10
- Alpha: 0.4
- Beta: 0.35
- Sharpe Ratio: 0.95
- Standard Deviation: 4.1
- Sortino Ratio: 1.1
- R-Squared: 0.15
- 1-year trailing return: 6.2%
- 3-year trailing return: 5.8%

### Manager Strategy Commentary

The Fixed Income Core Bond Fund (INC2) has been actively managing its duration risk in response
to recent central bank updates. The fund's exceptionally low Beta of 0.35 indicates its role as
a defensive asset during periods of equity market corrections, serving as a stable foundation in
a diversified portfolio. The fund's strategy is focused on maintaining a conservative approach to
mitigate risks associated with interest rate fluctuations and market volatility. We anticipate
that this strategy will continue to provide stability and potentially attractive returns in the
current economic environment.

### Compliance Disclosures

Past performance is not indicative of future results. The fund's current macroeconomic strategy
is focused on maintaining a conservative approach to mitigate risks associated with interest
rate fluctuations and market volatility.
```

## Timing summary

| Node | Started (offset) | Duration | Tool call(s) | Tool duration |
|---|---|---|---|---|
| `quant_data_pull` | +0.00s | 3502 ms | `get_fund_performance` | 6 ms |
| `qual_narrative_pull` | +0.00s | 4805 ms | `search_fund_commentary` | 582 ms |
| `compliance_check` | +4.81s | 4713 ms | `ComplianceVerdict` (structured output) | <1 ms |
| `final_synthesis` | +9.52s | 2118 ms | — | — |
| **Total** | | **11.64 s** | | |

## What this run demonstrates

- **Correct grounding**: every quantitative figure in the final response traces exactly to the
  seeded mock data for `INC2` - no hallucination.
- **Correct scoping**: `quant_data_pull` correctly declined the macro-strategy half of the
  question (not its job); `qual_narrative_pull` picked that up instead.
- **Correct join semantics**: `compliance_check` waited for both parallel entry points before
  starting, per the unconditional-edge design in `architecture.md`.
- **Rubric compliance achieved on the first pass**: the mandatory disclaimer and hedged
  forward-looking language were present without needing a `revise_draft` cycle.
- **Bedrock resolves Bug #2**: native `tool_use` for the structured-output call, zero internal
  retries needed - the exact failure mode documented for Ollama didn't occur here.
- **~30-50x faster than the equivalent Ollama run** (11.64s vs. 5-10+ minutes), for the same
  query shape - the practical motivation for the DEV model-provider toggle.

## S3 Auto Sync - Inner working

How a document dropped into the Knowledge Base's S3 docs bucket ends up searchable by
`qual_narrative_pull`'s `search_fund_commentary` tool, with **no manual `start_ingestion_job`
call**. Built by `infra/terraform/modules/kb-ingestion-sync` (SQS queue + DLQ, S3 bucket
notification, Lambda + event source mapping) plus
`infra/terraform/modules/iam/kb_ingestion_sync_role.tf` (the Lambda's execution role) and the
`kb_ingestion_dlq_depth` alarm in `modules/observability`. Wired into all three environments'
root modules identically, `count = var.enable_knowledge_base ? 1 : 0` (see CLAUDE.md's Phase 02
log, "Auto-sync RAG pipeline" entry, for the design decisions and trade-offs). Confirmed working
live against real AWS in dev on 2026-07-13 (ingestion job `7MWH1RDDPA`, see step 8 below).

Real dev resource names used throughout (from `name_prefix = "amc-orchestrator-dev"`):

| Resource | Name / ID |
|---|---|
| Docs bucket | `amc-orchestrator-dev-kb-docs-766354255780` |
| Events queue | `amc-orchestrator-dev-kb-ingestion-events` |
| DLQ | `amc-orchestrator-dev-kb-ingestion-dlq` |
| Lambda | `amc-orchestrator-dev-kb-ingestion-sync` |
| Lambda execution role | `amc-orchestrator-dev-kb-ingestion-sync-role` |
| Knowledge Base | `CLFXD2BCJX` |
| Data source | `FHWNEWR1PU` (`amc-orchestrator-dev-fund-commentary-docs`) |

### Step-by-step: from S3 upload to searchable document

1. **User (or CI) uploads a file to the docs bucket.**
   `aws s3 cp doc_inc2.txt s3://amc-orchestrator-dev-kb-docs-766354255780/` - or a delete of an
   existing key. This step itself is **not** automated by Terraform; it's the one manual/CI step
   this pipeline was built to remove all the *downstream* toil from (see
   `data/knowledge_base_store.py`'s `ensure_seeded()` docstring, and CLAUDE.md's "Auto-sync RAG
   pipeline" entry for why the initial upload stays manual).

2. **S3 bucket notification fires synchronously on the write.**
   `aws_s3_bucket_notification.docs` (`kb-ingestion-sync/main.tf`) is configured on the bucket for
   `s3:ObjectCreated:*` and `s3:ObjectRemoved:*`. S3 itself (not a Lambda, not polling) publishes
   an event describing the object key/bucket/event-type directly to SQS - this is a native S3
   feature, no compute runs at this step.

3. **The event lands in the SQS events queue.**
   `aws_sqs_queue.events` (`amc-orchestrator-dev-kb-ingestion-events`). Delivery from S3 is only
   possible because of `aws_sqs_queue_policy.events` - an explicit resource-based policy
   statement (`AllowS3SendMessage`) granting the `s3.amazonaws.com` service principal
   `sqs:SendMessage`, conditioned on `aws:SourceArn` matching this exact docs bucket's ARN (so no
   other bucket in the account can push into this queue). `depends_on` in `main.tf` guarantees
   this policy exists *before* the bucket notification is created, avoiding a race where S3
   attempts delivery before permission exists.

4. **The queue debounces rapid/bulk uploads instead of firing per-file.**
   This is the deliberate core design point: Bedrock allows only **one running ingestion job per
   data source at a time**, so triggering a Lambda invocation (and a `start_ingestion_job` call)
   per individual S3 event would mostly just collide. Instead,
   `aws_lambda_event_source_mapping.events` sets `batch_size = 10` and
   `maximum_batching_window_in_seconds = 300` (5 minutes) - the mapping waits up to 5 minutes
   (or until 10 messages accumulate, whichever comes first) before invoking the Lambda with the
   whole batch at once. Uploading 4 files in a burst (as in the live test) still results in
   **one** Lambda invocation and **one** ingestion job, not four.

5. **The event source mapping invokes the Lambda with the batch.**
   `amc-orchestrator-dev-kb-ingestion-sync` (Python 3.13, `sync_src/handler.py`, 256 MB, 120s
   timeout). It runs as `amc-orchestrator-dev-kb-ingestion-sync-role`, whose only three
   permissions (`kb_ingestion_sync_role.tf`) are: `bedrock:StartIngestionJob` (wildcarded to
   `knowledge-base/*` account-wide - see that file's comment on why it can't be scoped to this
   one KB's ARN without recreating an IAM↔KB module cycle), `sqs:ReceiveMessage` /
   `sqs:DeleteMessage` / `sqs:GetQueueAttributes` scoped to the events queue's ARN by predictable
   naming convention, and `logs:CreateLogGroup` / `CreateLogStream` / `PutLogEvents` scoped to its
   own log group. It cannot read or write the KB's content directly, only trigger a sync of it.

6. **The handler ignores the batch's actual contents and just triggers a full data-source
   re-sync.** `handler.py` never inspects `event["Records"]` for which keys changed - it calls
   `bedrock_agent.start_ingestion_job(knowledgeBaseId=KNOWLEDGE_BASE_ID,
   dataSourceId=DATA_SOURCE_ID)` unconditionally. This is intentional: Bedrock's ingestion job is
   already incremental/differential over the whole data source (it diffs against what's already
   indexed), so a full re-sync call correctly picks up every new/changed/deleted object in the
   batch without the Lambda needing to parse or track individual keys itself.

7. **Two possible outcomes from the `start_ingestion_job` call, both handled:**
   - **Success** (`200`, most common case): a real new `ingestionJobId` is returned and the
     function exits cleanly - SQS deletes the batch's messages from the queue since the Lambda
     returned without raising.
   - **`ConflictException`** (a job is already running for this data source, e.g. two uploads in
     quick succession outside one batching window): the handler treats this as a **success**, not
     a failure (`{"status": "sync_already_running"}`), and still lets SQS delete the messages -
     reasoning: the already-running job is incremental and will still pick up whatever new files
     triggered *this* invocation, so nothing is lost by not retrying.
   - **Any other `ClientError`** (a genuine failure - bad KB/data-source ID, throttling exhausted,
     permissions error, etc.): the handler re-raises. The Lambda invocation fails, and because
     this is an SQS-triggered async invocation, the **messages are not deleted** - they become
     visible again after the queue's visibility timeout (`lambda_timeout_seconds * 6` = 720s, per
     AWS's own SQS-Lambda sizing guidance, chosen specifically so a message can never become
     visible again *while* an invocation using it is still in flight).

8. **Genuine failures redrive to the DLQ after 3 attempts, and alarm.**
   `aws_sqs_queue.events`' `redrive_policy` sends a message to `amc-orchestrator-dev-kb-ingestion-dlq`
   after `maxReceiveCount = 3` failed receives. The `kb_ingestion_dlq_depth` CloudWatch alarm
   (`modules/observability`, gated on `kb_ingestion_dlq_name != ""`) watches
   `ApproximateNumberOfMessagesVisible` on that DLQ and fires through the shared
   `aws_sns_topic.alarms` topic the moment even one message lands there - the alarm's own
   description text is literally "a document sync genuinely failed after retries," to make clear
   this is not a transient-condition alarm.

9. **The document becomes retrievable once the ingestion job completes.**
   Once `start_ingestion_job` succeeds, Bedrock itself takes over: it reads the changed
   object(s) from the docs bucket, chunks/embeds them, and writes vectors into the configured
   vector store - in dev, S3 Vectors (`modules/s3-vectors`'s index), not OpenSearch (see
   CLAUDE.md's "S3 Vectors" section for why dev differs from staging/prod here). This part of the
   pipeline is fully managed by the `aws_bedrockagent_knowledge_base` resource Terraform already
   created in Pass 2 - the ingestion-sync module's only job was getting `start_ingestion_job`
   *called* automatically; the actual chunk/embed/index work was never something this repo
   implements itself. Once the job's status is `COMPLETE`, `search_fund_commentary`
   (`tools/qual_tools.py` → `data/knowledge_base_store.py` → Bedrock's managed `Retrieve` API)
   can find the new content on the very next query.

### Live proof (2026-07-13, real AWS, no manual CLI ingestion call made)

After uploading 4 mock-fund commentary `.txt` files to
`amc-orchestrator-dev-kb-docs-766354255780`:

```
aws bedrock-agent list-ingestion-jobs \
  --knowledge-base-id CLFXD2BCJX --data-source-id FHWNEWR1PU

ingestionJobId: 7MWH1RDDPA
status:         COMPLETE
startedAt:      2026-07-13T13:10:17Z
updatedAt:      2026-07-13T13:10:30Z
statistics:
  numberOfDocumentsScanned:        4
  numberOfNewDocumentsIndexed:     4
  numberOfModifiedDocumentsIndexed: 0
  numberOfDocumentsDeleted:        0
  numberOfDocumentsFailed:         0
```

Also confirmed at each layer, not just the end result:
- `aws s3api get-bucket-notification-configuration` on the docs bucket showed the `QueueConfigurations`
  entry pointing at the events queue for `ObjectCreated:*`/`ObjectRemoved:*`.
- `aws lambda list-event-source-mappings --function-name amc-orchestrator-dev-kb-ingestion-sync`
  showed `State: Enabled`, `BatchSize: 10`, `MaximumBatchingWindowInSeconds: 300`.
- The events queue briefly showed `ApproximateNumberOfMessagesNotVisible: 1` (a message actively
  being processed by the Lambda) before the ingestion job appeared - the expected sequence, not
  inferred.

No `start_ingestion_job` CLI/console call was made by a human for this run - step 5 above (the
Lambda) made it.
