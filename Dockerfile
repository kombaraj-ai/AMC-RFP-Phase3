# Amazon Bedrock AgentCore Runtime container image.
#
# Must be linux/arm64 - AgentCore Runtime runs on Graviton; this is a hard
# requirement, not a preference (confirmed against Strands' own AgentCore
# deployment guide). Build/push is a manual or CI step, deliberately never
# done by Terraform - see infra/terraform/README.md's "Pass 3" section for
# the exact commands and why.
#
# Build:  docker build --platform linux/arm64 -t <ecr_repository_url>:<tag> .
FROM --platform=linux/arm64 ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Dependencies first for better layer caching - only re-resolved when these
# actually change, not on every source edit.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache --no-install-project

COPY src/ ./src/
RUN uv sync --frozen --no-cache

# No `environments/.env.*` file is baked into the image on purpose: Terraform's
# `agent_runtime_artifact` sets real process environment variables directly
# (ENVIRONMENT, DYNAMODB_TABLE_NAME, BEDROCK_KNOWLEDGE_BASE_ID, etc. - see
# infra/terraform/modules/agentcore-runtime), and `Settings` reads those
# without needing an env file to exist at all (see config/settings.py's
# `get_settings()` - a missing env file just falls through to process env vars
# plus field defaults).

EXPOSE 8080

CMD ["uv", "run", "uvicorn", "amc_orchestrator.runtime_entrypoint:app", "--host", "0.0.0.0", "--port", "8080"]
