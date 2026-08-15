import datetime as dt

from aar.models import IncidentType
from aar.schemas.forms import IncidentCreateForm
from aar.services.incident_service import create_incident, list_incidents


def test_create_and_list_incident(session):
    form = IncidentCreateForm(
        date=dt.date(2026, 2, 1),
        location="Kerkstraat 5, Gent",
        incident_type=IncidentType.WATERONGEVAL,
        description="Fictief waterongeval voor test.",
    )
    incident = create_incident(session, form)
    assert incident.id is not None

    results = list_incidents(session)
    assert len(results) == 1
    assert results[0].location == "Kerkstraat 5, Gent"


def test_search_filters_by_text(session):
    form1 = IncidentCreateForm(
        date=dt.date(2026, 2, 1), location="Kerkstraat 5, Gent", incident_type=IncidentType.BRAND, description=""
    )
    form2 = IncidentCreateForm(
        date=dt.date(2026, 2, 2),
        location="Havenweg 1, Antwerpen",
        incident_type=IncidentType.BRAND,
        description="",
    )
    create_incident(session, form1)
    create_incident(session, form2)

    results = list_incidents(session, search_text="Antwerpen")
    assert len(results) == 1
    assert results[0].location == "Havenweg 1, Antwerpen"


def test_filter_by_incident_type(session):
    form1 = IncidentCreateForm(
        date=dt.date(2026, 2, 1), location="A", incident_type=IncidentType.BRAND, description=""
    )
    form2 = IncidentCreateForm(
        date=dt.date(2026, 2, 2), location="B", incident_type=IncidentType.WATERONGEVAL, description=""
    )
    create_incident(session, form1)
    create_incident(session, form2)

    results = list_incidents(session, incident_type=IncidentType.WATERONGEVAL)
    assert len(results) == 1
    assert results[0].location == "B"
