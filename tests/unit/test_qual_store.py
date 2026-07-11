"""Unit tests for `data.qual_store`'s dispatch logic only.

Not re-testing chroma_store/knowledge_base_store's own behavior (covered in
their own test modules) - just that `effective_data_backend` picks the right
one.
"""

from __future__ import annotations

from unittest.mock import patch

from amc_orchestrator.config.settings import Settings
from amc_orchestrator.data import qual_store


def test_local_backend_dispatches_to_chroma_store() -> None:
    settings = Settings(environment="dev", data_backend="local")

    with patch(
        "amc_orchestrator.data.qual_store.chroma_store.search_commentary",
        return_value=["passage"],
    ) as mocked:
        results = qual_store.search_commentary(settings, "query", n_results=2)

    mocked.assert_called_once_with(
        settings.chroma_full_path, settings.chroma_collection_name, "query", n_results=2
    )
    assert results == ["passage"]


def test_aws_backend_dispatches_to_knowledge_base_store() -> None:
    settings = Settings(
        environment="dev", data_backend="aws", bedrock_knowledge_base_id="kb-123"
    )

    with patch(
        "amc_orchestrator.data.qual_store.knowledge_base_store.search_commentary",
        return_value=["passage"],
    ) as mocked:
        results = qual_store.search_commentary(settings, "query", n_results=2)

    mocked.assert_called_once_with("kb-123", settings.aws_region, "query", n_results=2)
    assert results == ["passage"]


def test_ensure_seeded_dispatches_by_backend() -> None:
    local_settings = Settings(environment="dev", data_backend="local")
    aws_settings = Settings(
        environment="dev", data_backend="aws", bedrock_knowledge_base_id="kb-123"
    )

    with patch("amc_orchestrator.data.qual_store.chroma_store.ensure_seeded") as local_mock:
        qual_store.ensure_seeded(local_settings)
    local_mock.assert_called_once_with(
        local_settings.chroma_full_path, local_settings.chroma_collection_name
    )

    with patch(
        "amc_orchestrator.data.qual_store.knowledge_base_store.ensure_seeded"
    ) as aws_mock:
        qual_store.ensure_seeded(aws_settings)
    aws_mock.assert_called_once_with("kb-123")
