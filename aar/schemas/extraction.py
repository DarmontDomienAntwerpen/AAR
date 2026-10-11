"""Stage 1 (extraction) LLM output contract.

Every extracted item must carry a verbatim `source_passage` — this is the
mechanism that enforces source traceability (spec §31) and stops the model
from asserting things that aren't actually in the report.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from aar.models.enums import ObservationCategory, ObservationType

# Must match aar.schemas.ingestion.COMMANDER_REPORT_SECTION_KEYS exactly —
# the literal form-section key an item came from, independent of whatever
# semantic category the LLM also assigns it. Deliberately separate from
# `category`: a sentence from "Overige opmerkingen" that reads like an
# assessment still needs to display under Overige opmerkingen, not get
# pulled into a different topic box just because of its semantic content
# (spec discussion: "de topics moeten dezelfde zijn als in de form").
SourceSection = Literal["situation", "actions", "went_well", "went_less_well", "other", "difficulties"]


class ExtractedItem(BaseModel):
    content: str = Field(
        min_length=1,
        description=(
            "Normalised/interpreted statement. Kort en telegramstijl (zie kernprincipes) — "
            "dit is wat de facilitator scant, niet het volledige verslag."
        ),
    )
    source_passage: str = Field(
        min_length=1, description="Verbatim excerpt from the report supporting this item"
    )
    source_section: SourceSection = Field(
        description="Welke sectie uit de GEGEVENS dit item kwam (exacte sleutelnaam, bv. 'actions')."
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
