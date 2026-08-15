from io import BytesIO

import pandas as pd
import pytest

from aar.models import DispatchRecord, ParseStatus, SourceDocument
from aar.services.dispatch_service import ingest_dispatch_excel
from aar.services.errors import DuplicateSourceError


def _dispatch_bytes() -> bytes:
    df = pd.DataFrame(
        {
            "Tijdstip": ["2026-03-04 14:07:00", "2026-03-04 14:11:00"],
            "Gebeurtenis": ["Eerste voertuig ter plaatse", "Opschaling"],
            "Eenheid": ["P12", "P21"],
        }
    )
    buf = BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


def test_ingest_dispatch_excel_success(session, sample_incident, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "aar.services.dispatch_service.get_settings",
        lambda: type("S", (), {"project_root": tmp_path})(),
    )
    file_bytes = _dispatch_bytes()
    doc = ingest_dispatch_excel(session, sample_incident, file_bytes, "dispatch.xlsx")

    assert doc.parse_status == ParseStatus.PARSED
    records = session.query(DispatchRecord).filter_by(source_document_id=doc.id).all()
    assert len(records) == 2
    assert records[0].event_description == "Eerste voertuig ter plaatse"


def test_ingest_dispatch_duplicate_raises(session, sample_incident, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "aar.services.dispatch_service.get_settings",
        lambda: type("S", (), {"project_root": tmp_path})(),
    )
    file_bytes = _dispatch_bytes()
    ingest_dispatch_excel(session, sample_incident, file_bytes, "dispatch.xlsx")
    with pytest.raises(DuplicateSourceError):
        ingest_dispatch_excel(session, sample_incident, file_bytes, "dispatch_copy.xlsx")
    assert session.query(SourceDocument).count() == 1
