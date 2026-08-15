import pytest

from aar.models import IncidentEvent, SourceDocumentType
from aar.services import media_service
from aar.services.errors import DuplicateSourceError


def _patch_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "aar.services.media_service.get_settings",
        lambda: type("S", (), {"project_root": tmp_path})(),
    )


def test_ingest_photo_success(session, sample_incident, tmp_path, monkeypatch):
    _patch_settings(monkeypatch, tmp_path)
    doc = media_service.ingest_photo(session, sample_incident, b"fake-jpeg-bytes", "gevel.jpg")

    assert doc.doc_type == SourceDocumentType.PHOTO_OR_PLAN
    assert doc.caption == ""
    assert doc.event_id is None
    photos = media_service.list_photos(session, sample_incident)
    assert len(photos) == 1


def test_ingest_photo_rejects_unsupported_extension(session, sample_incident, tmp_path, monkeypatch):
    _patch_settings(monkeypatch, tmp_path)
    with pytest.raises(media_service.UnsupportedMediaTypeError):
        media_service.ingest_photo(session, sample_incident, b"data", "malware.exe")


def test_ingest_duplicate_photo_raises(session, sample_incident, tmp_path, monkeypatch):
    _patch_settings(monkeypatch, tmp_path)
    media_service.ingest_photo(session, sample_incident, b"same-bytes", "plan.pdf")
    with pytest.raises(DuplicateSourceError):
        media_service.ingest_photo(session, sample_incident, b"same-bytes", "plan_copy.pdf")


def test_set_caption(session, sample_incident, tmp_path, monkeypatch):
    _patch_settings(monkeypatch, tmp_path)
    doc = media_service.ingest_photo(session, sample_incident, b"bytes", "foto.png")
    media_service.set_caption(session, doc, "  Voorgevel bij aankomst  ")
    assert doc.caption == "Voorgevel bij aankomst"


def test_link_and_unlink_event(session, sample_incident, tmp_path, monkeypatch):
    _patch_settings(monkeypatch, tmp_path)
    doc = media_service.ingest_photo(session, sample_incident, b"bytes", "foto.png")
    event = IncidentEvent(incident_id=sample_incident.id, title="Aankomst", order_index=0)
    session.add(event)
    session.commit()

    media_service.link_to_event(session, doc, event)
    assert doc.event_id == event.id

    media_service.link_to_event(session, doc, None)
    assert doc.event_id is None


def test_delete_photo_removes_row_and_file(session, sample_incident, tmp_path, monkeypatch):
    _patch_settings(monkeypatch, tmp_path)
    doc = media_service.ingest_photo(session, sample_incident, b"bytes", "foto.png")
    from pathlib import Path

    path = Path(doc.stored_path)
    assert path.exists()

    media_service.delete_photo(session, doc)
    assert not path.exists()
    assert media_service.list_photos(session, sample_incident) == []


def test_deleting_event_unlinks_but_keeps_photo(session, sample_incident, tmp_path, monkeypatch):
    from aar.services import aar_service

    _patch_settings(monkeypatch, tmp_path)
    doc = media_service.ingest_photo(session, sample_incident, b"bytes", "foto.png")
    event = IncidentEvent(incident_id=sample_incident.id, title="Aankomst", order_index=0)
    session.add(event)
    session.commit()
    media_service.link_to_event(session, doc, event)

    aar_service.delete_event(session, event)

    remaining = media_service.list_photos(session, sample_incident)
    assert len(remaining) == 1
    assert remaining[0].event_id is None
