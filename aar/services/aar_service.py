"""CRUD + human-in-the-loop editing for the interactive AAR (spec §48).

Every mutation here is deterministic Python — no LLM involved. The
facilitator is the final authority: edits/deletes are immediate and no
AI-vs-human audit trail is kept (spec §50), only current validated content.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from aar.models import (
    DiscussionPoint,
    EventPerspective,
    HumanCorrection,
    Improvement,
    Incident,
    IncidentEvent,
    IncidentStatus,
    Lesson,
    Observation,
    PositiveFinding,
)

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


def delete_discussion_point(session: Session, dp: DiscussionPoint) -> None:
    session.delete(dp)
    session.commit()


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
    events = get_events(session, incident)
    lines = [e.ai_summary for e in events if e.ai_summary]
    return "\n".join(lines)


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
