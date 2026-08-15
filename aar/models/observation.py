from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aar.db.session import Base
from aar.models.enums import CreatedBy, ObservationCategory, ObservationType


class Observation(Base):
    """The atomic unit of evidence: one interpreted statement plus its source
    passage, tagged with a semantic type (spec §24-30). This is what every
    higher-level finding (event, discussion point, lesson, ...) links back to
    for source traceability (spec §31)."""

    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=False)
    commander_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("commander_reports.id"), nullable=True
    )

    observation_type: Mapped[ObservationType] = mapped_column(
        Enum(ObservationType, native_enum=False, length=32), nullable=False
    )
    category: Mapped[ObservationCategory] = mapped_column(
        Enum(ObservationCategory, native_enum=False, length=32),
        default=ObservationCategory.OTHER,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_passage: Mapped[str | None] = mapped_column(Text, nullable=True)
    attributed_to: Mapped[str | None] = mapped_column(Text, nullable=True)

    reported_time_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispatch_timestamp: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    # For AI_OBSERVATION rows that span multiple sources: list of
    # {"observation_id": int} or {"commander_report_id": int} refs.
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)

    created_by: Mapped[CreatedBy] = mapped_column(
        Enum(CreatedBy, native_enum=False, length=16), default=CreatedBy.AI
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())

    incident: Mapped["Incident"] = relationship(back_populates="observations")
    commander_report: Mapped["CommanderReport | None"] = relationship(
        back_populates="observations"
    )
