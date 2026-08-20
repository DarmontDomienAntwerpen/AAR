from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Form, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session

from aar.models import (
    CommanderReport,
    DiscussionPoint,
    Improvement,
    IncidentEvent,
    IncidentStatus,
    IncidentType,
    Lesson,
    Observation,
    PositiveFinding,
)
from aar.models.enums import ObjectiveAchieved
from aar.schemas.constants import CATEGORY_ORDER, CATEGORY_SUPERGROUP, SUPERGROUP_LABELS_NL, SUPERGROUP_ORDER
from aar.services import aar_service, incident_service, media_service
from aar.services.analysis_service import trigger_analysis
from aar.web.deps import get_db, incident_or_404
from aar.web.flash import redirect_with_flash
from aar.web.templating import templates

router = APIRouter()

VALID_TABS = {
    "overzicht",
    "verslagen",
    "middelen",
    "waarnemingen",
    "verloop",
    "bespreken",
    "positief",
    "leerpunten",
}


def _callsign_sort_key(callsign: str) -> tuple:
    """Command-structure-aware ordering: numeric callsigns group under their
    hundred (LVO 100 leads 110/120/130..., LVO 200 leads 210/220...) and
    sort chronologically within that group; non-numeric callsigns (e.g.
    "AL1" for a standalone ladder truck with no place in the command
    hierarchy) sort after, alphabetically among themselves."""
    digits = (callsign or "").strip()
    if digits.isdigit():
        n = int(digits)
        return (0, (n // 100) * 100, n)
    return (1, 0, digits)


def _group_by_command_structure(
    reports: list[CommanderReport],
) -> list[tuple[str | None, list[CommanderReport]]]:
    """Groups already-`_callsign_sort_key`-sorted reports into
    `(hundred_label, [reports])` — one group per LVO hundred (e.g. "100"),
    plus a trailing `(None, [...])` group for non-numeric ("losse eenheden")
    callsigns. Relies on the input already being sorted so same-group
    reports are consecutive."""
    groups: list[tuple[str | None, list[CommanderReport]]] = []
    for r in reports:
        digits = (r.callsign or "").strip()
        group_key = str((int(digits) // 100) * 100) if digits.isdigit() else None
        if not groups or groups[-1][0] != group_key:
            groups.append((group_key, []))
        groups[-1][1].append(r)
    return groups


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

    discussion_points_by_id = {dp.id: dp for dp in discussion_points}

    improvements_by_lesson: dict[int | None, list] = {}
    for imp in improvements:
        improvements_by_lesson.setdefault(imp.related_lesson_id, []).append(imp)

    observations = session.query(Observation).filter_by(incident_id=incident.id).all()
    observations_by_id = {o.id: o for o in observations}
    observations_by_report: dict[int, list[Observation]] = {}
    for o in observations:
        if o.commander_report_id:
            observations_by_report.setdefault(o.commander_report_id, []).append(o)

    # Pre-grouped and pre-sorted per commander, so the "Waarnemingen & acties"
    # template only has to render — no sorting/grouping logic belongs in
    # Jinja. Two levels: broad supergroup (feiten/inschatting/acties/...,
    # rendered as one column top-to-bottom so reading order follows the
    # narrative arc) containing its categories (finer sub-labels within).
    commander_topics: dict[int, list[tuple]] = {}
    for report_id, obs_list in observations_by_report.items():
        by_supergroup: dict[str, dict] = {}
        for o in obs_list:
            supergroup = CATEGORY_SUPERGROUP.get(o.category, "overig")
            by_supergroup.setdefault(supergroup, {}).setdefault(o.category, []).append(o)
        commander_topics[report_id] = [
            (
                supergroup,
                SUPERGROUP_LABELS_NL.get(supergroup, supergroup),
                sorted(by_supergroup[supergroup].items(), key=lambda kv: CATEGORY_ORDER.get(kv[0], 99)),
            )
            for supergroup in sorted(by_supergroup.keys(), key=lambda k: SUPERGROUP_ORDER.get(k, 99))
        ]

    default_summary = (
        incident.situation_summary
        or incident.ai_situation_narrative
        or aar_service.default_situation_summary(session, incident)
    )
    timed_events = sorted([e for e in events if e.exact_time is not None], key=lambda e: e.exact_time)
    commander_reports = sorted(
        session.query(CommanderReport).filter_by(incident_id=incident.id).all(),
        key=lambda r: _callsign_sort_key(r.callsign),
    )
    commander_groups = _group_by_command_structure(commander_reports)

    # Per-commander dashboard counts: how many bespreekpunten/positieve
    # punten this commander's own observations contributed to (a merged
    # point attributed to multiple commanders counts for each of them).
    commander_stats: dict[int, dict[str, int]] = {r.id: {"discussion": 0, "positive": 0} for r in commander_reports}
    for dp in discussion_points:
        for rid in {
            observations_by_id[oid].commander_report_id
            for oid in dp.observation_ids
            if oid in observations_by_id and observations_by_id[oid].commander_report_id in commander_stats
        }:
            commander_stats[rid]["discussion"] += 1
    for pf in positive_findings:
        for rid in {
            observations_by_id[oid].commander_report_id
            for oid in pf.observation_ids
            if oid in observations_by_id and observations_by_id[oid].commander_report_id in commander_stats
        }:
            commander_stats[rid]["positive"] += 1

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
            "discussion_points_by_id": discussion_points_by_id,
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
            "commander_groups": commander_groups,
            "commander_stats": commander_stats,
            "commander_topics": commander_topics,
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


@router.post("/incidents/{incident_id}/aar/incident-details")
def update_incident_details(
    incident_id: int,
    date: str = Form(""),
    location: str = Form(""),
    incident_type: str = Form(""),
    description: str = Form(""),
    session: Session = Depends(get_db),
):
    incident = incident_or_404(session, incident_id)
    try:
        if not date or not location or not incident_type:
            raise ValueError("Vul alle verplichte velden in (datum, locatie, type).")
        parsed_date = dt.date.fromisoformat(date)
        parsed_type = IncidentType(incident_type)
    except (ValidationError, ValueError) as exc:
        message = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
        return redirect_with_flash(_back(incident_id, "overzicht"), message, "error")

    incident_service.update_incident_details(
        session,
        incident,
        date=parsed_date,
        location=location,
        incident_type=parsed_type,
        description=description,
    )
    return redirect_with_flash(_back(incident_id, "overzicht"), "Incidentgegevens opgeslagen.")


@router.post("/incidents/{incident_id}/aar/initial-call-notes")
def update_initial_call_notes(incident_id: int, text: str = Form(""), session: Session = Depends(get_db)):
    incident = incident_or_404(session, incident_id)
    incident_service.update_initial_call_notes(session, incident, text)
    return redirect_with_flash(_back(incident_id, "overzicht"), "Oproepgegevens opgeslagen.")


@router.post("/incidents/{incident_id}/aar/situation-summary")
def update_situation_summary(incident_id: int, text: str = Form(""), session: Session = Depends(get_db)):
    incident = incident_or_404(session, incident_id)
    aar_service.update_situation_summary(session, incident, text)
    return redirect_with_flash(_back(incident_id, "overzicht"), "Samenvatting opgeslagen.")


@router.post("/incidents/{incident_id}/aar/commander-notes/{report_id}")
def update_commander_notes(
    incident_id: int, report_id: int, text: str = Form(""), session: Session = Depends(get_db)
):
    incident_or_404(session, incident_id)
    report = session.get(CommanderReport, report_id)
    if report is None or report.incident_id != incident_id:
        return redirect_with_flash(_back(incident_id, "waarnemingen"), "Verslag niet gevonden.", "error")
    aar_service.update_commander_notes(session, report, text)
    return redirect_with_flash(_back(incident_id, "waarnemingen"), "Notities opgeslagen.")


@router.post("/incidents/{incident_id}/aar/commander-identity/{report_id}")
def update_commander_identity(
    incident_id: int,
    report_id: int,
    callsign: str = Form(""),
    unit_name: str = Form(""),
    rank: str = Form(""),
    surname: str = Form(""),
    objective_achieved: str = Form(""),
    objective_achieved_explanation: str = Form(""),
    session: Session = Depends(get_db),
):
    incident_or_404(session, incident_id)
    report = session.get(CommanderReport, report_id)
    if report is None or report.incident_id != incident_id:
        return redirect_with_flash(_back(incident_id, "waarnemingen"), "Verslag niet gevonden.", "error")
    try:
        objective_value = ObjectiveAchieved(objective_achieved) if objective_achieved else None
    except ValueError:
        objective_value = None
    aar_service.update_commander_identity(
        session,
        report,
        callsign=callsign,
        unit_name=unit_name,
        rank=rank,
        surname=surname,
        objective_achieved=objective_value,
        objective_achieved_explanation=objective_achieved_explanation,
    )
    return redirect_with_flash(_back(incident_id, "waarnemingen"), "Gegevens opgeslagen.")


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


@router.post("/incidents/{incident_id}/aar/discussion-points/{dp_id}/toggle-discussed")
def toggle_discussion_point_discussed(incident_id: int, dp_id: int, session: Session = Depends(get_db)):
    incident_or_404(session, incident_id)
    dp = session.get(DiscussionPoint, dp_id)
    if dp is not None:
        aar_service.toggle_discussion_point_discussed(session, dp)
    return redirect_with_flash(_back(incident_id, "bespreken"), "Bespreekpunt bijgewerkt.")


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
