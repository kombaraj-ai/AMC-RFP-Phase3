"""Compliance & Risk Agent - LLM-as-a-Judge guardrail.

Judges the combined quant + qual output (or the Revisor's latest rewrite, on
a loop-back pass) against the AMC compliance rubric and returns a structured
`ComplianceVerdict`, never free text, so the graph's routing conditions can
make a deterministic decision.
"""

from __future__ import annotations

import copy
from collections.abc import AsyncIterator
from typing import Any

import structlog
from strands import Agent
from strands.types.exceptions import StructuredOutputException

from amc_orchestrator.config.compliance_rubric import COMPLIANCE_RUBRIC
from amc_orchestrator.config.model_factory import get_model
from amc_orchestrator.config.settings import Settings
from amc_orchestrator.observability.hooks import LoggingHookProvider
from amc_orchestrator.schemas.compliance import ComplianceVerdict

NODE_NAME = "compliance_check"

logger = structlog.get_logger(__name__)

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


class _RetryingComplianceAgent(Agent):
    """Compliance Agent that retries the whole turn on `StructuredOutputException`.

    `qwen2.5:7b-instruct` occasionally fails to invoke the structured-output
    tool even after Strands forces it (see CLAUDE.md "Bug #2" - observed on
    2 of 3 end-to-end CLI runs). Strands only auto-retries model calls for
    `ModelThrottledException` (`strands.event_loop._retry.ModelRetryStrategy`),
    never for this exception, so a clean-slate manual retry is layered on top
    here: on failure, the conversation is rolled back to what it was before
    the attempt and re-sent from scratch, up to `max_attempts` times total.
    """

    def __init__(self, *, max_attempts: int = 3, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._max_structured_output_attempts = max_attempts

    async def stream_async(
        self, prompt: Any = None, *, invocation_state: dict[str, Any] | None = None, **kwargs: Any
    ) -> AsyncIterator[Any]:
        messages_before_attempt = copy.deepcopy(self.messages)
        for attempt in range(1, self._max_structured_output_attempts + 1):
            try:
                stream = super().stream_async(prompt, invocation_state=invocation_state, **kwargs)
                async for event in stream:
                    yield event
                return
            except StructuredOutputException:
                self.messages = copy.deepcopy(messages_before_attempt)
                if attempt == self._max_structured_output_attempts:
                    raise
                logger.warning(
                    "compliance_structured_output_retry",
                    node=NODE_NAME,
                    attempt=attempt,
                    max_attempts=self._max_structured_output_attempts,
                )


def get_compliance_agent(settings: Settings) -> Agent:
    """Build the Compliance & Risk (LLM-as-a-Judge) Agent."""
    model = get_model(settings, temperature=settings.model_temperature_judge)
    return _RetryingComplianceAgent(
        max_attempts=settings.compliance_structured_output_max_attempts,
        model=model,
        system_prompt=SYSTEM_PROMPT,
        structured_output_model=ComplianceVerdict,
        name=NODE_NAME,
        hooks=[LoggingHookProvider(NODE_NAME)],
    )
