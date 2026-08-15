from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aar.db.session import Base
from aar.models.enums import ObjectiveAchieved, ParseStatus, SourceDocumentType


class SourceDocument(Base):
    """A single uploaded original file (commander DOCX, dispatch XLSX, or a
    reference photo/plan). `caption` and `event_id` are only meaningful for
    PHOTO_OR_PLAN documents — reference material the facilitator can caption
    and optionally pin to a specific incident moment."""

    __tablename__ = "source_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=False)
    doc_type: Mapped[SourceDocumentType] = mapped_column(
        Enum(SourceDocumentType, native_enum=False, length=32), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    uploaded_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    parse_status: Mapped[ParseStatus] = mapped_column(
        Enum(ParseStatus, native_enum=False, length=16), default=ParseStatus.PENDING
    )
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    caption: Mapped[str] = mapped_column(Text, default="")
    event_id: Mapped[int | None] = mapped_column(ForeignKey("incident_events.id"), nullable=True)

    incident: Mapped["Incident"] = relationship(back_populates="source_documents")
    commander_report: Mapped["CommanderReport | None"] = relationship(
        back_populates="source_document", uselist=False, cascade="all, delete-orphan"
    )
    dispatch_records: Mapped[list["DispatchRecord"]] = relationship(
        back_populates="source_document", cascade="all, delete-orphan"
    )
    event: Mapped["IncidentEvent | None"] = relationship()


class CommanderReport(Base):
    """Parsed content of one commander's DOCX report. 1:1 with a SourceDocument."""

    __tablename__ = "commander_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=False)
    source_document_id: Mapped[int] = mapped_column(
        ForeignKey("source_documents.id"), nullable=False, unique=True
    )

    callsign: Mapped[str] = mapped_column(Text, default="")
    unit_name: Mapped[str] = mapped_column(Text, default="")
    rank: Mapped[str] = mapped_column(Text, default="")
    surname: Mapped[str] = mapped_column(Text, default="")

    # Raw section text keyed by section id (spec §16 A-N), original wording preserved.
    raw_sections: Mapped[dict] = mapped_column(JSON, default=dict)

    objective_achieved: Mapped[ObjectiveAchieved | None] = mapped_column(
        Enum(ObjectiveAchieved, native_enum=False, length=32), nullable=True
    )
    objective_achieved_explanation: Mapped[str] = mapped_column(Text, default="")

    extraction_status: Mapped[ParseStatus] = mapped_column(
        Enum(ParseStatus, native_enum=False, length=16), default=ParseStatus.PENDING
    )
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    incident: Mapped["Incident"] = relationship(back_populates="commander_reports")
    source_document: Mapped["SourceDocument"] = relationship(back_populates="commander_report")
    observations: Mapped[list["Observation"]] = relationship(back_populates="commander_report")

    @property
    def display_name(self) -> str:
        """e.g. 'P12 (1ste Hulpcentrum) — Adjudant Janssens'."""
        callsign = self.callsign.strip()
        unit = self.unit_name.strip()
        rank = self.rank.strip()
        surname = self.surname.strip()
        head = f"{callsign} ({unit})" if unit else callsign
        tail = f"{rank} {surname}".strip()
        if head and tail:
            return f"{head} — {tail}"
        return head or tail or f"Commandant #{self.id}"


class DispatchRecord(Base):
    """One structured row extracted from the dispatch/control-room spreadsheet."""

    __tablename__ = "dispatch_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=False)
    source_document_id: Mapped[int] = mapped_column(
        ForeignKey("source_documents.id"), nullable=False
    )
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    event_description: Mapped[str] = mapped_column(Text, default="")
    unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_row: Mapped[dict] = mapped_column(JSON, default=dict)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    incident: Mapped["Incident"] = relationship(back_populates="dispatch_records")
    source_document: Mapped["SourceDocument"] = relationship(back_populates="dispatch_records")
