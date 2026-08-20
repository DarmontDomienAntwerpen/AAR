"""End-to-end tests for the FastAPI web UI, driven via Starlette's
TestClient (real ASGI app, real routing/templating — not a mock).

Uses an isolated temp SQLite DB per test via monkeypatching AAR_DB_PATH and
resetting the process-wide settings/engine singletons first, mirroring the
pattern documented for the (removed) Streamlit AppTest suite.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fixtures.synthetic_incident.build_fixture import build_commander_reports, build_dispatch_excel


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AAR_DB_PATH", str(tmp_path / "web_test.db"))
    monkeypatch.setenv("AAR_LLM_PROVIDER", "mock")

    from aar.config.settings import get_settings

    get_settings.cache_clear()
    import aar.db.session as db_session_module

    db_session_module._engine = None

    from aar.web.app import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c

    get_settings.cache_clear()
    db_session_module._engine = None


def _create_incident(client: TestClient) -> int:
    resp = client.post(
        "/incidents/new",
        data={
            "date": "2026-03-04",
            "location": "Kerkstraat 45, Antwerpen",
            "incident_type": "Brand",
            "description": "Testincident",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    location = resp.headers["location"]
    incident_id = int(location.split("/incidents/")[1].split("/")[0])
    return incident_id


def test_archive_page_loads(client: TestClient):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Archief" in resp.text


def test_new_incident_form_loads(client: TestClient):
    resp = client.get("/incidents/new")
    assert resp.status_code == 200


def test_create_incident_redirects_to_sources(client: TestClient):
    incident_id = _create_incident(client)
    resp = client.get(f"/incidents/{incident_id}/sources")
    assert resp.status_code == 200
    assert "Bronnen" in resp.text


def test_create_incident_rejects_empty_location(client: TestClient):
    resp = client.post(
        "/incidents/new",
        data={"date": "2026-03-04", "location": "", "incident_type": "Brand", "description": ""},
    )
    assert resp.status_code == 400


def test_archive_search_finds_created_incident(client: TestClient):
    _create_incident(client)
    resp = client.get("/", params={"q": "Kerkstraat"})
    assert "Kerkstraat 45" in resp.text
    resp2 = client.get("/", params={"q": "Nonexistentstraat"})
    assert "Kerkstraat 45" not in resp2.text


def test_full_flow_upload_analyze_review_finalize(client: TestClient, tmp_path):
    incident_id = _create_incident(client)

    report_paths = build_commander_reports(tmp_path / "reports")
    files = [("files", (p.name, p.read_bytes(), "application/octet-stream")) for p in report_paths]
    resp = client.post(f"/incidents/{incident_id}/sources/reports", files=files, follow_redirects=False)
    assert resp.status_code == 303

    dispatch_path = build_dispatch_excel(tmp_path / "dispatch")
    resp = client.post(
        f"/incidents/{incident_id}/sources/dispatch",
        files={"file": (dispatch_path.name, dispatch_path.read_bytes(), "application/octet-stream")},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    sources_page = client.get(f"/incidents/{incident_id}/sources")
    assert "P12 (1ste Hulpcentrum)" in sources_page.text
    assert "klaar voor analyse" in sources_page.text

    resp = client.post(f"/incidents/{incident_id}/analysis/run", follow_redirects=False)
    assert resp.status_code == 303
    assert "flash_type=success" in resp.headers["location"] or "Analyse" in resp.headers["location"]

    for tab in ("overzicht", "verloop", "bespreken", "positief", "leerpunten"):
        resp = client.get(f"/incidents/{incident_id}/aar", params={"tab": tab})
        assert resp.status_code == 200, tab

    # Add a photo, link it to the first event on the verloop tab.
    photo_bytes = b"\xff\xd8\xff\xe0fake-jpeg-content"
    resp = client.post(
        f"/incidents/{incident_id}/sources/photos",
        files={"files": ("gevel.jpg", photo_bytes, "image/jpeg")},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    sources_page = client.get(f"/incidents/{incident_id}/sources")
    assert "gevel.jpg" in sources_page.text

    from aar.db.session import get_session
    from aar.models import IncidentEvent, SourceDocument, SourceDocumentType

    session = get_session()
    photo = session.query(SourceDocument).filter_by(
        incident_id=incident_id, doc_type=SourceDocumentType.PHOTO_OR_PLAN
    ).one()
    event = session.query(IncidentEvent).filter_by(incident_id=incident_id).first()
    session.close()

    resp = client.get(f"/incidents/{incident_id}/media/{photo.id}")
    assert resp.status_code == 200
    assert resp.content == photo_bytes

    resp = client.post(
        f"/incidents/{incident_id}/media/link",
        data={"photo_id": photo.id, "event_id": event.id},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    verloop_page = client.get(f"/incidents/{incident_id}/aar", params={"tab": "verloop"})
    assert f"/incidents/{incident_id}/media/{photo.id}" in verloop_page.text

    # Add a correction, re-run analysis (Phase 9 path).
    resp = client.post(
        f"/incidents/{incident_id}/aar/events/{event.id}/correction",
        data={"text": "Dit was geen tegenstelling."},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    resp = client.post(f"/incidents/{incident_id}/aar/reanalyze", follow_redirects=False)
    assert resp.status_code == 303

    # Add a manual discussion point, then finalize.
    resp = client.post(
        f"/incidents/{incident_id}/aar/discussion-points",
        data={"title": "Handmatig punt", "description": "Toegevoegd door facilitator."},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    resp = client.get(f"/incidents/{incident_id}/final")
    assert resp.status_code == 200
    assert "Handmatig punt" in resp.text

    resp = client.post(f"/incidents/{incident_id}/final/finalize", follow_redirects=False)
    assert resp.status_code == 303

    final_page = client.get(f"/incidents/{incident_id}/final")
    assert "Afgerond" in final_page.text


def test_duplicate_report_upload_shows_warning(client: TestClient, tmp_path):
    incident_id = _create_incident(client)
    report_paths = build_commander_reports(tmp_path / "reports")
    p = report_paths[0]

    client.post(
        f"/incidents/{incident_id}/sources/reports",
        files={"files": (p.name, p.read_bytes(), "application/octet-stream")},
    )
    resp = client.post(
        f"/incidents/{incident_id}/sources/reports",
        files={"files": (p.name, p.read_bytes(), "application/octet-stream")},
        follow_redirects=False,
    )
    assert "flash_type=warning" in resp.headers["location"]


def test_unsupported_photo_extension_rejected(client: TestClient, tmp_path):
    incident_id = _create_incident(client)
    resp = client.post(
        f"/incidents/{incident_id}/sources/photos",
        files={"files": ("malware.exe", b"data", "application/octet-stream")},
        follow_redirects=False,
    )
    assert "flash_type=warning" in resp.headers["location"]


def test_nonexistent_incident_returns_404(client: TestClient):
    resp = client.get("/incidents/999999/sources")
    assert resp.status_code == 404
