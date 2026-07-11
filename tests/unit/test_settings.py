"""Unit tests for `Settings.effective_model_provider`.

DEV can opt into either provider; STAGING/PROD always resolve to Bedrock
regardless of `model_provider` - a compliance/production requirement, not a
developer preference. See config/settings.py and config/model_factory.py.
"""

from __future__ import annotations

from amc_orchestrator.config.settings import Settings


def test_dev_defaults_to_ollama() -> None:
    settings = Settings(environment="dev")
    assert settings.effective_model_provider == "ollama"


def test_dev_respects_explicit_ollama() -> None:
    settings = Settings(environment="dev", model_provider="ollama")
    assert settings.effective_model_provider == "ollama"


def test_dev_can_opt_into_bedrock() -> None:
    settings = Settings(environment="dev", model_provider="bedrock")
    assert settings.effective_model_provider == "bedrock"


def test_staging_forces_bedrock_even_if_ollama_requested() -> None:
    settings = Settings(environment="staging", model_provider="ollama")
    assert settings.effective_model_provider == "bedrock"


def test_prod_forces_bedrock_even_if_ollama_requested() -> None:
    settings = Settings(environment="prod", model_provider="ollama")
    assert settings.effective_model_provider == "bedrock"


# --- effective_data_backend ---------------------------------------------
# Same shape as effective_model_provider above, for the same reason: DEV can
# opt into the AWS-backed stores (DynamoDB/Bedrock Knowledge Base) per-run;
# STAGING/PROD always use them regardless of `data_backend`.


def test_dev_defaults_to_local_data_backend() -> None:
    settings = Settings(environment="dev")
    assert settings.effective_data_backend == "local"


def test_dev_can_opt_into_aws_data_backend() -> None:
    settings = Settings(environment="dev", data_backend="aws")
    assert settings.effective_data_backend == "aws"


def test_staging_forces_aws_data_backend_even_if_local_requested() -> None:
    settings = Settings(environment="staging", data_backend="local")
    assert settings.effective_data_backend == "aws"


def test_prod_forces_aws_data_backend_even_if_local_requested() -> None:
    settings = Settings(environment="prod", data_backend="local")
    assert settings.effective_data_backend == "aws"
