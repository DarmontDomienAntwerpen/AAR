import pytest
from pydantic import BaseModel

from aar.llm.base import LLMOutputValidationError, LLMProvider


class _Greeting(BaseModel):
    message: str


class _FlakyProvider(LLMProvider):
    """Returns invalid JSON once, then valid JSON."""

    def __init__(self):
        self.calls = 0

    def _complete(self, *, system_prompt, user_prompt, schema, attempt, previous_error):
        self.calls += 1
        if attempt == 0:
            return "not json"
        return '{"message": "hallo"}'


class _AlwaysBadProvider(LLMProvider):
    def _complete(self, *, system_prompt, user_prompt, schema, attempt, previous_error):
        return "still not json"


def test_provider_retries_and_recovers():
    provider = _FlakyProvider()
    result = provider.generate_structured(
        system_prompt="sys", user_prompt="usr", response_model=_Greeting
    )
    assert result.message == "hallo"
    assert provider.calls == 2


def test_provider_raises_after_exhausting_retries():
    provider = _AlwaysBadProvider()
    with pytest.raises(LLMOutputValidationError):
        provider.generate_structured(system_prompt="sys", user_prompt="usr", response_model=_Greeting)
