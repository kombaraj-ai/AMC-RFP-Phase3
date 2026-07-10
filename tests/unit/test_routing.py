"""Unit tests for the compliance-loop routing conditions.

Uses lightweight duck-typed stand-ins for GraphState/GraphNode/NodeResult -
`build_routing_conditions` only ever touches `.execution_order` and
`.results`, so no real Strands Graph or Ollama call is needed here.
"""

from __future__ import annotations

from types import SimpleNamespace

from amc_orchestrator.schemas.compliance import ComplianceVerdict
from amc_orchestrator.workflows.routing import build_routing_conditions

COMPLIANCE_NODE = "compliance_check"


def _node(node_id: str) -> SimpleNamespace:
    return SimpleNamespace(node_id=node_id)


def _node_result(verdict: ComplianceVerdict | None) -> SimpleNamespace:
    agent_result = SimpleNamespace(structured_output=verdict) if verdict is not None else SimpleNamespace()
    return SimpleNamespace(result=agent_result)


def _state(execution_order: list[str], verdict: ComplianceVerdict | None) -> SimpleNamespace:
    results = {}
    if COMPLIANCE_NODE in execution_order:
        results[COMPLIANCE_NODE] = _node_result(verdict)
    return SimpleNamespace(
        execution_order=[_node(node_id) for node_id in execution_order],
        results=results,
    )


def _approved(text: str = "draft") -> ComplianceVerdict:
    return ComplianceVerdict(status="APPROVED", violations=[], suggested_edits="", evaluated_text=text)


def _rejected(text: str = "draft") -> ComplianceVerdict:
    return ComplianceVerdict(
        status="REJECTED", violations=["NO GUARANTEES"], suggested_edits="soften language", evaluated_text=text
    )


def test_approved_on_first_pass_routes_to_synthesis() -> None:
    needs_revision, ready_to_synthesize = build_routing_conditions(max_attempts=3)
    state = _state(["quant_data_pull", "qual_narrative_pull", COMPLIANCE_NODE], _approved())

    assert needs_revision(state) is False
    assert ready_to_synthesize(state) is True


def test_rejected_within_attempt_budget_routes_to_revisor() -> None:
    needs_revision, ready_to_synthesize = build_routing_conditions(max_attempts=3)
    state = _state(["quant_data_pull", "qual_narrative_pull", COMPLIANCE_NODE], _rejected())

    assert needs_revision(state) is True
    assert ready_to_synthesize(state) is False


def test_rejected_after_exhausting_attempts_forces_synthesis() -> None:
    needs_revision, ready_to_synthesize = build_routing_conditions(max_attempts=2)
    # compliance_check has already run twice (>= max_attempts) and is still REJECTED.
    state = _state(
        ["quant_data_pull", "qual_narrative_pull", COMPLIANCE_NODE, "revise_draft", COMPLIANCE_NODE],
        _rejected(),
    )

    assert needs_revision(state) is False
    assert ready_to_synthesize(state) is True


def test_missing_verdict_is_treated_as_rejected_while_attempts_remain() -> None:
    needs_revision, ready_to_synthesize = build_routing_conditions(max_attempts=3)
    state = _state(["quant_data_pull", "qual_narrative_pull", COMPLIANCE_NODE], None)

    assert needs_revision(state) is True
    assert ready_to_synthesize(state) is False


def test_missing_verdict_after_exhausting_attempts_forces_synthesis() -> None:
    needs_revision, ready_to_synthesize = build_routing_conditions(max_attempts=1)
    state = _state(["quant_data_pull", "qual_narrative_pull", COMPLIANCE_NODE], None)

    assert needs_revision(state) is False
    assert ready_to_synthesize(state) is True


def test_before_compliance_has_ever_run_neither_edge_fires() -> None:
    """Regression test: quant_data_pull/qual_narrative_pull complete in the
    first batch, before compliance_check has run at all. Both conditions
    must be False here, or revise_draft/final_synthesis would incorrectly
    fire in parallel with compliance_check's first pass (caught via an
    empirical CLI smoke test - see routing.py's module docstring)."""
    needs_revision, ready_to_synthesize = build_routing_conditions(max_attempts=3)
    state = _state(["quant_data_pull", "qual_narrative_pull"], None)

    assert needs_revision(state) is False
    assert ready_to_synthesize(state) is False
