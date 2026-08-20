from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aar.db.session import Base
from aar.models.enums import ConfidenceState, DiscussionOrigin


class DiscussionPoint(Base):
    """A candidate topic for the group AAR discussion (spec §41)."""

    __tablename__ = "discussion_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=False)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("incident_events.id"), nullable=True)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    origin_category: Mapped[DiscussionOrigin] = mapped_column(
        Enum(DiscussionOrigin, native_enum=False, length=32), default=DiscussionOrigin.OTHER
    )
    confidence_state: Mapped[ConfidenceState] = mapped_column(
        Enum(ConfidenceState, native_enum=False, length=32),
        default=ConfidenceState.ONVOLDOENDE_BEWIJS,
    )
    observation_ids: Mapped[list] = mapped_column(JSON, default=list)
    is_human_added: Mapped[bool] = mapped_column(Boolean, default=False)
    discussed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())

    incident: Mapped["Incident"] = relationship(back_populates="discussion_points")
    event: Mapped["IncidentEvent | None"] = relationship()


class PositiveFinding(Base):
    """A candidate positive/effective-practice finding (spec §40)."""

    __tablename__ = "positive_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=False)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("incident_events.id"), nullable=True)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    observation_ids: Mapped[list] = mapped_column(JSON, default=list)
    is_human_added: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())

    incident: Mapped["Incident"] = relationship(back_populates="positive_findings")
    event: Mapped["IncidentEvent | None"] = relationship()


class Lesson(Base):
    """A candidate lesson learned (spec §42) — an AI proposal the facilitator
    can accept, edit, or delete."""

    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    observation_ids: Mapped[list] = mapped_column(JSON, default=list)
    discussion_point_ids: Mapped[list] = mapped_column(JSON, default=list)
    is_human_added: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())

    incident: Mapped["Incident"] = relationship(back_populates="lessons")


class Improvement(Base):
    """A candidate improvement proposal (spec §43) — no owner/deadline/status,
    per the explicit no-action-tracking rule (spec §44)."""

    __tablename__ = "improvements"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    related_lesson_id: Mapped[int | None] = mapped_column(ForeignKey("lessons.id"), nullable=True)
    observation_ids: Mapped[list] = mapped_column(JSON, default=list)
    is_human_added: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())

    incident: Mapped["Incident"] = relationship(back_populates="improvements")
    related_lesson: Mapped["Lesson | None"] = relationship()
