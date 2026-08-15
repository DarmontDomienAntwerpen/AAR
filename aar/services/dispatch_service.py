"""Ties dispatch Excel parsing to persistence."""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from aar.config.logging_setup import get_logger
from aar.config.settings import get_settings
from aar.ingestion.dispatch_excel import DispatchExcelParseError, parse_dispatch_excel
from aar.models import DispatchRecord, Incident, ParseStatus, SourceDocument, SourceDocumentType
from aar.services.errors import DuplicateSourceError

logger = get_logger("services.dispatch_service")


def _uploads_dir(incident_id: int) -> Path:
    settings = get_settings()
    directory = settings.project_root / "data" / "uploads" / str(incident_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def ingest_dispatch_excel(
    session: Session, incident: Incident, file_bytes: bytes, filename: str
) -> SourceDocument:
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
        doc_type=SourceDocumentType.DISPATCH_EXCEL,
        original_filename=filename,
        stored_path=str(stored_path),
        content_hash=content_hash,
        parse_status=ParseStatus.PENDING,
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)

    try:
        sheet = parse_dispatch_excel(stored_path, source_filename=filename)
    except DispatchExcelParseError as exc:
        doc.parse_status = ParseStatus.ERROR
        doc.parse_error = str(exc)
        session.commit()
        logger.warning("Failed to parse dispatch sheet %s: %s", filename, exc)
        return doc

    for rec in sheet.records:
        session.add(
            DispatchRecord(
                incident_id=incident.id,
                source_document_id=doc.id,
                row_index=rec.row_index,
                timestamp=rec.timestamp,
                event_description=rec.event_description,
                unit=rec.unit,
                raw_row=rec.raw_row,
                is_valid=rec.is_valid,
                validation_error=rec.validation_error,
            )
        )

    doc.parse_status = ParseStatus.PARSED
    doc.parse_error = "; ".join(sheet.warnings) if sheet.warnings else None
    session.commit()
    session.refresh(doc)
    logger.info(
        "Ingested dispatch sheet %s for incident %s (%d record(s)).",
        filename,
        incident.id,
        len(sheet.records),
    )
    return doc
