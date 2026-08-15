from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from aar.models import IncidentEvent, SourceDocument
from aar.services import media_service
from aar.services.errors import DuplicateSourceError
from aar.web.deps import get_db, incident_or_404
from aar.web.flash import redirect_with_flash

router = APIRouter()


def _photo_or_404(session: Session, incident_id: int, doc_id: int) -> SourceDocument:
    doc = session.get(SourceDocument, doc_id)
    if doc is None or doc.incident_id != incident_id:
        raise HTTPException(status_code=404, detail="Bestand niet gevonden")
    return doc


@router.post("/incidents/{incident_id}/sources/photos")
async def upload_photos(
    incident_id: int, files: list[UploadFile] = File(...), session: Session = Depends(get_db)
):
    incident = incident_or_404(session, incident_id)
    messages = []
    for f in files:
        content = await f.read()
        try:
            media_service.ingest_photo(session, incident, content, f.filename)
        except (DuplicateSourceError, media_service.UnsupportedMediaTypeError) as exc:
            messages.append(str(exc))

    flash = "; ".join(messages) if messages else "Foto's/plannen toegevoegd."
    flash_type = "warning" if messages else "success"
    return redirect_with_flash(f"/incidents/{incident_id}/sources", flash, flash_type)


@router.get("/incidents/{incident_id}/media/{doc_id}")
def view_media(incident_id: int, doc_id: int, session: Session = Depends(get_db)):
    doc = _photo_or_404(session, incident_id, doc_id)
    media_type = mimetypes.guess_type(doc.original_filename)[0] or "application/octet-stream"
    return FileResponse(doc.stored_path, media_type=media_type)


@router.post("/incidents/{incident_id}/media/{doc_id}/caption")
def update_caption(incident_id: int, doc_id: int, caption: str = Form(""), session: Session = Depends(get_db)):
    doc = _photo_or_404(session, incident_id, doc_id)
    media_service.set_caption(session, doc, caption)
    return redirect_with_flash(f"/incidents/{incident_id}/sources", "Bijschrift opgeslagen.")


@router.post("/incidents/{incident_id}/media/link")
def link_photo(
    incident_id: int, photo_id: int = Form(...), event_id: str = Form(""), session: Session = Depends(get_db)
):
    doc = _photo_or_404(session, incident_id, photo_id)
    event = None
    if event_id:
        event = session.get(IncidentEvent, int(event_id))
        if event is None or event.incident_id != incident_id:
            event = None
    media_service.link_to_event(session, doc, event)
    return redirect_with_flash(f"/incidents/{incident_id}/aar?tab=verloop", "Foto/plan gekoppeld.")


@router.post("/incidents/{incident_id}/media/{doc_id}/delete")
def delete_photo(incident_id: int, doc_id: int, session: Session = Depends(get_db)):
    doc = _photo_or_404(session, incident_id, doc_id)
    media_service.delete_photo(session, doc)
    return redirect_with_flash(f"/incidents/{incident_id}/sources", "Bestand verwijderd.")
