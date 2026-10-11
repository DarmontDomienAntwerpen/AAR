"""CRUD + human-in-the-loop editing for the interactive AAR (spec §48).

Every mutation here is deterministic Python — no LLM involved. The
facilitator is the final authority: edits/deletes are immediate and no
AI-vs-human audit trail is kept (spec §50), only current validated content.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from aar.models import (
    CommanderReport,
    CreatedBy,
    DiscussionPoint,
    EventPerspective,
    HumanCorrection,
    Improvement,
    Incident,
    IncidentEvent,
    IncidentStatus,
    Lesson,
    Observation,
    ObservationCategory,
    ObservationType,
    PositiveFinding,
    SourceDocument,
)
from aar.schemas.constants import CRUCIAL_SUMMARY_CATEGORIES

# Matched against each event's *observations* (their category), not the
# event's own title: a real LLM gives events specific, content-derived
# titles (e.g. "Beslissing opschaling en zoekactie P34"), never the bare
# category label — matching against the title left this filter finding
# nothing and the summary permanently empty for real analyses.

# -- reads -------------------------------------------------------------


def get_events(session: Session, incident: Incident) -> list[IncidentEvent]:
    return (
        session.query(IncidentEvent)
        .filter_by(incident_id=incident.id)
        .order_by(IncidentEvent.order_index)
        .all()
    )


def get_discussion_points(session: Session, incident: Incident) -> list[DiscussionPoint]:
    return session.query(DiscussionPoint).filter_by(incident_id=incident.id).all()


def get_positive_findings(session: Session, incident: Incident) -> list[PositiveFinding]:
    return session.query(PositiveFinding).filter_by(incident_id=incident.id).all()


def get_lessons(session: Session, incident: Incident) -> list[Lesson]:
    return session.query(Lesson).filter_by(incident_id=incident.id).all()


def get_improvements(session: Session, incident: Incident) -> list[Improvement]:
    return session.query(Improvement).filter_by(incident_id=incident.id).all()


def get_observations_by_ids(session: Session, ids: list[int]) -> list[Observation]:
    if not ids:
        return []
    return session.query(Observation).filter(Observation.id.in_(ids)).all()


# -- event edits ---------------------------------------------------------


def update_event_summary(session: Session, event: IncidentEvent, new_summary: str) -> IncidentEvent:
    event.ai_summary = new_summary.strip()
    session.commit()
    session.refresh(event)
    return event


def update_commander_notes(session: Session, report: CommanderReport, text: str) -> CommanderReport:
    """Facilitator's live notes captured while this commander talks through
    their part during the AAR meeting — never touched by re-analysis."""
    report.facilitator_notes = text.strip()
    session.commit()
    session.refresh(report)
    return report


def update_commander_identity(
    session: Session,
    report: CommanderReport,
    *,
    callsign: str,
    unit_name: str,
    rank: str,
    surname: str,
) -> CommanderReport:
    """Facilitator correction of a commander's identity fields (transcription
    fixes — callsign, unit name, rank, surname)."""
    report.callsign = callsign.strip()
    report.unit_name = unit_name.strip()
    report.rank = rank.strip()
    report.surname = surname.strip()
    session.commit()
    session.refresh(report)
    return report


def add_manual_event(session: Session, incident: Incident, title: str) -> IncidentEvent:
    max_order = max((e.order_index for e in get_events(session, incident)), default=-1)
    event = IncidentEvent(
        incident_id=incident.id, title=title.strip(), order_index=max_order + 1, is_human_added=True
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def delete_event(session: Session, event: IncidentEvent) -> None:
    session.query(EventPerspective).filter_by(event_id=event.id).delete()
    session.query(SourceDocument).filter_by(event_id=event.id).update({"event_id": None})
    session.delete(event)
    session.commit()


# -- discussion points / positive findings / lessons / improvements ------


def add_manual_discussion_point(
    session: Session, incident: Incident, title: str, description: str
) -> DiscussionPoint:
    dp = DiscussionPoint(
        incident_id=incident.id, title=title.strip(), description=description.strip(), is_human_added=True
    )
    session.add(dp)
    session.commit()
    session.refresh(dp)
    return dp


def update_discussion_point(session: Session, dp: DiscussionPoint, title: str, description: str) -> DiscussionPoint:
    dp.title = title.strip()
    dp.description = description.strip()
    session.commit()
    session.refresh(dp)
    return dp


def update_discussion_point_notes(session: Session, dp: DiscussionPoint, text: str) -> DiscussionPoint:
    dp.facilitator_notes = text.strip()
    session.commit()
    session.refresh(dp)
    return dp


def delete_discussion_point(session: Session, dp: DiscussionPoint) -> None:
    session.delete(dp)
    session.commit()


def toggle_discussion_point_discussed(session: Session, dp: DiscussionPoint) -> DiscussionPoint:
    dp.discussed = not dp.discussed
    session.commit()
    session.refresh(dp)
    return dp


def add_manual_positive_finding(session: Session, incident: Incident, title: str, description: str) -> PositiveFinding:
    pf = PositiveFinding(
        incident_id=incident.id, title=title.strip(), description=description.strip(), is_human_added=True
    )
    session.add(pf)
    session.commit()
    session.refresh(pf)
    return pf


def update_positive_finding(session: Session, pf: PositiveFinding, title: str, description: str) -> PositiveFinding:
    pf.title = title.strip()
    pf.description = description.strip()
    session.commit()
    session.refresh(pf)
    return pf


def delete_positive_finding(session: Session, pf: PositiveFinding) -> None:
    session.delete(pf)
    session.commit()


def add_manual_werkpunt(session: Session, incident: Incident, content: str) -> Observation:
    """Werkpunten are otherwise a direct, unfiltered pull-through of the
    form's "Wat kon beter" section — a manually-added one is the one
    exception, not tied to any single commander's report (same pattern as
    add_manual_positive_finding)."""
    obs = Observation(
        incident_id=incident.id,
        commander_report_id=None,
        observation_type=ObservationType.HUMAN_OBSERVATION,
        category=ObservationCategory.WENT_LESS_WELL,
        content=content.strip(),
        source_section="went_less_well",
        created_by=CreatedBy.HUMAN,
    )
    session.add(obs)
    session.commit()
    session.refresh(obs)
    return obs


def update_werkpunt(session: Session, obs: Observation, content: str) -> Observation:
    obs.content = content.strip()
    session.commit()
    session.refresh(obs)
    return obs


def delete_werkpunt(session: Session, obs: Observation) -> None:
    session.delete(obs)
    session.commit()


def add_manual_lesson(session: Session, incident: Incident, title: str, description: str) -> Lesson:
    lesson = Lesson(
        incident_id=incident.id, title=title.strip(), description=description.strip(), is_human_added=True
    )
    session.add(lesson)
    session.commit()
    session.refresh(lesson)
    return lesson


def update_lesson(session: Session, lesson: Lesson, title: str, description: str) -> Lesson:
    lesson.title = title.strip()
    lesson.description = description.strip()
    session.commit()
    session.refresh(lesson)
    return lesson


def delete_lesson(session: Session, lesson: Lesson) -> None:
    session.delete(lesson)
    session.commit()


def add_manual_improvement(session: Session, incident: Incident, title: str, description: str) -> Improvement:
    imp = Improvement(
        incident_id=incident.id, title=title.strip(), description=description.strip(), is_human_added=True
    )
    session.add(imp)
    session.commit()
    session.refresh(imp)
    return imp


def update_improvement(session: Session, imp: Improvement, title: str, description: str) -> Improvement:
    imp.title = title.strip()
    imp.description = description.strip()
    session.commit()
    session.refresh(imp)
    return imp


def delete_improvement(session: Session, imp: Improvement) -> None:
    session.delete(imp)
    session.commit()


# -- corrections / finalisation ------------------------------------------


def add_correction(
    session: Session, incident: Incident, target_type: str, target_id: int | None, correction_text: str
) -> HumanCorrection:
    correction = HumanCorrection(
        incident_id=incident.id,
        target_type=target_type,
        target_id=target_id,
        correction_text=correction_text.strip(),
    )
    session.add(correction)
    session.commit()
    session.refresh(correction)
    if incident.status == IncidentStatus.ANALYZED:
        incident.status = IncidentStatus.IN_REVIEW
        session.commit()
    return correction


def default_situation_summary(session: Session, incident: Incident) -> str:
    """A structured starting draft for the facilitator to edit — grouped per
    incident moment, with each commander's account kept as its own
    attributed line rather than merged into one unattributed paragraph.
    Different commanders can genuinely disagree or report different things
    about the same moment; collapsing that into one blended narrative would
    misrepresent it as a single agreed-upon account."""
    events = get_events(session, incident)
    crucial_obs_ids = {
        oid
        for (oid,) in session.query(Observation.id)
        .filter(Observation.incident_id == incident.id, Observation.category.in_(CRUCIAL_SUMMARY_CATEGORIES))
        .all()
    }
    relevant = [
        e
        for e in events
        if e.is_human_added or any(oid in crucial_obs_ids for oid in (e.observation_ids or []))
    ]
    blocks: list[str] = []
    for event in relevant:
        lines = [f"{p.commander_display_name}: {p.perspective_text}" for p in event.perspectives if p.perspective_text]
        if lines:
            blocks.append(event.title + "\n" + "\n".join(lines))
        elif event.ai_summary:
            blocks.append(event.title + "\n" + event.ai_summary)
    return "\n\n".join(blocks)


def update_situation_summary(session: Session, incident: Incident, text: str) -> Incident:
    incident.situation_summary = text.strip()
    session.commit()
    session.refresh(incident)
    return incident


def finalize_incident(session: Session, incident: Incident) -> Incident:
    incident.status = IncidentStatus.FINALIZED
    session.commit()
    session.refresh(incident)
    return incident


def reopen_incident(session: Session, incident: Incident) -> Incident:
    """Undoes finalize_incident — lifts the write lock so the facilitator
    can correct something after archiving. Deliberate manual action, not
    exposed anywhere except the Definitieve AAR page."""
    incident.status = IncidentStatus.IN_REVIEW
    session.commit()
    session.refresh(incident)
    return incident
