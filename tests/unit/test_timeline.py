import datetime as dt

from aar.analysis.timeline import enrich_with_dispatch_times
from aar.models import DispatchRecord, IncidentEvent, SourceDocument, SourceDocumentType


def _make_dispatch_doc(session, incident) -> SourceDocument:
    doc = SourceDocument(
        incident_id=incident.id,
        doc_type=SourceDocumentType.DISPATCH_EXCEL,
        original_filename="dispatch.xlsx",
        stored_path="/tmp/dispatch.xlsx",
        content_hash="dispatch-hash",
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    return doc


def test_enrich_attaches_time_on_clear_match(session, sample_incident):
    doc = _make_dispatch_doc(session, sample_incident)
    record = DispatchRecord(
        incident_id=sample_incident.id,
        source_document_id=doc.id,
        row_index=2,
        timestamp=dt.datetime(2026, 3, 4, 14, 7),
        event_description="Eerste voertuig ter plaatse escalatie brand pand",
        unit="P12",
        is_valid=True,
    )
    session.add(record)
    event = IncidentEvent(
        incident_id=sample_incident.id,
        title="Escalatie brand pand",
        order_index=0,
        ai_summary="Escalatie van de brand in het pand gemeld door meerdere commandanten.",
    )
    session.add(event)
    session.commit()

    enriched = enrich_with_dispatch_times(session, sample_incident)
    session.refresh(event)

    assert enriched == 1
    assert event.exact_time == dt.datetime(2026, 3, 4, 14, 7)
    assert event.exact_time_source == f"dispatch_record:{record.id}"


def test_enrich_leaves_unset_when_no_overlap(session, sample_incident):
    doc = _make_dispatch_doc(session, sample_incident)
    session.add(
        DispatchRecord(
            incident_id=sample_incident.id,
            source_document_id=doc.id,
            row_index=2,
            timestamp=dt.datetime(2026, 3, 4, 14, 7),
            event_description="Volledig ongerelateerde melding brandweerkazerne",
            is_valid=True,
        )
    )
    event = IncidentEvent(
        incident_id=sample_incident.id,
        title="Primaire zoekactie",
        order_index=0,
        ai_summary="Zoektocht naar slachtoffers op de bovenverdieping.",
    )
    session.add(event)
    session.commit()

    enriched = enrich_with_dispatch_times(session, sample_incident)
    session.refresh(event)

    assert enriched == 0
    assert event.exact_time is None
    assert event.exact_time_source is None


def test_enrich_leaves_unset_on_ambiguous_tie(session, sample_incident):
    doc = _make_dispatch_doc(session, sample_incident)
    session.add_all(
        [
            DispatchRecord(
                incident_id=sample_incident.id,
                source_document_id=doc.id,
                row_index=2,
                timestamp=dt.datetime(2026, 3, 4, 14, 7),
                event_description="Escalatie brand pand gemeld",
                is_valid=True,
            ),
            DispatchRecord(
                incident_id=sample_incident.id,
                source_document_id=doc.id,
                row_index=3,
                timestamp=dt.datetime(2026, 3, 4, 14, 25),
                event_description="Escalatie brand pand bevestigd",
                is_valid=True,
            ),
        ]
    )
    event = IncidentEvent(
        incident_id=sample_incident.id,
        title="Escalatie brand pand",
        order_index=0,
        ai_summary="Escalatie van de brand in het pand.",
    )
    session.add(event)
    session.commit()

    enriched = enrich_with_dispatch_times(session, sample_incident)
    session.refresh(event)

    assert enriched == 0
    assert event.exact_time is None


def test_enrich_ignores_generic_overlap_in_long_ai_summary(session, sample_incident):
    """Regression guard: a long, richly-worded ai_summary (real quoted report
    content, as the mock/a real LLM would produce) must not cause a match on
    its own just because generic incident vocabulary happens to overlap with
    a dispatch row — matching is title-only precisely to prevent this."""
    doc = _make_dispatch_doc(session, sample_incident)
    session.add(
        DispatchRecord(
            incident_id=sample_incident.id,
            source_document_id=doc.id,
            row_index=2,
            timestamp=dt.datetime(2026, 3, 4, 14, 19),
            event_description="Slachtoffer aangetroffen eerste verdieping",
            is_valid=True,
        )
    )
    event = IncidentEvent(
        incident_id=sample_incident.id,
        title="Wat ging minder goed",
        order_index=0,
        ai_summary=(
            "De controle van de eerste verdieping gebeurde later dan gewenst. "
            "Er was aanvankelijk onvoldoende zicht op de toestand van de eerste "
            "verdieping vanaf de buitenzijde, en het slachtoffer werd daardoor "
            "pas laat aangetroffen door de zoekploeg."
        ),
    )
    session.add(event)
    session.commit()

    enriched = enrich_with_dispatch_times(session, sample_incident)
    session.refresh(event)

    assert enriched == 0
    assert event.exact_time is None


def test_enrich_skips_invalid_dispatch_records(session, sample_incident):
    doc = _make_dispatch_doc(session, sample_incident)
    session.add(
        DispatchRecord(
            incident_id=sample_incident.id,
            source_document_id=doc.id,
            row_index=2,
            timestamp=None,
            event_description="Escalatie brand pand gemeld",
            is_valid=False,
            validation_error="Ongeldig tijdstip",
        )
    )
    event = IncidentEvent(
        incident_id=sample_incident.id, title="Escalatie", order_index=0, ai_summary="Escalatie van de brand."
    )
    session.add(event)
    session.commit()

    enriched = enrich_with_dispatch_times(session, sample_incident)
    assert enriched == 0
