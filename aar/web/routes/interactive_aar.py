from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from aar.models import (
    CommanderReport,
    DiscussionPoint,
    Improvement,
    IncidentEvent,
    IncidentStatus,
    Lesson,
    Observation,
    PositiveFinding,
)
from aar.services import aar_service, media_service
from aar.services.analysis_service import trigger_analysis
from aar.web.deps import get_db, incident_or_404
from aar.web.flash import redirect_with_flash
from aar.web.templating import templates

router = APIRouter()

VALID_TABS = {"overzicht", "verloop", "bespreken", "positief", "leerpunten"}


@router.get("/incidents/{incident_id}/aar")
def aar_page(incident_id: int, request: Request, tab: str = "overzicht", session: Session = Depends(get_db)):
    incident = incident_or_404(session, incident_id)
    if incident.status == IncidentStatus.ANALYZED:
        incident.status = IncidentStatus.IN_REVIEW
        session.commit()

    if tab not in VALID_TABS:
        tab = "overzicht"

    events = aar_service.get_events(session, incident)
    discussion_points = aar_service.get_discussion_points(session, incident)
    positive_findings = aar_service.get_positive_findings(session, incident)
    lessons = aar_service.get_lessons(session, incident)
    improvements = aar_service.get_improvements(session, incident)

    # Order by the narrative position of the moment each is linked to (the
    # only "chronology" the tool ever claims — relative order, never a
    # fabricated clock time) rather than arbitrary insertion order.
    _no_order = len(events) + 1
    discussion_points.sort(key=lambda dp: dp.event.order_index if dp.event else _no_order)
    positive_findings.sort(key=lambda pf: pf.event.order_index if pf.event else _no_order)

    improvements_by_lesson: dict[int | None, list] = {}
    for imp in improvements:
        improvements_by_lesson.setdefault(imp.related_lesson_id, []).append(imp)

    observations = session.query(Observation).filter_by(incident_id=incident.id).all()
    observations_by_id = {o.id: o for o in observations}

    default_summary = incident.situation_summary or aar_service.default_situation_summary(session, incident)
    timed_events = sorted([e for e in events if e.exact_time is not None], key=lambda e: e.exact_time)
    commander_reports = (
        session.query(CommanderReport).filter_by(incident_id=incident.id).order_by(CommanderReport.callsign).all()
    )

    photos = media_service.list_photos(session, incident)
    photos_by_event: dict[int | None, list] = {}
    for p in photos:
        photos_by_event.setdefault(p.event_id, []).append(p)
    unlinked_photos = photos_by_event.get(None, [])

    return templates.TemplateResponse(
        request,
        "aar.html",
        {
            "active_nav": "aar",
            "incident": incident,
            "tab": tab,
            "events": events,
            "timed_events": timed_events,
            "discussion_points": discussion_points,
            "positive_findings": positive_findings,
            "lessons": lessons,
            "improvements_by_lesson": improvements_by_lesson,
            "unlinked_improvements": improvements_by_lesson.get(None, []),
            "observations_by_id": observations_by_id,
            "default_summary": default_summary,
            "photos": photos,
            "photos_by_event": photos_by_event,
            "unlinked_photos": unlinked_photos,
            "commander_reports": commander_reports,
        },
    )


def _back(incident_id: int, tab: str) -> str:
    return f"/incidents/{incident_id}/aar?tab={tab}"


def _require_title(incident_id: int, tab: str, title: str) -> str | None:
    """Returns an error redirect if `title` is blank, else None. Guards
    against empty submissions reaching the service layer — Starlette treats
    an empty form field as absent for required Form(...) params, which would
    otherwise surface as a raw 422 instead of a friendly message (a real
    browser will submit an empty string for a blank text input)."""
    if not title.strip():
        return redirect_with_flash(_back(incident_id, tab), "Titel mag niet leeg zijn.", "error")
    return None


@router.post("/incidents/{incident_id}/aar/situation-summary")
def update_situation_summary(incident_id: int, text: str = Form(""), session: Session = Depends(get_db)):
    incident = incident_or_404(session, incident_id)
    aar_service.update_situation_summary(session, incident, text)
    return redirect_with_flash(_back(incident_id, "overzicht"), "Samenvatting opgeslagen.")


