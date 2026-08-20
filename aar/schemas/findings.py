"""Stage 5 (analysis/findings) LLM output contract."""
from __future__ import annotations

from pydantic import BaseModel, Field

from aar.models.enums import ConfidenceState, DiscussionOrigin


class DiscussionPointCandidate(BaseModel):
    title: str = Field(min_length=1, description="Kort en telegramstijl, geen volzin.")
    description: str = Field(min_length=1)
    origin_category: DiscussionOrigin = DiscussionOrigin.OTHER
    confidence_state: ConfidenceState = ConfidenceState.ONVOLDOENDE_BEWIJS
    observation_ids: list[int] = Field(default_factory=list)
    event_title: str | None = None


class PositiveFindingCandidate(BaseModel):
    title: str = Field(min_length=1, description="Kort en telegramstijl, geen volzin.")
    description: str = Field(min_length=1)
    observation_ids: list[int] = Field(default_factory=list)
    event_title: str | None = None


class AIObservationCandidate(BaseModel):
    content: str = Field(min_length=1)
    evidence_observation_ids: list[int] = Field(default_factory=list)


class FindingsOutput(BaseModel):
    discussion_points: list[DiscussionPointCandidate] = Field(default_factory=list)
    positive_findings: list[PositiveFindingCandidate] = Field(default_factory=list)
    ai_observations: list[AIObservationCandidate] = Field(default_factory=list)
