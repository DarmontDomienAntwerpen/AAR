from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aar.db.session import Base


class IncidentEvent(Base):
    """A candidate incident moment (arrival, escalation, victim found, ...).
    Chronology is a relative `order_index` maintained by the app; `exact_time`
    is only ever set when a dispatch record reliably supports it (spec §21-22).
    """

    __tablename__ = "incident_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    exact_time: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    exact_time_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    approx_time_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    ai_summary: Mapped[str] = mapped_column(Text, default="")
    involved_units: Mapped[list] = mapped_column(JSON, default=list)
    involved_commanders: Mapped[list] = mapped_column(JSON, default=list)
    observation_ids: Mapped[list] = mapped_column(JSON, default=list)

    is_human_added: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    incident: Mapped["Incident"] = relationship(back_populates="events")
    perspectives: Mapped[list["EventPerspective"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class EventPerspective(Base):
    """One commander's account of a specific incident moment."""

    __tablename__ = "event_perspectives"
    __table_args__ = (UniqueConstraint("event_id", "commander_report_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("incident_events.id"), nullable=False)
    commander_report_id: Mapped[int] = mapped_column(
        ForeignKey("commander_reports.id"), nullable=False
    )
    commander_display_name: Mapped[str] = mapped_column(Text, default="")
    perspective_text: Mapped[str] = mapped_column(Text, default="")
    observation_ids: Mapped[list] = mapped_column(JSON, default=list)

    event: Mapped["IncidentEvent"] = relationship(back_populates="perspectives")
    commander_report: Mapped["CommanderReport"] = relationship()
