"""Schemas produced by deterministic ingestion (DOCX/XLSX parsing).

These are NOT LLM output — they are the validated result of ordinary Python
parsing (spec §54: "Use Pydantic aggressively at system boundaries").
"""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from aar.models.enums import ObjectiveAchieved

# Section keys used both by the DOCX template generator and the parser.
# Keep this list and the template headings in `templates/` in sync.
COMMANDER_REPORT_SECTION_KEYS: list[str] = [
    "observations",
    "information_position",
    "assessment",
    "decision",
    "objective",
    "narrative",
    "result",
    "went_well",
    "went_less_well",
    "why",
    "doubts_assumptions",
    "other",
]


class CommanderIdentity(BaseModel):
    callsign: str = Field(default="")
    unit_name: str = Field(default="")
    rank: str = Field(default="")
    surname: str = Field(default="")

    @property
    def is_complete(self) -> bool:
        return bool(self.callsign and self.surname)

    @property
    def display_name(self) -> str:
        head = f"{self.callsign} ({self.unit_name})" if self.unit_name else self.callsign
        tail = f"{self.rank} {self.surname}".strip()
        if head and tail:
            return f"{head} — {tail}"
        return head or tail


class CommanderReportRaw(BaseModel):
    """Result of deterministically parsing one commander DOCX."""

    identity: CommanderIdentity
    sections: dict[str, str] = Field(default_factory=dict)
    objective_achieved: ObjectiveAchieved | None = None
    objective_achieved_explanation: str = ""
    source_filename: str


class DispatchRecordRaw(BaseModel):
    """One row extracted from the dispatch spreadsheet."""

    row_index: int
    timestamp: dt.datetime | None = None
    event_description: str = ""
    unit: str | None = None
    raw_row: dict = Field(default_factory=dict)
    is_valid: bool = True
    validation_error: str | None = None


class DispatchSheetRaw(BaseModel):
    records: list[DispatchRecordRaw] = Field(default_factory=list)
    source_filename: str
    sheet_name: str
    warnings: list[str] = Field(default_factory=list)
