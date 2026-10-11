"""Provider-agnostic LLM abstraction.

Every call in the analysis pipeline goes through `LLMProvider.generate_structured`,
never a provider SDK directly — provider-specific code stays isolated to the
`_complete()` implementations in this package (spec §12). Output is always
validated against a Pydantic model before it reaches the rest of the app; an
LLM is never trusted blindly (spec §54).
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from aar.config.logging_setup import get_logger

logger = get_logger("llm.base")


def _repair_double_encoded_json(value):
    """Anthropic's forced tool-use occasionally serialises a nested
    list/object field as a JSON *string* instead of the actual list/object
    (seen on ReconstructionOutput.events under load) — a provider quirk,
    not a real schema mismatch. Recursively un-stringify any string value
    that itself parses as JSON, so a transient encoding glitch doesn't
    burn a retry (or fail the whole call) over content that was actually
    present and correct."""
    if isinstance(value, dict):
        return {k: _repair_double_encoded_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_repair_double_encoded_json(v) for v in value]
    if isinstance(value, str) and value[:1] in "[{":
        try:
            return _repair_double_encoded_json(json.loads(value))
        except json.JSONDecodeError:
            return value
    return value

TModel = TypeVar("TModel", bound=BaseModel)


class LLMOutputValidationError(Exception):
    """Raised when the LLM could not produce output matching the requested
    schema even after retries. Callers must handle this — never fall back to
    inventing a result (spec §58: fail usefully, don't silently discard)."""


class LLMProvider(ABC):
    """Abstract base for all LLM backends."""

    max_retries: int = 1

    def generate_structured(
        self, *, system_prompt: str, user_prompt: str, response_model: type[TModel]
    ) -> TModel:
        schema = response_model.model_json_schema()
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            raw = self._complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
                attempt=attempt,
                previous_error=str(last_error) if last_error else None,
            )
            try:
                data = _repair_double_encoded_json(json.loads(raw))
                return response_model.model_validate(data)
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                logger.warning(
                    "LLM output failed validation for %s on attempt %d/%d: %s",
                    response_model.__name__,
                    attempt + 1,
                    self.max_retries + 1,
                    exc,
                )

        raise LLMOutputValidationError(
            f"LLM output for {response_model.__name__} failed schema validation "
            f"after {self.max_retries + 1} attempt(s): {last_error}"
        )

    @abstractmethod
    def _complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict,
        attempt: int,
        previous_error: str | None,
    ) -> str:
        """Return raw text expected to be a JSON object matching `schema`.
        `previous_error` is set on retry attempts so a real provider can be
        told what went wrong last time."""
        raise NotImplementedError
