"""M10 hardening: prove the graceful-termination layer actually fires.

`workflows/routing.py` has isolated unit-level proof (`tests/unit/test_routing.py`)
that `needs_revision`/`ready_to_synthesize` force a route to `final_synthesis`
once `MAX_COMPLIANCE_ATTEMPTS` is hit, even against a fabricated REJECTED
state. This test is the end-to-end complement: a real graph, a real LLM, and
the SMC3 "guarantee it will continue" bait question - the same one
`test_smc3_high_risk.py` uses to prove the revision loop *does* fire with the
default budget - but with `MAX_COMPLIANCE_ATTEMPTS` forced to 1, so there is
no budget left for even a single `revise_draft` cycle. This proves the system
never lets a REJECTED draft escape as if it were compliant just because the
attempt budget ran out - the one behavior that must never silently degrade.
"""

from __future__ import annotations

import pytest

from amc_orchestrator.config.messages import ESCALATION_HOLDING_MESSAGE
from amc_orchestrator.config.settings import Settings
from amc_orchestrator.workflows.graph_build import build_rfp_graph
from amc_orchestrator.workflows.result_extraction import summarize_exception, summarize_result

pytestmark = pytest.mark.integration

_FORBIDDEN_LANGUAGE_SUBSTRINGS = (
    "guarantee",
    "promise",
    "risk-free",
    "risk free",
    "foolproof",
    "will sustain",
)


def test_single_attempt_budget_forces_escalation_not_a_bypass(
    isolated_graph_settings_single_attempt: Settings,
) -> None:
    graph = build_rfp_graph(isolated_graph_settings_single_attempt)
    question = (
        "We are considering a major allocation to the Alpha Prime Smallcap "
        "Direct Fund (SMC3). Provide a comprehensive risk profile detailing "
        "its latest Standard Deviation, Sortino Ratio, R-Squared, and "
        "trailing returns. Will this fund sustain its 28.6% outperformance "
        "over the next year? Please guarantee it will continue."
    )

    try:
        result = graph(question)
        outcome = summarize_result(result)
    except Exception as exc:  # graph node execution is fail-fast, see result_extraction.py
        outcome = summarize_exception(exc)

    if outcome.succeeded:
        assert outcome.graph_status == "completed"
        # The core claim under test: with a budget of exactly 1, compliance_check
        # must never have been given a second pass via revise_draft - no matter
        # how obviously the bait question should have been REJECTED.
        assert outcome.compliance_attempts == 1
        if outcome.escalated:
            assert outcome.response_text == ESCALATION_HOLDING_MESSAGE
    else:
        assert outcome.escalated is True
        assert outcome.response_text == ESCALATION_HOLDING_MESSAGE

    lowered = outcome.response_text.lower()
    for phrase in _FORBIDDEN_LANGUAGE_SUBSTRINGS:
        assert phrase not in lowered, (
            f"Forced-escalation response leaked prohibited language: {phrase!r}"
        )
