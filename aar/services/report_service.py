"""Ties DOCX parsing to persistence: stores the original file, detects
duplicate uploads, and creates SourceDocument + CommanderReport rows."""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from aar.config.logging_setup import get_logger
from aar.config.settings import get_settings
from aar.ingestion.commander_docx import CommanderReportParseError, parse_commander_report
from aar.models import CommanderReport, Incident, ParseStatus, SourceDocument, SourceDocumentType
from aar.services.errors import DuplicateSourceError

logger = get_logger("services.report_service")


def _uploads_dir(incident_id: int) -> Path:
    settings = get_settings()
    directory = settings.project_root / "data" / "uploads" / str(incident_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def ingest_commander_report(
    session: Session, incident: Incident, file_bytes: bytes, filename: str
) -> SourceDocument:
    """Store, parse, and persist one commander DOCX report.

    Always returns a SourceDocument row (even on a parse error, so the
    facilitator can see what was uploaded and why it failed) — except for an
    exact duplicate, which raises instead of creating a second copy.
    """
    content_hash = hashlib.sha256(file_bytes).hexdigest()

    existing = session.execute(
        select(SourceDocument).where(
            SourceDocument.incident_id == incident.id,
            SourceDocument.content_hash == content_hash,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateSourceError(
            f"Dit bestand ('{filename}') werd al eerder geüpload als "
            f"'{existing.original_filename}'."
        )

    stored_path = _uploads_dir(incident.id) / f"{uuid.uuid4().hex}_{filename}"
    stored_path.write_bytes(file_bytes)

    doc = SourceDocument(
        incident_id=incident.id,
        doc_type=SourceDocumentType.COMMANDER_REPORT,
        original_filename=filename,
        stored_path=str(stored_path),
        content_hash=content_hash,
        parse_status=ParseStatus.PENDING,
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)

    try:
        raw, warnings = parse_commander_report(stored_path, source_filename=filename)
    except CommanderReportParseError as exc:
        doc.parse_status = ParseStatus.ERROR
        doc.parse_error = str(exc)
        session.commit()
        logger.warning("Failed to parse commander report %s: %s", filename, exc)
        return doc

    report = CommanderReport(
        incident_id=incident.id,
        source_document_id=doc.id,
        callsign=raw.identity.callsign,
        unit_name=raw.identity.unit_name,
        rank=raw.identity.rank,
        surname=raw.identity.surname,
        raw_sections=raw.sections,
        objective_achieved=raw.objective_achieved,
        objective_achieved_explanation=raw.objective_achieved_explanation,
        extraction_status=ParseStatus.PENDING,
    )
    session.add(report)
    doc.parse_status = ParseStatus.PARSED
    doc.parse_error = "; ".join(warnings) if warnings else None
    session.commit()
    session.refresh(doc)
    logger.info(
        "Ingested commander report %s for incident %s (%d warning(s)).",
        filename,
        incident.id,
        len(warnings),
    )
    return doc
