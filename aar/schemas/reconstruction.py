"""Stage 3 (incident reconstruction) LLM output contract.

Deliberately has NO exact-timestamp field. Exact times may only be attached
later, deterministically, by the dispatch-enrichment stage matching a
DispatchRecord — never invented by the LLM (spec §22). `order_hint` expresses
relative narrative order only.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ReconstructedPerspective(BaseModel):
    commander_report_id: int
    perspective_text: str = Field(min_length=1)
    observation_ids: list[int] = Field(default_factory=list)


class ReconstructedEvent(BaseModel):
    title: str = Field(min_length=1)
    order_hint: int = Field(description="Relative order among events in this same output, low=earlier")
    ai_summary: str = Field(min_length=1)
    involved_units: list[str] = Field(default_factory=list)
    involved_commanders: list[str] = Field(default_factory=list)
    observation_ids: list[int] = Field(default_factory=list)
    perspectives: list[ReconstructedPerspective] = Field(default_factory=list)
    approx_time_text: str | None = None


class ReconstructionOutput(BaseModel):
    events: list[ReconstructedEvent] = Field(default_factory=list)
