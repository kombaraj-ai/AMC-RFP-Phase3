"""RFP submission endpoint - the HTTP equivalent of `cli.py`.

Applies the identical try/except-around-`graph(...)` safety pattern as
`cli.py` (see CLAUDE.md "Bug #2"): Strands node execution is fail-fast, so a
`StructuredOutputException` from `compliance_check` propagates as a raw
Python exception, not a `FAILED` GraphResult. Without this try/except, that
would surface to callers as an unhandled 500 instead of the intended
graceful escalation response.
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from amc_orchestrator.config.settings import Settings, get_settings
from amc_orchestrator.observability.logging_setup import bind_trace_context, clear_trace_context
from amc_orchestrator.workflows.graph_build import build_rfp_graph
from amc_orchestrator.workflows.result_extraction import (
    RfpOutcome,
    summarize_exception,
    summarize_result,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["rfp"])


class RfpRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        description="The client's institutional RFP / portfolio query.",
    )


@router.post("/rfp", response_model=RfpOutcome)
def submit_rfp(request: RfpRequest, settings: Settings = Depends(get_settings)) -> RfpOutcome:  # noqa: B008
    request_id = str(uuid.uuid4())
    bind_trace_context(trace_id=request_id)
    try:
        graph = build_rfp_graph(settings)
        try:
            result = graph(request.question)
            outcome = summarize_result(result)
        except Exception as exc:  # graph node execution is fail-fast; never 500 the caller
            logger.error("graph_invocation_failed", error=str(exc), error_type=type(exc).__name__)
            outcome = summarize_exception(exc)
        return outcome
    finally:
        clear_trace_context()
