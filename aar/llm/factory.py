from __future__ import annotations

from aar.config.logging_setup import get_logger
from aar.config.settings import Settings, get_settings
from aar.llm.base import LLMProvider
from aar.llm.mock import MockLLMProvider

logger = get_logger("llm.factory")


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "AAR_LLM_PROVIDER=anthropic maar ANTHROPIC_API_KEY ontbreekt. "
                "Stel de sleutel in via .env of kies AAR_LLM_PROVIDER=mock."
            )
        from aar.llm.provider_anthropic import AnthropicProvider

        return AnthropicProvider(
            api_key=settings.anthropic_api_key, model=settings.anthropic_model
        )
    if settings.llm_provider != "mock":
        logger.warning(
            "Onbekende AAR_LLM_PROVIDER=%r, terugvallen op mock.", settings.llm_provider
        )
    return MockLLMProvider()