@router.post("/incidents/{incident_id}/aar/reanalyze")
def reanalyze(incident_id: int, session: Session = Depends(get_db)):
    incident = incident_or_404(session, incident_id)
    run = trigger_analysis(session, incident)
    if run.status.value == "success":
        return redirect_with_flash(_back(incident_id, "overzicht"), "Heranalyse voltooid.")
    return redirect_with_flash(_back(incident_id, "overzicht"), f"Heranalyse mislukt: {run.error_message}", "error")


# -- events ---------------------------------------------------------------


@router.post("/incidents/{incident_id}/aar/events")
def add_event(incident_id: int, title: str = Form(""), session: Session = Depends(get_db)):
    if (err := _require_title(incident_id, "verloop", title)) is not None:
        return err
    incident = incident_or_404(session, incident_id)
    aar_service.add_manual_event(session, incident, title)
    return redirect_with_flash(_back(incident_id, "verloop"), "Moment toegevoegd.")


@router.post("/incidents/{incident_id}/aar/events/{event_id}/update")
def update_event(incident_id: int, event_id: int, summary: str = Form(""), session: Session = Depends(get_db)):
    incident_or_404(session, incident_id)
    event = session.get(IncidentEvent, event_id)
    if event is not None:
        aar_service.update_event_summary(session, event, summary)
    return redirect_with_flash(_back(incident_id, "verloop"), "Moment opgeslagen.")


@router.post("/incidents/{incident_id}/aar/events/{event_id}/delete")
def delete_event(incident_id: int, event_id: int, session: Session = Depends(get_db)):
    incident_or_404(session, incident_id)
    event = session.get(IncidentEvent, event_id)
    if event is not None:
        aar_service.delete_event(session, event)
    return redirect_with_flash(_back(incident_id, "verloop"), "Moment verwijderd.")


@router.post("/incidents/{incident_id}/aar/events/{event_id}/correction")
def add_event_correction(incident_id: int, event_id: int, text: str = Form(""), session: Session = Depends(get_db)):
    if not text.strip():
        return redirect_with_flash(_back(incident_id, "verloop"), "Correctie mag niet leeg zijn.", "error")
    incident = incident_or_404(session, incident_id)
    aar_service.add_correction(session, incident, "event", event_id, text)
    return redirect_with_flash(
        _back(incident_id, "verloop"), "Correctie opgeslagen. Voer een heranalyse uit om ze te verwerken."
    )


# -- discussion points ------------------------------------------------------


@router.post("/incidents/{incident_id}/aar/discussion-points")
def add_discussion_point(
    incident_id: int, title: str = Form(""), description: str = Form(""), session: Session = Depends(get_db)
):
    if (err := _require_title(incident_id, "bespreken", title)) is not None:
        return err
    incident = incident_or_404(session, incident_id)
    aar_service.add_manual_discussion_point(session, incident, title, description)
    return redirect_with_flash(_back(incident_id, "bespreken"), "Bespreekpunt toegevoegd.")


@router.post("/incidents/{incident_id}/aar/discussion-points/{dp_id}/update")
def update_discussion_point(
    incident_id: int, dp_id: int, title: str = Form(""), description: str = Form(""), session: Session = Depends(get_db)
):
    if (err := _require_title(incident_id, "bespreken", title)) is not None:
        return err
    incident_or_404(session, incident_id)
    dp = session.get(DiscussionPoint, dp_id)
    if dp is not None:
        aar_service.update_discussion_point(session, dp, title, description)
    return redirect_with_flash(_back(incident_id, "bespreken"), "Bespreekpunt opgeslagen.")


@router.post("/incidents/{incident_id}/aar/discussion-points/{dp_id}/delete")
def delete_discussion_point(incident_id: int, dp_id: int, session: Session = Depends(get_db)):
    incident_or_404(session, incident_id)
    dp = session.get(DiscussionPoint, dp_id)
    if dp is not None:
        aar_service.delete_discussion_point(session, dp)
    return redirect_with_flash(_back(incident_id, "bespreken"), "Bespreekpunt verwijderd.")


