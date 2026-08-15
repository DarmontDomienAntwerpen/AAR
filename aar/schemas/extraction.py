"""Stage 1 (extraction) LLM output contract.

Every extracted item must carry a verbatim `source_passage` — this is the
mechanism that enforces source traceability (spec §31) and stops the model
from asserting things that aren't actually in the report.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from aar.models.enums import ObservationCategory, ObservationType


class ExtractedItem(BaseModel):
    content: str = Field(min_length=1, description="Normalised/interpreted statement")
    source_passage: str = Field(
        min_length=1, description="Verbatim excerpt from the report supporting this item"
    )
    observation_type: ObservationType
    category: ObservationCategory = ObservationCategory.OTHER
    reported_time_text: str | None = Field(
        default=None, description="Approximate time as stated in the narrative, verbatim, if any"
    )

    @field_validator("content", "source_passage")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class ReportExtraction(BaseModel):
    """Structured extraction of a single commander report."""

    commander_report_id: int
    items: list[ExtractedItem] = Field(default_factory=list)
