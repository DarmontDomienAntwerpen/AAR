from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from aar.models import CommanderReport, IncidentEvent, SourceDocument, SourceDocumentType
from aar.services import media_service
from aar.services.errors import DuplicateSourceError
from aar.web.deps import get_db, writable_incident_or_404
from aar.web.flash import redirect_with_flash

router = APIRouter()


def _photo_or_404(session: Session, incident_id: int, doc_id: int) -> SourceDocument:
    doc = session.get(SourceDocument, doc_id)
    if doc is None or doc.incident_id != incident_id:
        raise HTTPException(status_code=404, detail="Bestand niet gevonden")
    return doc


def _photo_only_or_404(session: Session, incident_id: int, doc_id: int) -> SourceDocument:
    """Like `_photo_or_404`, but rejects non-PHOTO_OR_PLAN documents (e.g. a
    commander report's own source file) — caption/link/delete only ever make
    sense for reference photos/plans."""
    doc = _photo_or_404(session, incident_id, doc_id)
    if doc.doc_type != SourceDocumentType.PHOTO_OR_PLAN:
        raise HTTPException(status_code=404, detail="Bestand niet gevonden")
    return doc


def _safe_redirect(incident_id: int, redirect_to: str, fallback: str) -> str:
    """A form can only send the facilitator back to a page within this same
    incident — never off-site — so any submitted `redirect_to` is checked
    against that prefix before use; otherwise `fallback` (e.g. Bronnen)."""
    safe_prefix = f"/incidents/{incident_id}/"
    return redirect_to if redirect_to.startswith(safe_prefix) else fallback


@router.post("/incidents/{incident_id}/sources/photos")
async def upload_photos(
    incident_id: int,
    files: list[UploadFile] = File(...),
    redirect_to: str = Form(""),
    commander_report_id: str = Form(""),
    session: Session = Depends(get_db),
):
    incident = writable_incident_or_404(session, incident_id)
    report = None
    if commander_report_id:
        report = session.get(CommanderReport, int(commander_report_id))
        if report is None or report.incident_id != incident_id:
            report = None

    messages = []
    for f in files:
        content = await f.read()
        try:
            doc = media_service.ingest_photo(session, incident, content, f.filename)
            if report is not None:
                media_service.link_to_commander_report(session, doc, report)
        except (DuplicateSourceError, media_service.UnsupportedMediaTypeError) as exc:
            messages.append(str(exc))

    flash = "; ".join(messages) if messages else "Foto's/plannen toegevoegd."
    flash_type = "warning" if messages else "success"
    target = _safe_redirect(incident_id, redirect_to, f"/incidents/{incident_id}/sources")
    return redirect_with_flash(target, flash, flash_type)


@router.get("/incidents/{incident_id}/media/{doc_id}")
def view_media(incident_id: int, doc_id: int, session: Session = Depends(get_db)):
    doc = _photo_or_404(session, incident_id, doc_id)
    media_type = mimetypes.guess_type(doc.original_filename)[0] or "application/octet-stream"
    # SQLite reuses a deleted row's id for the next insert when that row
    # held the table's current highest id (its default rowid-assignment
    # rule) — so a freshly-uploaded photo can land on the same doc_id an
    # earlier, now-deleted photo had. Without this header the browser can
    # serve that old photo straight from its own cache for this URL,
    # never even asking the server, showing the wrong image after upload.
    # no-cache forces revalidation on every request; ETag/Last-Modified
    # (set by FileResponse from the actual file being served) then
    # correctly reveal that the content changed.
    return FileResponse(doc.stored_path, media_type=media_type, headers={"Cache-Control": "no-cache"})


@router.post("/incidents/{incident_id}/media/{doc_id}/caption")
def update_caption(
    incident_id: int, doc_id: int, caption: str = Form(""), redirect_to: str = Form(""), session: Session = Depends(get_db)
):
    writable_incident_or_404(session, incident_id)
    doc = _photo_only_or_404(session, incident_id, doc_id)
    media_service.set_caption(session, doc, caption)
    target = _safe_redirect(incident_id, redirect_to, f"/incidents/{incident_id}/sources")
    return redirect_with_flash(target, "Bijschrift opgeslagen.")


@router.post("/incidents/{incident_id}/media/link")
def link_photo(
    incident_id: int,
    photo_id: int = Form(...),
    event_id: str = Form(""),
    redirect_to: str = Form(""),
    session: Session = Depends(get_db),
):
    writable_incident_or_404(session, incident_id)
    doc = _photo_only_or_404(session, incident_id, photo_id)
    event = None
    if event_id:
        event = session.get(IncidentEvent, int(event_id))
        if event is None or event.incident_id != incident_id:
            event = None
    media_service.link_to_event(session, doc, event)
    target = _safe_redirect(incident_id, redirect_to, f"/incidents/{incident_id}/aar?tab=verloop")
    return redirect_with_flash(target, "Foto/plan gekoppeld.")


@router.post("/incidents/{incident_id}/media/link-commander")
def link_photo_to_commander(
    incident_id: int,
    photo_id: int = Form(...),
    commander_report_id: str = Form(""),
    session: Session = Depends(get_db),
):
    writable_incident_or_404(session, incident_id)
    doc = _photo_only_or_404(session, incident_id, photo_id)
    report = None
    if commander_report_id:
        report = session.get(CommanderReport, int(commander_report_id))
        if report is None or report.incident_id != incident_id:
            report = None
    media_service.link_to_commander_report(session, doc, report)
    target = f"/incidents/{incident_id}/aar?tab=waarnemingen"
    if report is not None:
        target += f"&open={report.id}"
    return redirect_with_flash(target, "Foto/plan gekoppeld.")


@router.post("/incidents/{incident_id}/media/{doc_id}/delete")
def delete_photo(incident_id: int, doc_id: int, redirect_to: str = Form(""), session: Session = Depends(get_db)):
    writable_incident_or_404(session, incident_id)
    doc = _photo_only_or_404(session, incident_id, doc_id)
    media_service.delete_photo(session, doc)
    target = _safe_redirect(incident_id, redirect_to, f"/incidents/{incident_id}/sources")
    return redirect_with_flash(target, "Bestand verwijderd.")
