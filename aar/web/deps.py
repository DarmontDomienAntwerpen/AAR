"""FastAPI dependencies: one DB session per request, always closed after."""
from __future__ import annotations

from typing import Iterator

from fastapi import HTTPException
from sqlalchemy.orm import Session

from aar.db.session import get_session
from aar.models import Incident
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
