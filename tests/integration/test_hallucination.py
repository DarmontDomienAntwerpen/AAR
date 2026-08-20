"""Spec §65 — adversarial hallucination tests, high priority. Each test
supplies input that deliberately lacks a piece of information and checks the
pipeline output never fabricates it. Uses the mock provider: since the mock
never paraphrases (content is always copied verbatim from the source
sentence — see aar/llm/mock.py), these are largely structural guarantees,
but are written explicitly so a future change that adds paraphrasing/
generation to the mock (or a bug in a real provider's prompt) gets caught
here rather than discovered in production.
"""
from __future__ import annotations

from aar.analysis.pipeline import run_analysis
from aar.llm.mock import MockLLMProvider
from aar.models import (
    CommanderReport,
    DiscussionPoint,
    IncidentEvent,
    Lesson,
    Observation,
    PositiveFinding,
    SourceDocument,
    SourceDocumentType,
)

_CAUSE_WORDS = ["kortsluiting", "brandstichting", "oorzaak", "ontstaan door"]
_VICTIM_WORDS = ["slachtoffer", "gewonde", "overleden", "vermist"]


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


def _all_generated_text(session, incident) -> str:
    parts = []
    parts += [o.content for o in session.query(Observation).filter_by(incident_id=incident.id).all()]
    parts += [e.ai_summary for e in session.query(IncidentEvent).filter_by(incident_id=incident.id).all()]
    parts += [
        dp.title + " " + dp.description
        for dp in session.query(DiscussionPoint).filter_by(incident_id=incident.id).all()
    ]
    parts += [
        pf.title + " " + pf.description
        for pf in session.query(PositiveFinding).filter_by(incident_id=incident.id).all()
    ]
    parts += [
        l.title + " " + l.description for l in session.query(Lesson).filter_by(incident_id=incident.id).all()
    ]
    return " ".join(parts).lower()


def test_no_cause_mentioned_none_is_fabricated(session, sample_incident):
    _make_report(
        session,
        sample_incident,
        "P12",
        {
            "situation": "Bij aankomst was er rookontwikkeling zichtbaar aan de voorzijde.",
            "actions": "We zijn naar binnen gegaan en hebben de brand geblust.",
        },
    )
    run = run_analysis(session, sample_incident, MockLLMProvider())
    assert run.status.value == "success"

    text = _all_generated_text(session, sample_incident)
    for word in _CAUSE_WORDS:
        assert word not in text, f"Fabricated cause mention found: {word!r}"


def test_no_victim_mentioned_none_is_invented(session, sample_incident):
    _make_report(
        session,
        sample_incident,
        "P12",
        {
            "situation": "Bij aankomst was er rookontwikkeling zichtbaar op het gelijkvloers.",
            "actions": "De brand werd snel onder controle gebracht zonder verdere bijzonderheden.",
            "result": "Het pand werd nadien geventileerd.",
        },
    )
    run = run_analysis(session, sample_incident, MockLLMProvider())
    assert run.status.value == "success"

    text = _all_generated_text(session, sample_incident)
    for word in _VICTIM_WORDS:
        assert word not in text, f"Fabricated victim mention found: {word!r}"


def test_conflicting_accounts_both_preserved_not_silently_resolved(session, sample_incident):
    r1 = _make_report(
        session, sample_incident, "P12",
        {"actions": "Ik gaf de opdracht aan P21 om de achterzijde te controleren."},
    )
    r2 = _make_report(
        session, sample_incident, "P21",
        {"actions": "Ik heb geen opdracht ontvangen om de achterzijde te controleren."},
    )
    run_analysis(session, sample_incident, MockLLMProvider())

    obs_r1 = session.query(Observation).filter_by(commander_report_id=r1.id).all()
    obs_r2 = session.query(Observation).filter_by(commander_report_id=r2.id).all()
    assert any("gaf de opdracht" in o.content for o in obs_r1)
    assert any("geen opdracht ontvangen" in o.content for o in obs_r2)
    # Neither account was dropped or silently merged into the other.
    assert obs_r1 and obs_r2


def test_no_narrative_time_means_no_events_get_an_exact_time(session, sample_incident):
    _make_report(
        session,
        sample_incident,
        "P12",
        {
            "situation": "Rook was zichtbaar bij aankomst.",
            "decision": "We besloten een interne aanval in te zetten.",
            "result": "De brand werd geblust.",
        },
    )
    run_analysis(session, sample_incident, MockLLMProvider())  # no dispatch data supplied at all

    events = session.query(IncidentEvent).filter_by(incident_id=sample_incident.id).all()
    assert events
    assert all(e.exact_time is None for e in events)
    assert all(e.exact_time_source is None for e in events)
