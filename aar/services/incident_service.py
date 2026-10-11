"""Deterministic CRUD/search for incidents. No business logic belongs in the
Streamlit layer — pages call these functions."""
from __future__ import annotations

import datetime as dt
import shutil

from sqlalchemy import select
from sqlalchemy.orm import Session

from aar.analysis.cleanup import run_cleanup
from aar.config.settings import get_settings
from aar.llm.base import LLMProvider
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


def update_incident_details(
    session: Session,
    incident: Incident,
    *,
    date: dt.date,
    location: str,
    incident_type: IncidentType,
    description: str,
) -> Incident:
    """Facilitator correction of the basic incident record — e.g. a typo in
    the address caught after creation. Deterministic, no LLM involved."""
    incident.date = date
    incident.location = location.strip()
    incident.incident_type = incident_type
    incident.description = description.strip()
    session.commit()
    session.refresh(incident)
    return incident


def update_initial_call_notes(session: Session, incident: Incident, text: str) -> Incident:
    """Facilitator's free-text notes on what was known from the initial
    dispatch call — always human-authored, never touched by automatic
    (re-)analysis (only by the explicit cleanup action below, on request)."""
    incident.initial_call_notes = text.strip()
    session.commit()
    session.refresh(incident)
    return incident


def clean_up_description(session: Session, incident: Incident, provider: LLMProvider) -> Incident:
    """On-demand proofreading pass on the incident description — typos and
    structure only, triggered explicitly by the facilitator, never as part
    of the automatic analysis pipeline."""
    if incident.description.strip():
        incident.description = run_cleanup(provider, incident.description).strip()
        session.commit()
        session.refresh(incident)
    return incident


def clean_up_initial_call_notes(session: Session, incident: Incident, provider: LLMProvider) -> Incident:
    """Same on-demand cleanup, for the initial-call notes."""
    if incident.initial_call_notes.strip():
        incident.initial_call_notes = run_cleanup(provider, incident.initial_call_notes).strip()
        session.commit()
        session.refresh(incident)
    return incident


def delete_incident(session: Session, incident: Incident) -> None:
    """Permanently removes an incident and everything under it (reports,
    observations, events, findings, uploaded source files) — cascade is
    configured on every Incident relationship, so deleting the row deletes
    the lot. Also removes the incident's upload directory from disk so no
    orphaned files are left behind."""
    incident_id = incident.id
    session.delete(incident)
    session.commit()

    uploads_dir = get_settings().project_root / "data" / "uploads" / str(incident_id)
    shutil.rmtree(uploads_dir, ignore_errors=True)
