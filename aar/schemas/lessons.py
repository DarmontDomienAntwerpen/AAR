"""Stage 6 (lessons/improvements) LLM output contract."""
from __future__ import annotations

from pydantic import BaseModel, Field


class LessonCandidate(BaseModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    discussion_point_titles: list[str] = Field(default_factory=list)


class ImprovementCandidate(BaseModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    related_lesson_title: str | None = None


class LessonsOutput(BaseModel):
    lessons: list[LessonCandidate] = Field(default_factory=list)
    improvements: list[ImprovementCandidate] = Field(default_factory=list)
