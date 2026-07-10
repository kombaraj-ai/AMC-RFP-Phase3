"""Conditional edge routing for the RFP graph's compliance self-correction loop.

Kept separate from `graph_build.py` so these condition functions are
unit-testable against a fabricated `GraphState`-like stand-in, without ever
invoking Ollama.

Termination has two layers (see docs/architecture.md): a hard safety-net
(`GraphBuilder.set_max_node_executions`, which - if actually hit - fails the
whole graph with NO output) and this module's graceful primary logic, which
forces a route to `final_synthesis` once `max_attempts` compliance checks
have run, even if the verdict is still REJECTED. The hard ceiling must never
be the thing that actually fires.

IMPORTANT - why `needs_revision`/`ready_to_synthesize` must short-circuit to
False when compliance_check has not executed at all yet: Strands Graph node
readiness uses OR-semantics across a node's incoming edges evaluated against
the just-completed batch (see `Graph._is_node_ready_with_conditions` in the
installed SDK) - a node becomes ready as soon as ANY ONE incoming edge from
the just-completed batch is satisfied, not only once ALL incoming edges are
satisfied. `revise_draft` and `final_synthesis` in `graph_build.py` have
edges from quant/qual/compliance ALL sharing this same condition (so that
`_build_node_input` includes all three as grounding once the condition is
true) - but quant_data_pull and qual_narrative_pull complete in the very
first batch, before compliance_check has run even once. Without the
`attempts == 0 -> False` short-circuit here, a "missing verdict" (intended
to mean "compliance ran but produced no structured output") would also be
true at that point, incorrectly firing revise_draft/final_synthesis in
parallel with compliance_check's first pass. This was caught empirically: an
early CLI smoke test showed `revise_draft` and `final_synthesis` starting
immediately after quant/qual, before compliance_check had produced any
verdict at all.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from amc_orchestrator.agents.compliance_agent import NODE_NAME as COMPLIANCE_NODE_ID
from amc_orchestrator.schemas.compliance import ComplianceVerdict

if TYPE_CHECKING:
    from strands.multiagent.graph import GraphState


class ConditionFn(Protocol):
    def __call__(self, state: "GraphState") -> bool: ...


def _compliance_attempt_count(state: "GraphState") -> int:
    return sum(1 for node in state.execution_order if node.node_id == COMPLIANCE_NODE_ID)


def _latest_compliance_verdict(state: "GraphState") -> ComplianceVerdict | None:
    node_result = state.results.get(COMPLIANCE_NODE_ID)
    if node_result is None:
        return None
    agent_result = node_result.result
    if isinstance(agent_result, Exception):
        return None
    return getattr(agent_result, "structured_output", None)


def build_routing_conditions(max_attempts: int) -> tuple[ConditionFn, ConditionFn]:
    """Return (`needs_revision`, `ready_to_synthesize`) condition functions bound
    to `max_attempts` compliance checks.

    A missing/malformed verdict (e.g. the model failed to produce structured
    output) is treated the same as REJECTED for routing purposes: retry via
    the Revisor while attempts remain, otherwise force synthesis (where the
    Synthesizer's own prompt treats anything other than an exact "APPROVED"
    status as the safe-escalation branch).
    """

    def needs_revision(state: "GraphState") -> bool:
        attempts = _compliance_attempt_count(state)
        if attempts == 0:
            # compliance_check has not judged anything yet - nothing to revise.
            return False
        if attempts >= max_attempts:
            return False
        verdict = _latest_compliance_verdict(state)
        return verdict is None or verdict.status == "REJECTED"

    def ready_to_synthesize(state: "GraphState") -> bool:
        if _compliance_attempt_count(state) == 0:
            # compliance_check has not judged anything yet - nothing to synthesize.
            return False
        return not needs_revision(state)

    return needs_revision, ready_to_synthesize
