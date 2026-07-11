"""Direct graph invocation from a terminal - the pre-API smoke-testing path.

Usage:
    uv run python -m amc_orchestrator.cli "<client question>"
"""

from __future__ import annotations

import sys
import uuid

import structlog

from amc_orchestrator.config.settings import get_settings
from amc_orchestrator.data import qual_store, quant_store
from amc_orchestrator.observability.logging_setup import bind_trace_context, configure_logging
from amc_orchestrator.workflows.graph_build import build_rfp_graph
from amc_orchestrator.workflows.result_extraction import summarize_exception, summarize_result

logger = structlog.get_logger(__name__)


def bootstrap_dev_data() -> None:
    """Idempotently seed the active data backend (SQLite+Chroma, or DynamoDB+KB)."""
    settings = get_settings()
    quant_store.ensure_seeded(settings)
    qual_store.ensure_seeded(settings)


def run_rfp_query(question: str) -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, fmt="console" if settings.environment == "dev" else "json")
    bind_trace_context(trace_id=str(uuid.uuid4()))

    bootstrap_dev_data()

    print(f"--- Processing Client Query: '{question}' ---\n")
    graph = build_rfp_graph(settings)
    try:
        result = graph(question)
        outcome = summarize_result(result)
    except Exception as exc:  # graph node execution is fail-fast; never crash the caller
        logger.error("graph_invocation_failed", error=str(exc), error_type=type(exc).__name__)
        outcome = summarize_exception(exc)

    print("\n--- FINAL RFP RESPONSE ---")
    print(outcome.response_text)
    print("\n--- METADATA ---")
    print(f"graph_status={outcome.graph_status}")
    print(f"compliance_attempts={outcome.compliance_attempts}")
    print(f"escalated={outcome.escalated}")


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: uv run python -m amc_orchestrator.cli "<client question>"')
        raise SystemExit(1)
    run_rfp_query(sys.argv[1])


if __name__ == "__main__":
    main()
