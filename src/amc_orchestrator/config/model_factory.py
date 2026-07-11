"""Model provider factory, driven by `Settings.effective_model_provider`.

This is the *only* module that imports a concrete Strands model class.
Agents never import `OllamaModel`/`BedrockModel` directly - they call
`get_model(settings, temperature=...)` - so switching provider (DEV's
Ollama/Bedrock toggle, or promoting to STAGING/PROD) is a config change,
not a code change.
"""

from __future__ import annotations

from strands.models import Model

from amc_orchestrator.config.settings import Settings


def get_model(settings: Settings, *, temperature: float) -> Model:
    """Return the model provider appropriate for `settings.effective_model_provider`."""
    if settings.effective_model_provider == "ollama":
        from strands.models.ollama import OllamaModel

        return OllamaModel(
            host=settings.ollama_host,
            model_id=settings.ollama_model_id,
            temperature=temperature,
        )

    from strands.models import BedrockModel

    return BedrockModel(
        model_id=settings.bedrock_model_id,
        region_name=settings.aws_region,
        temperature=temperature,
    )