# -- positive findings --------------------------------------------------------


@router.post("/incidents/{incident_id}/aar/positive-findings")
def add_positive_finding(
    incident_id: int, title: str = Form(""), description: str = Form(""), session: Session = Depends(get_db)
):
    if (err := _require_title(incident_id, "positief", title)) is not None:
        return err
    incident = incident_or_404(session, incident_id)
    aar_service.add_manual_positive_finding(session, incident, title, description)
    return redirect_with_flash(_back(incident_id, "positief"), "Positief punt toegevoegd.")


@router.post("/incidents/{incident_id}/aar/positive-findings/{pf_id}/update")
def update_positive_finding(
    incident_id: int, pf_id: int, title: str = Form(""), description: str = Form(""), session: Session = Depends(get_db)
):
    if (err := _require_title(incident_id, "positief", title)) is not None:
        return err
    incident_or_404(session, incident_id)
    pf = session.get(PositiveFinding, pf_id)
    if pf is not None:
        aar_service.update_positive_finding(session, pf, title, description)
    return redirect_with_flash(_back(incident_id, "positief"), "Positief punt opgeslagen.")


@router.post("/incidents/{incident_id}/aar/positive-findings/{pf_id}/delete")
def delete_positive_finding(incident_id: int, pf_id: int, session: Session = Depends(get_db)):
    incident_or_404(session, incident_id)
    pf = session.get(PositiveFinding, pf_id)
    if pf is not None:
        aar_service.delete_positive_finding(session, pf)
    return redirect_with_flash(_back(incident_id, "positief"), "Positief punt verwijderd.")


# -- lessons & improvements --------------------------------------------------


@router.post("/incidents/{incident_id}/aar/lessons")
def add_lesson(
    incident_id: int, title: str = Form(""), description: str = Form(""), session: Session = Depends(get_db)
):
    if (err := _require_title(incident_id, "leerpunten", title)) is not None:
        return err
    incident = incident_or_404(session, incident_id)
    aar_service.add_manual_lesson(session, incident, title, description)
    return redirect_with_flash(_back(incident_id, "leerpunten"), "Leerpunt toegevoegd.")


@router.post("/incidents/{incident_id}/aar/lessons/{lesson_id}/update")
def update_lesson(
    incident_id: int, lesson_id: int, title: str = Form(""), description: str = Form(""), session: Session = Depends(get_db)
):
    if (err := _require_title(incident_id, "leerpunten", title)) is not None:
        return err
    incident_or_404(session, incident_id)
    lesson = session.get(Lesson, lesson_id)
    if lesson is not None:
        aar_service.update_lesson(session, lesson, title, description)
    return redirect_with_flash(_back(incident_id, "leerpunten"), "Leerpunt opgeslagen.")


@router.post("/incidents/{incident_id}/aar/lessons/{lesson_id}/delete")
def delete_lesson(incident_id: int, lesson_id: int, session: Session = Depends(get_db)):
    incident_or_404(session, incident_id)
    lesson = session.get(Lesson, lesson_id)
    if lesson is not None:
        aar_service.delete_lesson(session, lesson)
    return redirect_with_flash(_back(incident_id, "leerpunten"), "Leerpunt verwijderd.")


@router.post("/incidents/{incident_id}/aar/improvements")
def add_improvement(
    incident_id: int, title: str = Form(""), description: str = Form(""), session: Session = Depends(get_db)
):
    if (err := _require_title(incident_id, "leerpunten", title)) is not None:
        return err
    incident = incident_or_404(session, incident_id)
    aar_service.add_manual_improvement(session, incident, title, description)
    return redirect_with_flash(_back(incident_id, "leerpunten"), "Verbetering toegevoegd.")


@router.post("/incidents/{incident_id}/aar/improvements/{imp_id}/delete")
def delete_improvement(incident_id: int, imp_id: int, session: Session = Depends(get_db)):
    incident_or_404(session, incident_id)
    imp = session.get(Improvement, imp_id)
    if imp is not None:
        aar_service.delete_improvement(session, imp)
    return redirect_with_flash(_back(incident_id, "leerpunten"), "Verbetering verwijderd.")
