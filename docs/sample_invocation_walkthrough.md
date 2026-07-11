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
