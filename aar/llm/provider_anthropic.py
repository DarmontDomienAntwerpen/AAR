"""Anthropic-backed LLM provider. Uses forced tool-use to get JSON output
that already matches the requested Pydantic schema's JSON Schema.

Requires `ANTHROPIC_API_KEY`. Not imported/instantiated unless
`AAR_LLM_PROVIDER=anthropic` — the rest of the app and the whole ordinary
test suite never need this module or a network connection (spec §12).
"""
from __future__ import annotations

from aar.config.logging_setup import get_logger
from aar.llm.base import LLMProvider

logger = get_logger("llm.anthropic")


class LLMProviderError(Exception):
    """Raised on a provider/network/API-level failure (not a validation failure)."""


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str, max_tokens: int = 4096) -> None:
        import anthropic  # local import: only required for this provider

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def _complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict,
        attempt: int,
        previous_error: str | None,
    ) -> str:
        import json

        import anthropic

        messages = [{"role": "user", "content": user_prompt}]
        if previous_error:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Je vorige antwoord voldeed niet aan het vereiste schema "
                        f"({previous_error}). Geef een nieuw, geldig antwoord."
                    ),
                }
            )

        tool_name = schema.get("title") or "structured_output"
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system_prompt,
                messages=messages,
                tools=[
                    {
                        "name": tool_name,
                        "description": f"Retourneer het resultaat als {tool_name}.",
                        "input_schema": schema,
                    }
                ],
                tool_choice={"type": "tool", "name": tool_name},
            )
        except anthropic.APIError as exc:
            logger.error("Anthropic API error: %s", exc)
            raise LLMProviderError(f"Anthropic API-fout: {exc}") from exc

        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                return json.dumps(block.input)

        raise LLMProviderError("Anthropic-respons bevatte geen tool_use-blok met resultaat.")
