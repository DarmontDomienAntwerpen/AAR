from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aar.db.session import Base
from aar.models.enums import AnalysisRunStatus


class HumanCorrection(Base):
    """A facilitator-supplied correction/context note. Re-fed to the LLM as
    authoritative context on the next analysis run (spec §49)."""

    __tablename__ = "human_corrections"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=False)

    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[int | None] = mapped_column(nullable=True)
    correction_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())

    incident: Mapped["Incident"] = relationship(back_populates="corrections")


class AnalysisRun(Base):
    """Bookkeeping row for one execution of the analysis pipeline."""

    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=False)

    started_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[AnalysisRunStatus] = mapped_column(
        Enum(AnalysisRunStatus, native_enum=False, length=16), default=AnalysisRunStatus.RUNNING
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stage_reached: Mapped[str] = mapped_column(Text, default="")
    correction_ids: Mapped[list] = mapped_column(JSON, default=list)

    incident: Mapped["Incident"] = relationship(back_populates="analysis_runs")
