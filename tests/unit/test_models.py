import datetime as dt

from aar.models import (
    CommanderReport,
    IncidentEvent,
    Observation,
    ObservationType,
    SourceDocument,
    SourceDocumentType,
)


def test_incident_created(sample_incident):
    assert sample_incident.id is not None
    assert sample_incident.location.startswith("Teststraat")


def test_commander_report_display_name(session, sample_incident):
    doc = SourceDocument(
        incident_id=sample_incident.id,
        doc_type=SourceDocumentType.COMMANDER_REPORT,
        original_filename="p12.docx",
        stored_path="/tmp/p12.docx",
        content_hash="abc123",
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)

    report = CommanderReport(
        incident_id=sample_incident.id,
        source_document_id=doc.id,
        callsign="P12",
        unit_name="1ste Hulpcentrum",
        rank="Adjudant",
        surname="Janssens",
    )
    session.add(report)
    session.commit()
    session.refresh(report)

    assert report.display_name == "P12 (1ste Hulpcentrum) — Adjudant Janssens"


def test_observation_and_event_roundtrip(session, sample_incident):
    obs = Observation(
        incident_id=sample_incident.id,
        observation_type=ObservationType.ASSUMPTION,
        content="Commander assumed the rear was already checked.",
        source_passage="Ik ging ervan uit dat de achterzijde al gecontroleerd was.",
        attributed_to="P12 (1ste Hulpcentrum) — Adjudant Janssens",
    )
    session.add(obs)
    session.commit()
    session.refresh(obs)

    event = IncidentEvent(
        incident_id=sample_incident.id,
        title="Controle achterzijde pand",
        order_index=1,
        observation_ids=[obs.id],
    )
    session.add(event)
    session.commit()
    session.refresh(event)

    assert event.exact_time is None
    assert obs.id in event.observation_ids


def test_event_without_exact_time_stays_unset(session, sample_incident):
    """Regression guard for the absolute-time rule (spec §22): an event with
    no supporting dispatch record must never end up with a fabricated time."""
    event = IncidentEvent(
        incident_id=sample_incident.id,
        title="Opstart primaire zoekactie",
        order_index=2,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    assert event.exact_time is None
    assert event.exact_time_source is None
