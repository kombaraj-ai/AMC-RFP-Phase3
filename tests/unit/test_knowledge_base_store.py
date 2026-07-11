"""Unit tests for `data.knowledge_base_store`, mocked boto3 - no real AWS.

Mirrors `test_chroma_store.py`'s intent: `search_commentary` must return a
flat `list[str]` (best-first passage text, no scores/ids/metadata) so
`tools/qual_tools.py` needs no change to consume either backend.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from amc_orchestrator.data import knowledge_base_store


def test_search_commentary_returns_flat_list_of_passages() -> None:
    client = MagicMock()
    client.retrieve.return_value = {
        "retrievalResults": [
            {"content": {"text": "Passage one."}},
            {"content": {"text": "Passage two."}},
        ]
    }

    with patch("amc_orchestrator.data.knowledge_base_store._client", return_value=client):
        results = knowledge_base_store.search_commentary(
            "kb-123", "us-east-1", "query", n_results=2
        )

    assert results == ["Passage one.", "Passage two."]
    client.retrieve.assert_called_once_with(
        knowledgeBaseId="kb-123",
        retrievalQuery={"text": "query"},
        retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 2}},
    )


def test_search_commentary_returns_empty_list_when_no_results() -> None:
    client = MagicMock()
    client.retrieve.return_value = {"retrievalResults": []}

    with patch("amc_orchestrator.data.knowledge_base_store._client", return_value=client):
        assert knowledge_base_store.search_commentary("kb-123", "us-east-1", "query") == []


def test_ensure_seeded_is_a_documented_noop() -> None:
    knowledge_base_store.ensure_seeded("kb-123")  # must not raise, must not call AWS
