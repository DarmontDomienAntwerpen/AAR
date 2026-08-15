from aar.analysis.pipeline import run_analysis
from aar.llm.mock import MockLLMProvider
from aar.models import (
    AnalysisRunStatus,
    CommanderReport,
    DiscussionPoint,
    Incident,
    IncidentEvent,
    IncidentStatus,
    Lesson,
    Observation,
    SourceDocument,
    SourceDocumentType,
)


def _make_report(session, incident, callsign, sections) -> CommanderReport:
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
        surname="Peeters",
        raw_sections=sections,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def test_full_pipeline_end_to_end(session, sample_incident):
    _make_report(
        session,
        sample_incident,
        "P12",
        {
            "observations": "Bij aankomst was er zware rookontwikkeling op de eerste verdieping.",
            "doubts_assumptions": "Ik ging ervan uit dat de achterzijde al gecontroleerd was door P21.",
            "went_well": "De coördinatie tussen de eenheden verliep vlot.",
        },
    )
    _make_report(
        session,
        sample_incident,
        "P21",
        {
            "observations": "Rook was zichtbaar aan de achterzijde van het pand.",
            "doubts_assumptions": "Volgens mij was er niemand meer binnen op dat moment.",
        },
    )

    run = run_analysis(session, sample_incident, MockLLMProvider())

    assert run.status == AnalysisRunStatus.SUCCESS
    assert run.stage_reached == "done"

    incident = session.get(Incident, sample_incident.id)
    assert incident.status == IncidentStatus.ANALYZED

    assert session.query(Observation).filter_by(incident_id=sample_incident.id).count() > 0
    assert session.query(IncidentEvent).filter_by(incident_id=sample_incident.id).count() > 0
    assert session.query(DiscussionPoint).filter_by(incident_id=sample_incident.id).count() > 0
    assert session.query(Lesson).filter_by(incident_id=sample_incident.id).count() > 0

    # Absolute time rule: no event may have a fabricated exact time (no
    # matching dispatch data was provided in this fixture at all).
    for event in session.query(IncidentEvent).filter_by(incident_id=sample_incident.id).all():
        assert event.exact_time is None


def test_pipeline_fails_cleanly_with_no_reports(session, sample_incident):
    run = run_analysis(session, sample_incident, MockLLMProvider())
    assert run.status == AnalysisRunStatus.ERROR
    assert "commandantenverslagen" in run.error_message.lower()

    incident = session.get(Incident, sample_incident.id)
    assert incident.status != IncidentStatus.ANALYZED


def test_pipeline_rerun_does_not_duplicate_events(session, sample_incident):
    _make_report(
        session,
        sample_incident,
        "P12",
        {"observations": "Bij aankomst was er zware rookontwikkeling."},
    )
    run_analysis(session, sample_incident, MockLLMProvider())
    first_event_count = session.query(IncidentEvent).filter_by(incident_id=sample_incident.id).count()

    run_analysis(session, sample_incident, MockLLMProvider())
    second_event_count = session.query(IncidentEvent).filter_by(incident_id=sample_incident.id).count()

    assert first_event_count == second_event_count
