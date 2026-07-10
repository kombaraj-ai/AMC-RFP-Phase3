"""Compliance & Risk Agent - LLM-as-a-Judge guardrail.

Judges the combined quant + qual output (or the Revisor's latest rewrite, on
a loop-back pass) against the AMC compliance rubric and returns a structured
`ComplianceVerdict`, never free text, so the graph's routing conditions can
make a deterministic decision.
"""

from __future__ import annotations

from strands import Agent

from amc_orchestrator.config.compliance_rubric import COMPLIANCE_RUBRIC
from amc_orchestrator.config.model_factory import get_model
from amc_orchestrator.config.settings import Settings
from amc_orchestrator.observability.hooks import LoggingHookProvider
from amc_orchestrator.schemas.compliance import ComplianceVerdict

NODE_NAME = "compliance_check"

SYSTEM_PROMPT = f"""\
You are the Chief Compliance Officer (CCO) Agent for a Mutual Fund AMC,
acting as an LLM-as-a-Judge. You must always respond with a structured
compliance verdict - never free text.

You will receive input structured like this:

    Original Task: <the client's question>

    Inputs from previous nodes:

    From quant_data_pull:
      - Agent: <raw quantitative fund metrics>

    From qual_narrative_pull:
      - Agent: <raw fund manager commentary/narrative>

    From revise_draft:
      - Agent: <the Revisor's latest rewritten draft, only present on a re-check>

How to determine the text to judge:
- If a "From revise_draft:" section is present, that is the latest revised
  draft. Evaluate that text directly - it already incorporates the quant
  numbers and qualitative narrative.
- Otherwise (first pass), synthesize a short, client-ready draft yourself by
  combining the quant metrics and qualitative narrative into a coherent
  answer to the Original Task, then evaluate that draft you just wrote.

Evaluate the draft strictly against this rubric:
{COMPLIANCE_RUBRIC}

You MUST call your structured output tool with:
- status: "APPROVED" if the draft fully satisfies every rubric rule, else "REJECTED".
- violations: the specific rubric rules violated (empty list if APPROVED).
- suggested_edits: concrete, actionable edits to resolve every violation
  (empty string if APPROVED).
- evaluated_text: a VERBATIM copy of the exact draft text you judged, in full,
  unchanged. This is a copy task, not a summary - reproduce it exactly.
"""


def get_compliance_agent(settings: Settings) -> Agent:
    """Build the Compliance & Risk (LLM-as-a-Judge) Agent."""
    model = get_model(settings, temperature=settings.model_temperature_judge)
    return Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        structured_output_model=ComplianceVerdict,
        name=NODE_NAME,
        hooks=[LoggingHookProvider(NODE_NAME)],
    )
