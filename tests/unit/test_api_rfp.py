"""Unit tests for the `/api/v1/rfp` endpoint.

Patches `build_rfp_graph` with a fake callable so this exercises FastAPI
request/response wiring and the try/except-around-`graph(...)` safety net
(mirroring `cli.py` - see CLAUDE.md "Bug #2") without needing a real Ollama
server. Fake `GraphResult`/`NodeResult` stand-ins follow the same duck-typing
approach as `tests/unit/test_routing.py`.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from strands.types.exceptions import StructuredOutputException

from amc_orchestrator.api.main import create_app
from amc_orchestrator.config.messages import ESCALATION_HOLDING_MESSAGE


def _fake_graph_result(*, synthesis_text: str, compliance_status: str) -> SimpleNamespace:
    compliance_result = SimpleNamespace(
        result=SimpleNamespace(structured_output=SimpleNamespace(status=compliance_status)),
    )
    synthesis_result = SimpleNamespace(result=synthesis_text)
    execution_order = [
        SimpleNamespace(node_id="quant_data_pull"),
        SimpleNamespace(node_id="qual_narrative_pull"),
        SimpleNamespace(node_id="compliance_check"),
    ]
    return SimpleNamespace(
        status=SimpleNamespace(value="completed"),
        execution_order=execution_order,
        results={"compliance_check": compliance_result, "final_synthesis": synthesis_result},
    )


def test_health() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_rfp_returns_compliant_completion() -> None:
    fake_result = _fake_graph_result(
        synthesis_text="Compliant answer. Past performance is not indicative of future results.",
        compliance_status="APPROVED",
    )
    fake_graph = lambda question: fake_result  # noqa: E731

    with patch("amc_orchestrator.api.routes.rfp.build_rfp_graph", return_value=fake_graph):
        client = TestClient(create_app())
        response = client.post(
            "/api/v1/rfp", json={"question": "What is the risk profile of INC2?"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["succeeded"] is True
    assert body["escalated"] is False
    assert body["graph_status"] == "completed"


def test_rfp_degrades_to_escalation_on_structured_output_failure() -> None:
    def raising_graph(question: str) -> None:
        raise StructuredOutputException("model failed to invoke the structured output tool")

    with patch("amc_orchestrator.api.routes.rfp.build_rfp_graph", return_value=raising_graph):
        client = TestClient(create_app())
        response = client.post(
            "/api/v1/rfp", json={"question": "What is the risk profile of INC2?"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["succeeded"] is False
    assert body["escalated"] is True
    assert body["response_text"] == ESCALATION_HOLDING_MESSAGE


def test_rfp_rejects_empty_question() -> None:
    client = TestClient(create_app())
    response = client.post("/api/v1/rfp", json={"question": ""})
    assert response.status_code == 422
