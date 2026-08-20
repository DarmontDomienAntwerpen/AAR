"""Stage 6 (lessons/improvements) LLM output contract."""
from __future__ import annotations

from pydantic import BaseModel, Field


class LessonCandidate(BaseModel):
    title: str = Field(min_length=1, description="Kort en telegramstijl, geen volzin.")
    description: str = Field(
        min_length=1,
        description="1-2 zinnen ECHTE synthese van het thema — nooit losse voorbeelden achter elkaar geplakt.",
    )
    discussion_point_titles: list[str] = Field(default_factory=list)


class ImprovementCandidate(BaseModel):
    title: str = Field(min_length=1, description="Kort en telegramstijl, geen volzin.")
    description: str = Field(min_length=1, description="1-2 zinnen, concreet en kort.")
    related_lesson_title: str | None = None


class LessonsOutput(BaseModel):
    lessons: list[LessonCandidate] = Field(default_factory=list)
    improvements: list[ImprovementCandidate] = Field(default_factory=list)
