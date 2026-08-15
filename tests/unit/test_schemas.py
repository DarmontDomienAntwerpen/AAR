import datetime as dt

import pytest
from pydantic import ValidationError

from aar.models.enums import ObservationType
from aar.schemas.extraction import ExtractedItem, ReportExtraction
from aar.schemas.forms import IncidentCreateForm
from aar.schemas.ingestion import CommanderIdentity, DispatchRecordRaw
from aar.schemas.reconstruction import ReconstructedEvent


def test_extracted_item_requires_source_passage():
    with pytest.raises(ValidationError):
        ExtractedItem(content="Something happened", source_passage="", observation_type=ObservationType.FACT)


def test_extracted_item_valid():
    item = ExtractedItem(
        content="Commander assumed the rear was checked",
        source_passage="Ik ging ervan uit dat de achterzijde gecontroleerd was",
        observation_type=ObservationType.ASSUMPTION,
    )
    assert item.observation_type == ObservationType.ASSUMPTION


def test_report_extraction_roundtrip():
    extraction = ReportExtraction(
        commander_report_id=1,
        items=[
            ExtractedItem(
                content="Heavy smoke on arrival",
                source_passage="Bij aankomst zware rookontwikkeling",
                observation_type=ObservationType.HUMAN_OBSERVATION,
            )
        ],
    )
    assert len(extraction.items) == 1


def test_reconstruction_output_has_no_exact_time_field():
    """Structural guard for the absolute-time rule: the reconstruction schema
    must not expose any field the LLM could use to fabricate a timestamp."""
    fields = ReconstructedEvent.model_fields
    assert "exact_time" not in fields
    assert "timestamp" not in fields
    event = ReconstructedEvent(title="Aankomst eerste voertuig", order_hint=1, ai_summary="Test")
    assert event.approx_time_text is None


def test_commander_identity_display_name():
    identity = CommanderIdentity(callsign="P12", unit_name="1ste Hulpcentrum", rank="Adjudant", surname="Janssens")
    assert identity.display_name == "P12 (1ste Hulpcentrum) — Adjudant Janssens"
    assert identity.is_complete


def test_dispatch_record_raw_allows_missing_timestamp():
    rec = DispatchRecordRaw(row_index=3, event_description="Onbekend tijdstip event", timestamp=None)
    assert rec.timestamp is None


def test_incident_create_form_rejects_empty_location():
    with pytest.raises(ValidationError):
        IncidentCreateForm(
            date=dt.date(2026, 1, 1), location="", incident_type="Brand", description=""
        )
