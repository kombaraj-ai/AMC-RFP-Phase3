"""Structured output contract for the Compliance & Risk (LLM-as-a-Judge) agent."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ComplianceVerdict(BaseModel):
    """The compliance agent's structured verdict on a draft response.

    `evaluated_text` must be a verbatim echo of the exact narrative the agent
    judged - a mechanical copy task, not a summarization task - so that on the
    APPROVED path, `final_synthesis` knows the precise compliant wording
    (which may be the Revisor's rewrite, not the original draft) without
    needing to reconstruct it.
    """

    status: Literal["APPROVED", "REJECTED"] = Field(
        description="APPROVED if the evaluated text fully satisfies the compliance rubric, else REJECTED."
    )
    violations: list[str] = Field(
        default_factory=list,
        description="Specific rubric rules violated. Empty when status is APPROVED.",
    )
    suggested_edits: str = Field(
        default="",
        description="Concrete, actionable edits to resolve the violations. Empty when status is APPROVED.",
    )
    evaluated_text: str = Field(
        description="Verbatim copy of the exact narrative text that was judged, unchanged, in full."
    )
