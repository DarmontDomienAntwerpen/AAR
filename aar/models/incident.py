from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, DateTime, Enum, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aar.db.session import Base
from aar.models.enums import IncidentStatus, IncidentType


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    location: Mapped[str] = mapped_column(Text, nullable=False)
    incident_type: Mapped[IncidentType] = mapped_column(
        Enum(IncidentType, native_enum=False, length=64), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, native_enum=False, length=32),
        default=IncidentStatus.DRAFT,
        nullable=False,
    )
    situation_summary: Mapped[str] = mapped_column(Text, default="")
    ai_situation_narrative: Mapped[str | None] = mapped_column(Text, default=None, nullable=True)
    # Free-text notes the facilitator types in with what was known from the
    # initial dispatch call — always human-authored, never AI-generated or
    # touched by (re-)analysis.
    initial_call_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    source_documents: Mapped[list["SourceDocument"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    commander_reports: Mapped[list["CommanderReport"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    dispatch_records: Mapped[list["DispatchRecord"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    observations: Mapped[list["Observation"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    events: Mapped[list["IncidentEvent"]] = relationship(
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="IncidentEvent.order_index",
    )
    discussion_points: Mapped[list["DiscussionPoint"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    positive_findings: Mapped[list["PositiveFinding"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    lessons: Mapped[list["Lesson"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    improvements: Mapped[list["Improvement"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    corrections: Mapped[list["HumanCorrection"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Incident id={self.id} date={self.date} location={self.location!r}>"
