"""Structured logging hooks attached to every agent.

Gives per-agent, per-tool-call structured logs (with whatever trace/request
IDs are bound via `logging_setup.bind_trace_context`) without any business
logic in the agents themselves having to log anything.
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from strands.hooks import (
    AfterInvocationEvent,
    AfterToolCallEvent,
    BeforeInvocationEvent,
    BeforeToolCallEvent,
    HookProvider,
    HookRegistry,
)

logger = structlog.get_logger(__name__)


class LoggingHookProvider(HookProvider):
    """Logs agent invocation and tool-call lifecycle events as structured JSON."""

    def __init__(self, node_name: str) -> None:
        self._node_name = node_name
        self._invocation_started_at: dict[int, float] = {}

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeInvocationEvent, self._on_before_invocation)
        registry.add_callback(AfterInvocationEvent, self._on_after_invocation)
        registry.add_callback(BeforeToolCallEvent, self._on_before_tool_call)
        registry.add_callback(AfterToolCallEvent, self._on_after_tool_call)

    def _on_before_invocation(self, event: BeforeInvocationEvent) -> None:
        self._invocation_started_at[id(event.agent)] = time.monotonic()
        logger.debug("agent_invocation_started", node=self._node_name)

    def _on_after_invocation(self, event: AfterInvocationEvent) -> None:
        started_at = self._invocation_started_at.pop(id(event.agent), None)
        duration_ms = round((time.monotonic() - started_at) * 1000) if started_at else None
        stop_reason = getattr(event.result, "stop_reason", None)
        logger.info(
            "agent_invocation_completed",
            node=self._node_name,
            duration_ms=duration_ms,
            stop_reason=stop_reason,
        )

    def _on_before_tool_call(self, event: BeforeToolCallEvent) -> None:
        logger.debug(
            "tool_call_started",
            node=self._node_name,
            tool_name=event.tool_use.get("name"),
        )

    def _on_after_tool_call(self, event: AfterToolCallEvent) -> None:
        logger.info(
            "tool_call_completed",
            node=self._node_name,
            tool_name=event.tool_use.get("name"),
            status=event.result.get("status") if isinstance(event.result, dict) else None,
            had_exception=event.exception is not None,
        )
