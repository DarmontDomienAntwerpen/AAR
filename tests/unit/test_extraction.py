from aar.analysis.extraction import run_extraction
from aar.llm.mock import MockLLMProvider
from aar.models import CommanderReport, Observation, ObservationType, ParseStatus, SourceDocument, SourceDocumentType


def _make_report(session, incident, sections: dict) -> CommanderReport:
    doc = SourceDocument(
        incident_id=incident.id,
        doc_type=SourceDocumentType.COMMANDER_REPORT,
        original_filename="p12.docx",
        stored_path="/tmp/p12.docx",
        content_hash="hash1",
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)

    report = CommanderReport(
        incident_id=incident.id,
        source_document_id=doc.id,
        callsign="P12",
        unit_name="1ste Hulpcentrum",
        rank="Adjudant",
        surname="Janssens",
        raw_sections=sections,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def test_run_extraction_persists_observations(session, sample_incident):
    report = _make_report(
        session,
        sample_incident,
        {
            "observations": "Bij aankomst was er zware rookontwikkeling op de eerste verdieping.",
            "doubts_assumptions": "Ik ging ervan uit dat de achterzijde al gecontroleerd was.",
        },
    )
    result = run_extraction(session, report, MockLLMProvider())

    assert len(result.items) >= 2
    observations = session.query(Observation).filter_by(commander_report_id=report.id).all()
    assert len(observations) == len(result.items)
    assert all(o.attributed_to == report.display_name for o in observations)
    assert any(o.observation_type == ObservationType.ASSUMPTION for o in observations)

    report_reloaded = session.get(CommanderReport, report.id)
    assert report_reloaded.extraction_status == ParseStatus.PARSED


def test_run_extraction_is_idempotent_on_rerun(session, sample_incident):
    report = _make_report(session, sample_incident, {"observations": "Rook zichtbaar."})
    run_extraction(session, report, MockLLMProvider())
    first_count = session.query(Observation).filter_by(commander_report_id=report.id).count()

    run_extraction(session, report, MockLLMProvider())
    second_count = session.query(Observation).filter_by(commander_report_id=report.id).count()

    assert first_count == second_count  # no duplicate accumulation on rerun


def test_run_extraction_skips_empty_sections(session, sample_incident):
    report = _make_report(session, sample_incident, {"observations": "", "narrative": "   "})
    result = run_extraction(session, report, MockLLMProvider())
    assert result.items == []
