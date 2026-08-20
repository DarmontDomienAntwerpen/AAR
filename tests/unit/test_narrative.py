from aar.analysis.narrative import run_narrative
from aar.llm.mock import MockLLMProvider
from aar.models import (
    CommanderReport,
    EventPerspective,
    IncidentEvent,
    Observation,
    SourceDocument,
    SourceDocumentType,
)
from aar.models.enums import CreatedBy, ObservationCategory, ObservationType


def _make_report(session, incident) -> CommanderReport:
    doc = SourceDocument(
        incident_id=incident.id,
        doc_type=SourceDocumentType.COMMANDER_REPORT,
        original_filename="P12.docx",
        stored_path="/tmp/P12.docx",
        content_hash="hash-P12",
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    report = CommanderReport(
        incident_id=incident.id,
        source_document_id=doc.id,
        callsign="P12",
        unit_name="Eenheid",
        rank="Adjudant",
        surname="Janssens",
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def test_run_narrative_persists_to_incident(session, sample_incident):
    """Only decision-relevant (DECISION/RESULT/OBJECTIVE/WENT_WELL/
    WENT_LESS_WELL) moments feed the narrative — same crucial-category
    filter as the deterministic fallback, so the summary stays short instead
    of dumping every category (spec discussion: "veel te lang")."""
    report = _make_report(session, sample_incident)
    obs = Observation(
        incident_id=sample_incident.id,
        commander_report_id=report.id,
        observation_type=ObservationType.HUMAN_OBSERVATION,
        category=ObservationCategory.DECISION,
        content="Interne aanval ingezet.",
        source_passage="Interne aanval ingezet.",
        created_by=CreatedBy.AI,
    )
    session.add(obs)
    session.commit()

    event = IncidentEvent(
        incident_id=sample_incident.id,
        title="Beslissing interne aanval",
        order_index=0,
        ai_summary="P12 beslist tot interne aanval.",
        observation_ids=[obs.id],
    )
    session.add(event)
    session.commit()
    session.add(
        EventPerspective(
            event_id=event.id,
            commander_report_id=report.id,
            commander_display_name="P12 — Adjudant Janssens",
            perspective_text="Ik besliste om een interne aanval in te zetten.",
        )
    )
    session.commit()

    result = run_narrative(session, sample_incident, MockLLMProvider())

    assert result.narrative
    assert sample_incident.ai_situation_narrative == result.narrative
    assert "Adjudant Janssens" in sample_incident.ai_situation_narrative


def test_run_narrative_excludes_non_crucial_events(session, sample_incident):
    report = _make_report(session, sample_incident)
    obs = Observation(
        incident_id=sample_incident.id,
        commander_report_id=report.id,
        observation_type=ObservationType.HUMAN_OBSERVATION,
        category=ObservationCategory.OTHER,  # not a crucial category
        content="Geparkeerde auto voor de deur.",
        source_passage="Geparkeerde auto voor de deur.",
        created_by=CreatedBy.AI,
    )
    session.add(obs)
    session.commit()
    event = IncidentEvent(
        incident_id=sample_incident.id,
        title="Trivia bij aankomst",
        order_index=0,
        ai_summary="Niet relevant.",
        observation_ids=[obs.id],
    )
    session.add(event)
    session.commit()

    result = run_narrative(session, sample_incident, MockLLMProvider())
    assert "Geen incidentmomenten" in result.narrative


def test_run_narrative_with_no_events_returns_explicit_placeholder(session, sample_incident):
    result = run_narrative(session, sample_incident, MockLLMProvider())
    assert "Geen incidentmomenten" in result.narrative
