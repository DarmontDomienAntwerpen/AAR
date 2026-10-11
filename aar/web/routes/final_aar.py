from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from aar.services import aar_service, media_service
from aar.web.deps import get_db, incident_or_404
from aar.web.flash import redirect_with_flash
from aar.web.templating import templates

router = APIRouter()


@router.get("/incidents/{incident_id}/final")
def final_aar_page(incident_id: int, request: Request, session: Session = Depends(get_db)):
    incident = incident_or_404(session, incident_id)
    events = aar_service.get_events(session, incident)
    timed_events = sorted([e for e in events if e.exact_time is not None], key=lambda e: e.exact_time)
    situation_summary = (
        incident.situation_summary
        or incident.ai_situation_narrative
        or aar_service.default_situation_summary(session, incident)
    )

    return templates.TemplateResponse(
        request,
        "final_aar.html",
        {
            "active_nav": "final",
            "incident": incident,
            "events": events,
            "timed_events": timed_events,
            "situation_summary": situation_summary,
            "photos": media_service.list_photos(session, incident),
            "positive_findings": aar_service.get_positive_findings(session, incident),
            "discussion_points": aar_service.get_discussion_points(session, incident),
            "lessons": aar_service.get_lessons(session, incident),
            "improvements": aar_service.get_improvements(session, incident),
        },
    )


@router.post("/incidents/{incident_id}/final/finalize")
def finalize(incident_id: int, session: Session = Depends(get_db)):
    incident = incident_or_404(session, incident_id)
    aar_service.finalize_incident(session, incident)
    return redirect_with_flash(f"/incidents/{incident_id}/final", "AAR gemarkeerd als afgerond.")


@router.post("/incidents/{incident_id}/final/reopen")
def reopen(incident_id: int, session: Session = Depends(get_db)):
    incident = incident_or_404(session, incident_id)
    aar_service.reopen_incident(session, incident)
    return redirect_with_flash(f"/incidents/{incident_id}/final", "AAR heropend — aanpassingen zijn weer mogelijk.")
