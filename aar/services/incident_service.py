"""Deterministic CRUD/search for incidents. No business logic belongs in the
Streamlit layer — pages call these functions."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from aar.models import Incident, IncidentStatus, IncidentType
from aar.schemas.forms import IncidentCreateForm


def create_incident(session: Session, form: IncidentCreateForm) -> Incident:
    incident = Incident(
        date=form.date,
        location=form.location.strip(),
        incident_type=form.incident_type,
        description=form.description.strip(),
        status=IncidentStatus.DRAFT,
    )
    session.add(incident)
    session.commit()
    session.refresh(incident)
    return incident


def get_incident(session: Session, incident_id: int) -> Incident | None:
    return session.get(Incident, incident_id)


def list_incidents(
    session: Session,
    *,
    search_text: str | None = None,
    incident_type: IncidentType | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
) -> list[Incident]:
    stmt = select(Incident).order_by(Incident.date.desc(), Incident.id.desc())
    if incident_type is not None:
        stmt = stmt.where(Incident.incident_type == incident_type)
    if date_from is not None:
        stmt = stmt.where(Incident.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Incident.date <= date_to)
    incidents = list(session.execute(stmt).scalars().all())

    if search_text:
        needle = search_text.strip().lower()
        incidents = [
            inc
            for inc in incidents
            if needle in inc.location.lower()
            or needle in inc.description.lower()
            or needle in inc.situation_summary.lower()
        ]
    return incidents


def update_status(session: Session, incident: Incident, status: IncidentStatus) -> Incident:
    incident.status = status
    session.commit()
    session.refresh(incident)
    return incident
