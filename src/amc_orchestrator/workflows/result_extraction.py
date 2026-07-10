"""Helpers to pull a clean, API/CLI-friendly summary out of a raw GraphResult.

Isolated here because `GraphResult`'s shape (NodeResult wrapping AgentResult,
execution_order as GraphNode objects, etc.) is an internal Strands detail that
both `cli.py` and `api/routes/rfp.py` need translated the same way.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from amc_orchestrator.agents.compliance_agent import NODE_NAME as COMPLIANCE_NODE
from amc_orchestrator.agents.synthesizer_agent import NODE_NAME as SYNTHESIS_NODE
from amc_orchestrator.config.messages import ESCALATION_HOLDING_MESSAGE

if TYPE_CHECKING:
    from strands.multiagent.graph import GraphResult


@dataclass(frozen=True)
class RfpOutcome:
    succeeded: bool
    response_text: str
    compliance_attempts: int
    escalated: bool
    graph_status: str


def summarize_result(result: "GraphResult") -> RfpOutcome:
    """Translate a raw `GraphResult` into an `RfpOutcome` for callers."""
    graph_status = result.status.value if hasattr(result.status, "value") else str(result.status)

    compliance_attempts = sum(
        1 for node in result.execution_order if node.node_id == COMPLIANCE_NODE
    )

    synthesis_node_result = result.results.get(SYNTHESIS_NODE)
    if synthesis_node_result is None or isinstance(synthesis_node_result.result, Exception):
        return RfpOutcome(
            succeeded=False,
            response_text=ESCALATION_HOLDING_MESSAGE,
            compliance_attempts=compliance_attempts,
            escalated=True,
            graph_status=graph_status,
        )

    response_text = str(synthesis_node_result.result)

    compliance_node_result = result.results.get(COMPLIANCE_NODE)
    final_verdict = (
        getattr(compliance_node_result.result, "structured_output", None)
        if compliance_node_result is not None and not isinstance(compliance_node_result.result, Exception)
        else None
    )
    escalated = final_verdict is None or final_verdict.status != "APPROVED"

    return RfpOutcome(
        succeeded=True,
        response_text=response_text,
        compliance_attempts=compliance_attempts,
        escalated=escalated,
        graph_status=graph_status,
    )


def summarize_exception(exc: BaseException) -> RfpOutcome:
    """Build a safe `RfpOutcome` when the graph invocation raised outright.

    Strands node execution is fail-fast: an exception inside any node (e.g.
    `StructuredOutputException` when a model fails to invoke its structured
    output tool even after being forced - observed empirically with
    `qwen2.5:7b-instruct` on occasion) propagates all the way out of
    `graph(...)` as a raw Python exception, not a FAILED `GraphResult`. This
    is the fallback for that path so callers (CLI, API) never crash outright
    and never fabricate compliant-looking content when the graph didn't even
    complete.
    """
    return RfpOutcome(
        succeeded=False,
        response_text=ESCALATION_HOLDING_MESSAGE,
        compliance_attempts=0,
        escalated=True,
        graph_status=f"error: {type(exc).__name__}: {exc}",
    )
