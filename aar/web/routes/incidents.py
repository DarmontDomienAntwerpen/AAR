from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import ValidationError
from sqlalchemy.orm import Session

from aar.models import IncidentType
from aar.schemas.forms import IncidentCreateForm
from aar.services import media_service
from aar.services.errors import DuplicateSourceError
from aar.services.incident_service import create_incident
from aar.web.deps import get_db
from aar.web.flash import redirect_with_flash
from aar.web.templating import templates

router = APIRouter()


@router.get("/incidents/new")
def new_incident_form(request: Request):
    return templates.TemplateResponse(
        request,
        "new_incident.html",
        {"active_nav": "new_incident", "IncidentType": IncidentType, "errors": None, "form": {}},
    )


@router.post("/incidents/new")
async def create_incident_submit(
    request: Request,
    date: str = Form(""),
    location: str = Form(""),
    incident_type: str = Form(""),
    description: str = Form(""),
    photos: list[UploadFile] = File(default=[]),
    session: Session = Depends(get_db),
):
    try:
        if not date or not location or not incident_type:
            raise ValueError("Vul alle verplichte velden in (datum, locatie, type).")
        form = IncidentCreateForm(
            date=dt.date.fromisoformat(date),
            location=location,
            incident_type=IncidentType(incident_type),
            description=description,
        )
    except (ValidationError, ValueError) as exc:
        message = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
        return templates.TemplateResponse(
            request,
            "new_incident.html",
            {
                "active_nav": "new_incident",
                "IncidentType": IncidentType,
                "errors": message,
                "form": {"date": date, "location": location, "incident_type": incident_type, "description": description},
            },
            status_code=400,
        )

    incident = create_incident(session, form)

    photo_warnings = []
    for f in photos:
        if not f.filename:
            continue
        content = await f.read()
        try:
            media_service.ingest_photo(session, incident, content, f.filename)
        except (DuplicateSourceError, media_service.UnsupportedMediaTypeError) as exc:
            photo_warnings.append(str(exc))

    if photo_warnings:
        return redirect_with_flash(
            f"/incidents/{incident.id}/sources",
            "Incident aangemaakt. " + "; ".join(photo_warnings),
            "warning",
        )
    return redirect_with_flash(f"/incidents/{incident.id}/sources", "Incident aangemaakt.")
