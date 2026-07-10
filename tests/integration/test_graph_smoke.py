"""End-to-end smoke test of the full RFP graph against real local Ollama.

A calm, low-risk query should complete in COMPLETED status with a compliant
disclaimer, ideally without needing more than one compliance pass.
"""

from __future__ import annotations

import pytest

from amc_orchestrator.config.settings import Settings
from amc_orchestrator.workflows.graph_build import build_rfp_graph
from amc_orchestrator.workflows.result_extraction import summarize_result

pytestmark = pytest.mark.integration


def test_low_risk_query_completes_and_is_compliant(isolated_graph_settings: Settings) -> None:
    graph = build_rfp_graph(isolated_graph_settings)

    result = graph(
        "Please provide the current risk metrics for the Fixed Income Core "
        "Bond Fund (INC2) and its current macroeconomic strategy."
    )
    outcome = summarize_result(result)

    assert outcome.graph_status == "completed"
    assert outcome.succeeded is True
    assert "Past performance is not indicative of future results." in outcome.response_text
    assert outcome.compliance_attempts >= 1
