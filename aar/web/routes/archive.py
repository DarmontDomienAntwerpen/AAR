from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from aar.models import IncidentType
from aar.services.incident_service import list_incidents
from aar.web.deps import get_db
from aar.web.templating import templates

router = APIRouter()


@router.get("/")
def archive(
    request: Request,
    q: str | None = None,
    type: str | None = None,
    session: Session = Depends(get_db),
):
    incident_type = IncidentType(type) if type else None
    incidents = list_incidents(session, search_text=q, incident_type=incident_type)
    return templates.TemplateResponse(
        request,
        "archive.html",
        {
            "active_nav": "archive",
            "incidents": incidents,
            "q": q or "",
            "selected_type": type or "",
        },
    )
