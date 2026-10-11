"""Reference photos/plans attached to an incident. Deliberately not parsed
or fed to the AI pipeline — purely visual reference material the facilitator
can caption and optionally pin to a specific incident moment (spec has no
requirement for this; it's an explicit, scoped addition on top of it)."""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from aar.config.logging_setup import get_logger
from aar.config.settings import get_settings
from aar.models import CommanderReport, Incident, IncidentEvent, ParseStatus, SourceDocument, SourceDocumentType
from aar.services.errors import DuplicateSourceError

logger = get_logger("services.media_service")

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}


class UnsupportedMediaTypeError(Exception):
    pass


def _uploads_dir(incident_id: int) -> Path:
    settings = get_settings()
    directory = settings.project_root / "data" / "uploads" / str(incident_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def ingest_photo(
    session: Session, incident: Incident, file_bytes: bytes, filename: str
) -> SourceDocument:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedMediaTypeError(
            f"Bestandstype '{extension}' wordt niet ondersteund. Toegestaan: "
            + ", ".join(sorted(ALLOWED_EXTENSIONS))
        )

    content_hash = hashlib.sha256(file_bytes).hexdigest()
    existing = session.execute(
        select(SourceDocument).where(
            SourceDocument.incident_id == incident.id,
            SourceDocument.content_hash == content_hash,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateSourceError(
            f"Dit bestand ('{filename}') werd al eerder geüpload als '{existing.original_filename}'."
        )

    stored_path = _uploads_dir(incident.id) / f"{uuid.uuid4().hex}_{filename}"
    stored_path.write_bytes(file_bytes)

    doc = SourceDocument(
        incident_id=incident.id,
        doc_type=SourceDocumentType.PHOTO_OR_PLAN,
        original_filename=filename,
        stored_path=str(stored_path),
        content_hash=content_hash,
        parse_status=ParseStatus.PARSED,
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    logger.info("Ingested photo/plan %s for incident %s.", filename, incident.id)
    return doc


def list_photos(session: Session, incident: Incident) -> list[SourceDocument]:
    return (
        session.query(SourceDocument)
        .filter_by(incident_id=incident.id, doc_type=SourceDocumentType.PHOTO_OR_PLAN)
        .order_by(SourceDocument.uploaded_at)
        .all()
    )


def set_caption(session: Session, doc: SourceDocument, caption: str) -> SourceDocument:
    doc.caption = caption.strip()
    session.commit()
    session.refresh(doc)
    return doc


def link_to_event(session: Session, doc: SourceDocument, event: IncidentEvent | None) -> SourceDocument:
    doc.event_id = event.id if event is not None else None
    session.commit()
    session.refresh(doc)
    return doc


def link_to_commander_report(
    session: Session, doc: SourceDocument, report: CommanderReport | None
) -> SourceDocument:
    """Pins a photo/plan to a specific commander's own account (shown in
    their "Waarnemingen & acties" overlay) — independent of event_id, see
    SourceDocument.linked_commander_report_id."""
    doc.linked_commander_report_id = report.id if report is not None else None
    session.commit()
    session.refresh(doc)
    return doc


def delete_photo(session: Session, doc: SourceDocument) -> None:
    path = Path(doc.stored_path)
    session.delete(doc)
    session.commit()
    if path.exists():
        path.unlink()
