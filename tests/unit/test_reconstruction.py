import datetime as dt

from aar.analysis.reconstruction import run_reconstruction
from aar.llm.mock import MockLLMProvider
from aar.models import (
    CommanderReport,
    CreatedBy,
    IncidentEvent,
    Observation,
    ObservationCategory,
    ObservationType,
    SourceDocument,
    SourceDocumentType,
)


def _make_report(session, incident, callsign) -> CommanderReport:
    doc = SourceDocument(
        incident_id=incident.id,
        doc_type=SourceDocumentType.COMMANDER_REPORT,
        original_filename=f"{callsign}.docx",
        stored_path=f"/tmp/{callsign}.docx",
        content_hash=f"hash-{callsign}",
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    report = CommanderReport(
        incident_id=incident.id,
        source_document_id=doc.id,
        callsign=callsign,
        unit_name="Eenheid",
        rank="Adjudant",
        surname="Janssens",
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def _add_observation(session, incident, report, content, category, obs_type=ObservationType.HUMAN_OBSERVATION):
    obs = Observation(
        incident_id=incident.id,
        commander_report_id=report.id,
        observation_type=obs_type,
        category=category,
        content=content,
        source_passage=content,
        attributed_to=report.display_name,
        created_by=CreatedBy.AI,
    )
    session.add(obs)
    session.commit()
    session.refresh(obs)
    return obs


def test_reconstruction_groups_observations_into_events(session, sample_incident):
    r1 = _make_report(session, sample_incident, "P12")
    r2 = _make_report(session, sample_incident, "P21")
    _add_observation(session, sample_incident, r1, "Zware rook zichtbaar bij aankomst.", ObservationCategory.OBSERVATION)
    _add_observation(session, sample_incident, r2, "Rook aan de achterzijde van het pand.", ObservationCategory.OBSERVATION)

    result = run_reconstruction(session, sample_incident, MockLLMProvider())
    assert len(result.events) >= 1

    events = session.query(IncidentEvent).filter_by(incident_id=sample_incident.id).all()
    assert len(events) == len(result.events)
    for event in events:
        assert event.exact_time is None  # reconstruction alone never sets exact time


def test_reconstruction_rerun_replaces_ai_events_but_keeps_human_added(session, sample_incident):
    r1 = _make_report(session, sample_incident, "P12")
    _add_observation(session, sample_incident, r1, "Zware rook zichtbaar.", ObservationCategory.OBSERVATION)

    run_reconstruction(session, sample_incident, MockLLMProvider())
    ai_event_count_first = (
        session.query(IncidentEvent).filter_by(incident_id=sample_incident.id, is_human_added=False).count()
    )

    manual_event = IncidentEvent(
        incident_id=sample_incident.id, title="Manueel toegevoegd moment", order_index=99, is_human_added=True
    )
    session.add(manual_event)
    session.commit()

    run_reconstruction(session, sample_incident, MockLLMProvider())

    ai_event_count_second = (
        session.query(IncidentEvent).filter_by(incident_id=sample_incident.id, is_human_added=False).count()
    )
    assert ai_event_count_second == ai_event_count_first  # replaced, not duplicated

    still_there = session.get(IncidentEvent, manual_event.id)
    assert still_there is not None
    assert still_there.title == "Manueel toegevoegd moment"


def test_reconstruction_excludes_conflict_and_ai_observation_types_from_input(session, sample_incident):
    r1 = _make_report(session, sample_incident, "P12")
    _add_observation(
        session, sample_incident, r1, "Dit is al een AI-observatie.", ObservationCategory.OTHER, ObservationType.AI_OBSERVATION
    )
    result = run_reconstruction(session, sample_incident, MockLLMProvider())
    assert result.events == []
