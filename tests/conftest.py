import datetime as dt

import pytest

from aar.db.session import get_session, init_db
from aar.models import Incident, IncidentType


@pytest.fixture()
def engine():
    """Fresh isolated in-memory SQLite engine per test — no shared state."""
    from sqlalchemy import create_engine

    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    init_db(eng)
    return eng


@pytest.fixture()
def session(engine):
    sess = get_session(engine)
    try:
        yield sess
    finally:
        sess.close()


@pytest.fixture()
def sample_incident(session):
    incident = Incident(
        date=dt.date(2026, 3, 4),
        location="Teststraat 12, Antwerpen",
        incident_type=IncidentType.BRAND,
        description="Fictieve testincident voor automatische tests.",
    )
    session.add(incident)
    session.commit()
    session.refresh(incident)
    return incident
