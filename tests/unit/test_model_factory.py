"""Unit tests for `get_model` - construction only, no real network/AWS calls.

Constructing `OllamaModel`/`BedrockModel` does not itself contact Ollama or
AWS (verified manually before writing these), so this is safe and fast to
unit-test without mocking.
"""

from __future__ import annotations

from strands.models import BedrockModel
from strands.models.ollama import OllamaModel

from amc_orchestrator.config.model_factory import get_model
from amc_orchestrator.config.settings import Settings


def test_ollama_provider_builds_ollama_model() -> None:
    settings = Settings(
        environment="dev",
        model_provider="ollama",
        ollama_host="http://localhost:11434",
        ollama_model_id="qwen2.5:7b-instruct",
    )

    model = get_model(settings, temperature=0.2)

    assert isinstance(model, OllamaModel)
    assert model.host == "http://localhost:11434"
    assert model.get_config()["model_id"] == "qwen2.5:7b-instruct"
    assert model.get_config()["temperature"] == 0.2


def test_dev_can_opt_into_bedrock_provider() -> None:
    settings = Settings(
        environment="dev",
        model_provider="bedrock",
        bedrock_model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        aws_region="us-west-2",
    )

    model = get_model(settings, temperature=0.15)

    assert isinstance(model, BedrockModel)
    assert model.config["model_id"] == "anthropic.claude-3-5-sonnet-20241022-v2:0"
    assert model.config["temperature"] == 0.15


def test_staging_always_builds_bedrock_model_regardless_of_model_provider() -> None:
    settings = Settings(environment="staging", model_provider="ollama")

    model = get_model(settings, temperature=0.4)

    assert isinstance(model, BedrockModel)
