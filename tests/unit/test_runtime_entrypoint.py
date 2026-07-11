"""Unit tests for the AgentCore Runtime `@app.entrypoint` handler.

Patches `build_rfp_graph` with a fake callable, exactly mirroring
`test_api_rfp.py`'s approach for the FastAPI route - this entrypoint reuses
the exact same `workflows.result_extraction` translation, so it should
degrade to escalation the same way, not crash the runtime container.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from amc_orchestrator import runtime_entrypoint
from amc_orchestrator.config.messages import ESCALATION_HOLDING_MESSAGE


def _fake_graph_result(*, synthesis_text: str, compliance_status: str) -> SimpleNamespace:
    compliance_result = SimpleNamespace(
        result=SimpleNamespace(structured_output=SimpleNamespace(status=compliance_status)),
    )
    synthesis_result = SimpleNamespace(result=synthesis_text)
    execution_order = [SimpleNamespace(node_id="compliance_check")]
    return SimpleNamespace(
        status=SimpleNamespace(value="completed"),
        execution_order=execution_order,
        results={"compliance_check": compliance_result, "final_synthesis": synthesis_result},
    )


def test_invoke_returns_compliant_outcome() -> None:
    fake_result = _fake_graph_result(
        synthesis_text="Compliant answer.", compliance_status="APPROVED"
    )
    fake_graph = lambda question: fake_result  # noqa: E731

    with patch("amc_orchestrator.runtime_entrypoint.build_rfp_graph", return_value=fake_graph):
        response = runtime_entrypoint.invoke({"prompt": "What is the risk profile of INC2?"})

    assert response["succeeded"] is True
    assert response["escalated"] is False
    assert response["response_text"] == "Compliant answer."


def test_invoke_degrades_to_escalation_on_exception() -> None:
    def raising_graph(question: str) -> None:
        raise RuntimeError("boom")

    with patch(
        "amc_orchestrator.runtime_entrypoint.build_rfp_graph", return_value=raising_graph
    ):
        response = runtime_entrypoint.invoke({"prompt": "What is the risk profile of INC2?"})

    assert response["succeeded"] is False
    assert response["escalated"] is True
    assert response["response_text"] == ESCALATION_HOLDING_MESSAGE


def test_invoke_rejects_missing_prompt() -> None:
    response = runtime_entrypoint.invoke({})
    assert "error" in response
