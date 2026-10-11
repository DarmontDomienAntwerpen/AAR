"""Stage 7 (situation narrative) LLM output contract.

Distinct from `default_situation_summary` (deterministic, per-event,
per-commander lines — used as the pre-Stage-7 fallback and by the mock
provider): this is genuine cross-report synthesis, only meaningful with a
real LLM (spec §57 discussion — "let the LLM sketch the situation from all
the boxes together")."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SituationNarrativeOutput(BaseModel):
    narrative: str = Field(
        min_length=1,
        description=(
            "Doorlopende tekst (enkele alinea's), geen opsomming per bevelvoerder. "
            "Waar bronnen elkaar aanvullen: samenvoegen tot één lopend verhaal. "
            "Waar bronnen elkaar tegenspreken: het verschil benoemen, geen kant kiezen."
        ),
    )
