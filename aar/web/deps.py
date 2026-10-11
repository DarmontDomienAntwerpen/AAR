"""FastAPI dependencies: one DB session per request, always closed after."""
from __future__ import annotations

from typing import Iterator

from fastapi import HTTPException
from sqlalchemy.orm import Session

from aar.db.session import get_session
from aar.models import Incident
from aar.models.enums import IncidentStatus
from aar.services.incident_service import get_incident


def get_db() -> Iterator[Session]:
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def incident_or_404(session: Session, incident_id: int) -> Incident:
    incident = get_incident(session, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident niet gevonden")
    return incident


class IncidentFinalizedError(HTTPException):
    """Raised by mutating routes when the incident has been marked
    afgerond — a finalized AAR is a locked archive record, see
    aar_service.finalize_incident."""

    def __init__(self) -> None:
        super().__init__(
            status_code=423,
            detail="Deze AAR is afgerond en gearchiveerd — aanpassingen zijn niet meer mogelijk.",
        )


def assert_writable(incident: Incident) -> None:
    if incident.status == IncidentStatus.FINALIZED:
        raise IncidentFinalizedError()


def writable_incident_or_404(session: Session, incident_id: int) -> Incident:
    """Like `incident_or_404`, but also rejects any incident that has
    already been finalized — use this in every mutating (POST) route."""
    incident = incident_or_404(session, incident_id)
    assert_writable(incident)
    return incident
