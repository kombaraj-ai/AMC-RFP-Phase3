"""Facade dispatching qual-data calls to Chroma (local) or a Bedrock Knowledge Base (aws).

Mirrors `config.model_factory.get_model`'s pattern: this is the only place that
chooses between the two concrete stores, so `tools/qual_tools.py` and `cli.py`/
`api/main.py`'s seeding never branch on `effective_data_backend` themselves.
"""

from __future__ import annotations

from amc_orchestrator.config.settings import Settings
from amc_orchestrator.data import chroma_store, knowledge_base_store


def ensure_seeded(settings: Settings) -> None:
    if settings.effective_data_backend == "local":
        chroma_store.ensure_seeded(settings.chroma_full_path, settings.chroma_collection_name)
    else:
        knowledge_base_store.ensure_seeded(settings.bedrock_knowledge_base_id)


def search_commentary(settings: Settings, query: str, n_results: int = 2) -> list[str]:
    if settings.effective_data_backend == "local":
        return chroma_store.search_commentary(
            settings.chroma_full_path, settings.chroma_collection_name, query, n_results=n_results
        )
    return knowledge_base_store.search_commentary(
        settings.bedrock_knowledge_base_id, settings.aws_region, query, n_results=n_results
    )
