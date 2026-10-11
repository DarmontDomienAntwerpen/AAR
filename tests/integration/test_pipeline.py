from aar.analysis.pipeline import run_analysis
from aar.llm.mock import MockLLMProvider
from aar.models import (
    AnalysisRunStatus,
    CommanderReport,
    DiscussionPoint,
    Improvement,
    Incident,
    IncidentEvent,
    IncidentStatus,
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
            "situation": "Bij aankomst was er zware rookontwikkeling op de eerste verdieping.",
            "other": "Ik ging ervan uit dat de achterzijde al gecontroleerd was door P21.",
            "evaluation": "De coördinatie tussen de eenheden verliep vlot.",
        },
    )
    _make_report(
        session,
        sample_incident,
        "P21",
        {
            "situation": "Rook was zichtbaar aan de achterzijde van het pand.",
            "other": "Volgens mij was er niemand meer binnen op dat moment.",
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
    # Not asserting on Lesson count here: a lesson clustering only 1
    # discussion point is deliberately suppressed (near-duplicate of that
    # point — see run_lessons), so with this fixture's small, thematically
    # scattered discussion points, 0 lessons can be the correct outcome.
    # Improvements still get created either way (see test_lessons.py).
    assert session.query(Improvement).filter_by(incident_id=sample_incident.id).count() > 0

    # Absolute time rule: no event may have a fabricated exact time (no
    # matching dispatch data was provided in this fixture at all).
    for event in session.query(IncidentEvent).filter_by(incident_id=sample_incident.id).all():
        assert event.exact_time is None


class _FailsOnFindingsProvider(MockLLMProvider):
    """Behaves like the real mock for every stage except findings, where it
    always returns invalid JSON — simulates a provider/validation failure
    partway through the pipeline."""

    def _complete(self, *, system_prompt, user_prompt, schema, attempt, previous_error):
        if schema.get("title") == "FindingsOutput":
            return "not valid json"
        return super()._complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=schema,
            attempt=attempt,
            previous_error=previous_error,
        )


def test_pipeline_records_error_and_preserves_earlier_stage_progress_on_mid_run_failure(
    session, sample_incident
):
    _make_report(
        session, sample_incident, "P12", {"situation": "Bij aankomst was er rookontwikkeling."}
    )

    run = run_analysis(session, sample_incident, _FailsOnFindingsProvider())

    assert run.status == AnalysisRunStatus.ERROR
    assert run.stage_reached == "findings"
    assert run.error_message

    incident = session.get(Incident, sample_incident.id)
    assert incident.status != IncidentStatus.ANALYZED  # never marked as successfully analysed

    # Extraction and reconstruction (earlier stages) already committed their
    # work before the failure — a partial pipeline run isn't silently discarded.
    assert session.query(Observation).filter_by(incident_id=sample_incident.id).count() > 0
    assert session.query(IncidentEvent).filter_by(incident_id=sample_incident.id).count() > 0
    # But nothing from the failed findings stage exists.
    assert session.query(DiscussionPoint).filter_by(incident_id=sample_incident.id).count() == 0


def test_pipeline_fails_cleanly_with_no_reports(session, sample_incident):
    run = run_analysis(session, sample_incident, MockLLMProvider())
    assert run.status == AnalysisRunStatus.ERROR
    assert "bevelvoerdersverslagen" in run.error_message.lower()

    incident = session.get(Incident, sample_incident.id)
    assert incident.status != IncidentStatus.ANALYZED


def test_pipeline_rerun_does_not_duplicate_events(session, sample_incident):
    _make_report(
        session,
        sample_incident,
        "P12",
        {"situation": "Bij aankomst was er zware rookontwikkeling."},
    )
    run_analysis(session, sample_incident, MockLLMProvider())
    first_event_count = session.query(IncidentEvent).filter_by(incident_id=sample_incident.id).count()

    run_analysis(session, sample_incident, MockLLMProvider())
    second_event_count = session.query(IncidentEvent).filter_by(incident_id=sample_incident.id).count()

    assert first_event_count == second_event_count
