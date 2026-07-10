"""Builds the AMC RFP Orchestrator's cyclic Strands Graph.

Topology (see docs/architecture.md for the full rationale): every downstream
consumer gets a DIRECT edge to the actual source of the data it needs (quant,
qual) rather than chaining through an intermediary, so the Revisor and
Synthesizer always have raw grounding straight from source - never a
paraphrase - regardless of how many times the compliance loop has run.

    quant_data_pull ----+------------------------+---------------+
                         |                        |               |
    qual_narrative_pull -+-> compliance_check      |               |
                         |         |                |               |
                         |  (all three edges below share the SAME   |
                         |   condition function, so a node becomes  |
                         |   ready only once compliance_check has   |
                         |   run - see routing.py - and its input   |
                         |   still includes quant+qual as grounding)|
                         |         v                                |
                         +--(needs_revision)--> revise_draft --------+
                         +--(ready_to_synthesize)--> final_synthesis

                         compliance_check <--------------------------
                         (unconditional loop-back edge from revise_draft)

CRITICAL: the edges from quant_data_pull/qual_narrative_pull into
revise_draft/final_synthesis MUST carry the same condition as the edge from
compliance_check. Strands Graph schedules a node as soon as ANY ONE of its
incoming edges from the just-completed batch is satisfied (OR-semantics, not
AND) - quant/qual complete in the very first batch, so unconditional edges
from them would make revise_draft/final_synthesis ready immediately,
in parallel with compliance_check's first pass, before any verdict exists.
This was caught empirically via a CLI smoke test before being fixed here.
"""

from __future__ import annotations

from strands.multiagent import GraphBuilder
from strands.multiagent.graph import Graph

from amc_orchestrator.agents.compliance_agent import NODE_NAME as COMPLIANCE_NODE, get_compliance_agent
from amc_orchestrator.agents.qual_agent import NODE_NAME as QUAL_NODE, get_qual_agent
from amc_orchestrator.agents.quant_agent import NODE_NAME as QUANT_NODE, get_quant_agent
from amc_orchestrator.agents.revisor_agent import NODE_NAME as REVISE_NODE, get_revisor_agent
from amc_orchestrator.agents.synthesizer_agent import NODE_NAME as SYNTHESIS_NODE, get_synthesizer_agent
from amc_orchestrator.config.settings import Settings
from amc_orchestrator.workflows.routing import build_routing_conditions


def build_rfp_graph(settings: Settings) -> Graph:
    """Construct and compile the RFP Orchestrator graph for the given settings."""
    needs_revision, ready_to_synthesize = build_routing_conditions(settings.max_compliance_attempts)

    builder = GraphBuilder()

    quant = builder.add_node(get_quant_agent(settings), QUANT_NODE)
    qual = builder.add_node(get_qual_agent(settings), QUAL_NODE)
    compliance = builder.add_node(get_compliance_agent(settings), COMPLIANCE_NODE)
    revisor = builder.add_node(get_revisor_agent(settings), REVISE_NODE)
    synthesizer = builder.add_node(get_synthesizer_agent(settings), SYNTHESIS_NODE)

    # quant/qual always feed compliance_check directly, unconditionally.
    builder.add_edge(quant, compliance)
    builder.add_edge(qual, compliance)

    # Direct fan-out for grounding into revise_draft/final_synthesis - but
    # gated by the SAME condition as the compliance edge (see module
    # docstring) so they only become ready once compliance_check has run.
    builder.add_edge(quant, revisor, condition=needs_revision)
    builder.add_edge(qual, revisor, condition=needs_revision)
    builder.add_edge(compliance, revisor, condition=needs_revision)

    builder.add_edge(quant, synthesizer, condition=ready_to_synthesize)
    builder.add_edge(qual, synthesizer, condition=ready_to_synthesize)
    builder.add_edge(compliance, synthesizer, condition=ready_to_synthesize)

    # Loop-back: a revised draft must be re-checked before it can synthesize.
    builder.add_edge(revisor, compliance)

    builder.set_entry_point(QUANT_NODE)
    builder.set_entry_point(QUAL_NODE)
    builder.set_execution_timeout(settings.graph_execution_timeout_seconds)
    builder.set_max_node_executions(settings.graph_max_node_executions)
    builder.reset_on_revisit(True)

    return builder.build()
