"""M10 hardening: a nonexistent fund ticker must be handled honestly, not crash.

`get_fund_performance` (`tools/quant_tools.py`) already has a deterministic
unit-level proof that it returns an error payload for an unknown ticker
(`tests/unit/test_tools.py::test_get_fund_performance_unknown_ticker_returns_error_payload`).
This test is the end-to-end complement: does the whole graph - agent
reasoning included, not just the tool wrapper - stay resilient and honest
when asked about a fund that was never seeded, rather than silently
fabricating numbers for it or crashing the graph.
"""

from __future__ import annotations

import pytest

from amc_orchestrator.config.settings import Settings
from amc_orchestrator.workflows.graph_build import build_rfp_graph
from amc_orchestrator.workflows.result_extraction import summarize_exception, summarize_result

pytestmark = pytest.mark.integration

_NOT_FOUND_SIGNALS = (
    "no data",
    "not found",
    "no performance data",
    "no record",
    "could not find",
    "couldn't find",
    "unable to locate",
    "does not exist",
    "doesn't exist",
    "no information",
    "no matching fund",
    "not available",
    "no such fund",
)


def test_unknown_ticker_reported_honestly_not_fabricated(
    isolated_graph_settings: Settings,
) -> None:
    graph = build_rfp_graph(isolated_graph_settings)
    question = (
        "Please provide the current risk metrics, including NAV, Alpha, and "
        "Beta, for the Quantum Horizon Innovation Fund (ZZZ9)."
    )

    try:
        result = graph(question)
        outcome = summarize_result(result)
    except Exception as exc:  # graph node execution is fail-fast, see result_extraction.py
        outcome = summarize_exception(exc)

    assert outcome.response_text, "Response text must never be empty."

    if not outcome.succeeded:
        # Graceful escalation (see CLAUDE.md Bug #2) is an acceptable outcome
        # here too - the escalation message never claims fabricated data.
        assert outcome.escalated is True
        return

    lowered = outcome.response_text.lower()
    assert any(signal in lowered for signal in _NOT_FOUND_SIGNALS), (
        "Response for an unseeded ticker (ZZZ9) did not honestly report missing "
        f"data via any expected phrase - got: {outcome.response_text!r}"
    )
