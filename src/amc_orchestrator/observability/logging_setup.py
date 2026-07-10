"""Structured JSON logging setup.

Isolates all logging configuration in one place so a later OpenTelemetry
migration (STAGING) only touches this module, not call sites throughout the
codebase - call sites always just do `structlog.get_logger(__name__)`.
"""

from __future__ import annotations

import logging
import sys

import structlog

_configured = False


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Configure structlog + stdlib logging once per process.

    Args:
        level: Standard logging level name, e.g. "DEBUG", "INFO".
        fmt: "json" for machine-readable production logs, "console" for a
            human-friendly local development renderer.
    """
    global _configured
    if _configured:
        return

    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer: structlog.typing.Processor
    if fmt == "console":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, structlog.processors.format_exc_info, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping().get(level.upper(), logging.INFO)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    _configured = True


def bind_trace_context(*, trace_id: str, request_id: str | None = None) -> None:
    """Bind correlation IDs to the current context so every log line downstream
    (across all agent/hook logging within this request) carries them."""
    structlog.contextvars.bind_contextvars(trace_id=trace_id, request_id=request_id or trace_id)


def clear_trace_context() -> None:
    structlog.contextvars.clear_contextvars()
