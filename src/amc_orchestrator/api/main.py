"""FastAPI app factory for the AMC RFP & Portfolio Insight Orchestrator.

Startup uses `lifespan` (the current FastAPI/Starlette API) rather than the
deprecated `@app.on_event("startup")` seen in the original brainstorm doc -
see CLAUDE.md "API gotchas".
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from amc_orchestrator.api.routes.rfp import router as rfp_router
from amc_orchestrator.config.settings import get_settings
from amc_orchestrator.data import chroma_store, sqlite_store
from amc_orchestrator.observability.logging_setup import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    sqlite_store.ensure_seeded(settings.sqlite_full_path)
    chroma_store.ensure_seeded(settings.chroma_full_path, settings.chroma_collection_name)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)

    app = FastAPI(
        title="AMC RFP & Portfolio Insight Orchestrator",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(rfp_router, prefix="/api/v1")

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok", "environment": settings.environment}

    return app


app = create_app()
