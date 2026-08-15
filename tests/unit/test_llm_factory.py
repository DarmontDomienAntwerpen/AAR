import pytest

from aar.config.settings import Settings
from aar.llm.factory import get_llm_provider
from aar.llm.mock import MockLLMProvider


def _settings(**overrides) -> Settings:
    base = dict(
        llm_provider="mock",
        anthropic_api_key=None,
        anthropic_model="claude-sonnet-5",
        db_path="/tmp/unused.db",
        log_level="INFO",
        access_password=None,
        session_secret="test-secret",
    )
    base.update(overrides)
    return Settings(**base)


def test_factory_defaults_to_mock():
    provider = get_llm_provider(_settings(llm_provider="mock"))
    assert isinstance(provider, MockLLMProvider)


def test_factory_unknown_provider_falls_back_to_mock():
    provider = get_llm_provider(_settings(llm_provider="something_else"))
    assert isinstance(provider, MockLLMProvider)


def test_factory_anthropic_without_key_raises():
    with pytest.raises(RuntimeError):
        get_llm_provider(_settings(llm_provider="anthropic", anthropic_api_key=None))
