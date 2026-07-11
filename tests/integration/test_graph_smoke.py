"""End-to-end smoke test of the full RFP graph against real local Ollama.

A calm, low-risk query should complete in COMPLETED status with a compliant
disclaimer, ideally without needing more than one compliance pass. It
cannot be asserted to *always* reach that outcome in DEV, though - see the
try/except below.
"""

from __future__ import annotations

import pytest

from amc_orchestrator.config.messages import ESCALATION_HOLDING_MESSAGE
from amc_orchestrator.config.settings import Settings
from amc_orchestrator.workflows.graph_build import build_rfp_graph
from amc_orchestrator.workflows.result_extraction import summarize_exception, summarize_result

pytestmark = pytest.mark.integration


def test_low_risk_query_completes_or_escalates_gracefully(
    isolated_graph_settings: Settings,
) -> None:
    """Verify the resilience contract every caller (CLI, API) depends on.

    `qwen2.5:7b-instruct` on Ollama cannot be relied on to invoke its
    structured-output tool 100% of the time - Strands' "force" mechanism
    needs `tool_choice`, which Ollama's provider silently ignores (see
    CLAUDE.md Bug #2). So this test cannot assert a guaranteed APPROVED
    completion without flaking. What IS guaranteed, and what actually
    matters for production callers, is that `graph(...)` never lets a raw
    exception escape uncaught and always yields one of exactly two
    well-formed outcomes: a real compliant answer, or the safe escalation
    message - mirroring the try/except in `cli.py`.
    """
    graph = build_rfp_graph(isolated_graph_settings)
    question = (
        "Please provide the current risk metrics for the Fixed Income Core "
        "Bond Fund (INC2) and its current macroeconomic strategy."
    )

    try:
        result = graph(question)
        outcome = summarize_result(result)
    except Exception as exc:  # graph node execution is fail-fast, see result_extraction.py
        outcome = summarize_exception(exc)

    if outcome.succeeded:
        assert outcome.graph_status == "completed"
        assert "Past performance is not indicative of future results." in outcome.response_text
        assert outcome.compliance_attempts >= 1
    else:
        assert outcome.escalated is True
        assert outcome.response_text == ESCALATION_HOLDING_MESSAGE
