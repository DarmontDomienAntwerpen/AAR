"""Loads the synthetic golden-fixture incident (spec §62) into the real app
database so it can be explored in the running Streamlit app, and runs the
full analysis pipeline on it using whichever LLM provider is configured in
.env (AAR_LLM_PROVIDER, defaults to "mock" — no API key needed).

Usage:
    python scripts/run_synthetic_demo.py

Then start the app (`streamlit run app.py`) and open the incident from the
archive — it will show as "Kerkstraat 45, Antwerpen" / Brand / 2026-03-04.
Safe to run multiple times: each run creates a new incident rather than
touching a previous demo run.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import datetime as dt  # noqa: E402
import tempfile  # noqa: E402

from aar.config.logging_setup import configure_logging, get_logger  # noqa: E402
from aar.db.session import get_engine, get_session, init_db  # noqa: E402
from aar.models import IncidentType  # noqa: E402
from aar.schemas.forms import IncidentCreateForm  # noqa: E402
from aar.services.analysis_service import trigger_analysis  # noqa: E402
from aar.services.dispatch_service import ingest_dispatch_excel  # noqa: E402
from aar.services.incident_service import create_incident  # noqa: E402
from aar.services.report_service import ingest_commander_report  # noqa: E402
from fixtures.synthetic_incident.build_fixture import (  # noqa: E402
    INCIDENT,
    build_commander_reports,
    build_dispatch_excel,
)

configure_logging()
logger = get_logger("scripts.run_synthetic_demo")


def main() -> None:
    init_db(get_engine())
    session = get_session()

    form = IncidentCreateForm(
        date=dt.date.fromisoformat(INCIDENT["date"]),
        location=INCIDENT["location"],
        incident_type=IncidentType(INCIDENT["incident_type"]),
        description=INCIDENT["description"],
    )
    incident = create_incident(session, form)
    print(f"Created demo incident #{incident.id}: {incident.location}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        report_paths = build_commander_reports(tmp_path / "reports")
        for path in report_paths:
            doc = ingest_commander_report(session, incident, path.read_bytes(), path.name)
            print(f"  Ingested {path.name}: {doc.parse_status.value}")

        dispatch_path = build_dispatch_excel(tmp_path / "dispatch")
        doc = ingest_dispatch_excel(session, incident, dispatch_path.read_bytes(), dispatch_path.name)
        print(f"  Ingested {dispatch_path.name}: {doc.parse_status.value}")

    print("Running analysis pipeline (mock LLM provider)...")
    run = trigger_analysis(session, incident)
    print(f"Analysis run status: {run.status.value}")
    if run.error_message:
        print(f"Error: {run.error_message}")

    session.close()
    print(f"\nDone. Start the app and open incident #{incident.id} from the archive.")


if __name__ == "__main__":
    main()
