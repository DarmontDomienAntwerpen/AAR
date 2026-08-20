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
from aar.ingestion.commander_sheet import CommanderSheetParseError, parse_commander_report_sheet
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


def ingest_commander_report_sheet(
    session: Session, incident: Incident, file_bytes: bytes, filename: str
) -> list[SourceDocument]:
    """Store, parse, and persist a Google-Forms responses sheet: one row per
    commander, each becoming its own CommanderReport.

    `CommanderReport.source_document_id` is 1:1 with a SourceDocument, so
    each row gets its own SourceDocument row (all pointing at the same
    stored file) rather than relaxing that constraint. Each row's content
    hash is derived from the file hash *and* its row index, so re-uploading
    the identical sheet is still correctly detected as a duplicate — checked
    once, up front, via row 0's hash, before anything is written.
    """
    base_hash = hashlib.sha256(file_bytes).hexdigest()
    first_row_hash = hashlib.sha256(f"{base_hash}:0".encode()).hexdigest()
    existing = session.execute(
        select(SourceDocument).where(
            SourceDocument.incident_id == incident.id,
            SourceDocument.content_hash == first_row_hash,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateSourceError(f"Dit bestand ('{filename}') werd al eerder geüpload.")

    stored_path = _uploads_dir(incident.id) / f"{uuid.uuid4().hex}_{filename}"
    stored_path.write_bytes(file_bytes)

    try:
        parsed = parse_commander_report_sheet(stored_path, source_filename=filename)
    except CommanderSheetParseError as exc:
        doc = SourceDocument(
            incident_id=incident.id,
            doc_type=SourceDocumentType.COMMANDER_REPORT,
            original_filename=filename,
            stored_path=str(stored_path),
            content_hash=first_row_hash,
            parse_status=ParseStatus.ERROR,
            parse_error=str(exc),
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)
        logger.warning("Failed to parse commander report sheet %s: %s", filename, exc)
        return [doc]

    shared_note = "; ".join(parsed.warnings) if parsed.warnings else None
    docs: list[SourceDocument] = []
    for i, raw in enumerate(parsed.reports):
        doc = SourceDocument(
            incident_id=incident.id,
            doc_type=SourceDocumentType.COMMANDER_REPORT,
            original_filename=raw.source_filename,
            stored_path=str(stored_path),
            content_hash=hashlib.sha256(f"{base_hash}:{i}".encode()).hexdigest(),
            parse_status=ParseStatus.PARSED,
            parse_error=shared_note,
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)

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
        session.commit()
        docs.append(doc)

    logger.info(
        "Ingested commander report sheet %s for incident %s: %d report(s), %d warning(s).",
        filename,
        incident.id,
        len(docs),
        len(parsed.warnings),
    )
    return docs
