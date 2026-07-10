"""Single source of truth for user-facing safe-fallback text.

Shared between `agents.synthesizer_agent` (the in-graph REJECTED-after-retries
escalation branch) and `workflows.result_extraction` (the graph-level
exception fallback, e.g. a `StructuredOutputException` from a model that
failed to invoke its structured-output tool), so both paths read identically
to callers/clients regardless of which one actually fired.
"""

ESCALATION_HOLDING_MESSAGE = (
    "This request requires manual compliance review before a response can be "
    "issued. Our automated compliance workflow could not produce an "
    "approved response within its retry limit. A member of the Compliance "
    "team will follow up directly."
)
