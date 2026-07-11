"""Qualitative fund-manager commentary store (Bedrock Knowledge Base, STAGING/PROD or DEV opt-in).

Plain boto3 + dicts, no Strands dependency - mirrors `chroma_store.py`'s shape so
`data/qual_store.py` can dispatch between the two without either caller-facing
function changing shape. Deliberately calls Bedrock's managed `Retrieve` API rather
than hand-rolling raw OpenSearch k-NN queries plus our own embedding calls - the
Knowledge Base Terraform provisions (`infra/terraform/modules/knowledge-base/`)
exists specifically to do embedding + retrieval end-to-end; reimplementing that here
would duplicate infrastructure that already does the job.
"""

from __future__ import annotations

import structlog
import boto3

logger = structlog.get_logger(__name__)


def _client(region: str):
    return boto3.client("bedrock-agent-runtime", region_name=region)


def ensure_seeded(knowledge_base_id: str) -> None:
    """Deliberate no-op.

    Unlike the DynamoDB/SQLite seed (an idempotent, cheap upsert safe to run on
    every startup), populating a Knowledge Base means uploading documents to S3
    and triggering an asynchronous `start_ingestion_job` - not something to run
    implicitly on every app startup. Document ingestion stays a separate,
    manual/CI step - see `infra/terraform/README.md`.
    """
    logger.info(
        "knowledge_base_store.ensure_seeded_noop",
        knowledge_base_id=knowledge_base_id,
        reason="KB ingestion is a separate manual/CI step, not run on app startup",
    )


def search_commentary(
    knowledge_base_id: str, region: str, query: str, n_results: int = 2
) -> list[str]:
    """Return up to `n_results` best-first passage texts, or `[]` if none found.

    Same flat `list[str]` shape as `chroma_store.search_commentary` - no scores,
    ids, or metadata - so `tools/qual_tools.py` needs no change to consume it.
    """
    response = _client(region).retrieve(
        knowledgeBaseId=knowledge_base_id,
        retrievalQuery={"text": query},
        retrievalConfiguration={
            "vectorSearchConfiguration": {"numberOfResults": n_results}
        },
    )
    results = response.get("retrievalResults", [])
    return [r["content"]["text"] for r in results if r.get("content", {}).get("text")]
