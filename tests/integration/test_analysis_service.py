from aar.config.settings import get_settings
from aar.models import AnalysisRunStatus, CommanderReport, SourceDocument, SourceDocumentType
from aar.services.analysis_service import get_latest_analysis_run, trigger_analysis


def test_trigger_analysis_uses_default_mock_provider(session, sample_incident, monkeypatch):
    # delenv alone isn't enough to isolate this from a real .env file: with
    # the var absent from os.environ, get_settings()'s load_dotenv(...,
    # override=False) call re-populates it straight from .env (real
    # deployments set AAR_LLM_PROVIDER=anthropic there) — silently making
    # this test hit the real Anthropic API. Force "mock" explicitly instead.
    monkeypatch.setenv("AAR_LLM_PROVIDER", "mock")
    get_settings.cache_clear()
    doc = SourceDocument(
        incident_id=sample_incident.id,
        doc_type=SourceDocumentType.COMMANDER_REPORT,
        original_filename="p12.docx",
        stored_path="/tmp/p12.docx",
        content_hash="h1",
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    report = CommanderReport(
        incident_id=sample_incident.id,
        source_document_id=doc.id,
        callsign="P12",
        surname="Janssens",
        raw_sections={"observations": "Rook zichtbaar bij aankomst."},
    )
    session.add(report)
    session.commit()

    try:
        run = trigger_analysis(session, sample_incident)
        assert run.status == AnalysisRunStatus.SUCCESS

        latest = get_latest_analysis_run(session, sample_incident)
        assert latest.id == run.id
    finally:
        get_settings.cache_clear()
