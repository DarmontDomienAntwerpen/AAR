"""Stage-independent utility call: proofread/tighten a short piece of
facilitator-typed free text (incident description, initial-call notes).
Not part of the analysis pipeline — triggered on demand, result overwrites
the field immediately (same "facilitator is final authority" model as every
other manual edit in aar_service)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class TextCleanupOutput(BaseModel):
    text: str = Field(min_length=1, description="De opgeschoonde tekst, zelfde taal, geen nieuwe feiten.")
