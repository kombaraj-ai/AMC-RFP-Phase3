"""Packaged entry point (`amc-orchestrator` console script, see pyproject.toml)
that starts the FastAPI server via uvicorn.

For direct graph invocation without an HTTP server, use `cli.py` instead.
"""

from __future__ import annotations

import uvicorn

from amc_orchestrator.config.settings import get_settings


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "amc_orchestrator.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.environment == "dev",
    )


if __name__ == "__main__":
    run()
