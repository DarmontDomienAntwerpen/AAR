"""Headless UI smoke test using Streamlit's AppTest framework — walks the
full facilitator flow (create incident, analyse, interactive AAR, correction
+ re-analysis, finalise, archive search) through the real app.py without a
browser. Uses the mock LLM provider, so no API key is required.

Not part of the pytest suite: st.cache_resource and the DB engine singleton
in aar/db/session.py are process-global, which makes repeated AppTest runs
inside one pytest process fragile. Run standalone instead:

    python scripts/ui_smoke_test.py
"""
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

tmpdir = tempfile.mkdtemp()
os.environ["AAR_DB_PATH"] = os.path.join(tmpdir, "smoke.db")
os.environ["AAR_LLM_PROVIDER"] = "mock"

sys.path.insert(0, str(REPO_ROOT))
os.chdir(REPO_ROOT)

from streamlit.testing.v1 import AppTest  # noqa: E402

at = AppTest.from_file(str(REPO_ROOT / "app.py"))
at.run()
assert not at.exception, f"Archive page raised: {at.exception}"
print("OK: archive page loaded")

new_incident_buttons = [b for b in at.button if "Nieuw incident" in (b.label or "")]
assert new_incident_buttons, "New incident button not found"
new_incident_buttons[0].click().run()
assert not at.exception, f"New incident page raised: {at.exception}"
print("OK: new incident page loaded")

loc_inputs = [w for w in at.text_input if w.label == "Locatie"]
assert loc_inputs, "Location field not found"
loc_inputs[0].set_value("Teststraat 1, Smoketest")
desc_inputs = [w for w in at.text_area if w.label == "Korte omschrijving"]
desc_inputs[0].set_value("Smoke test incident.")
submit_buttons = [b for b in at.button if "aanmaken" in (b.label or "").lower()]
assert submit_buttons, "Submit button not found"
submit_buttons[0].click().run()
assert not at.exception, f"Incident creation raised: {at.exception}"
print("OK: incident created, now on:", at.session_state["route"])

assert at.session_state["route"] == "sources"
incident_id = at.session_state["incident_id"]
assert incident_id

# Seed a commander report directly via the service layer (bypassing file
# upload widget simulation, which AppTest does not support well) so we can
# exercise analysis/aar/final_aar screens.
from aar.db.session import get_session  # noqa: E402
from aar.models import (  # noqa: E402
    CommanderReport,
    Incident,
    ParseStatus,
    SourceDocument,
    SourceDocumentType,
)

session = get_session()
incident = session.get(Incident, incident_id)
doc = SourceDocument(
    incident_id=incident.id,
    doc_type=SourceDocumentType.COMMANDER_REPORT,
    original_filename="p12.docx",
    stored_path="/tmp/p12.docx",
    content_hash="smoke-hash-1",
    parse_status=ParseStatus.PARSED,
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
    raw_sections={
        "observations": "Bij aankomst was er zware rookontwikkeling op de eerste verdieping.",
        "doubts_assumptions": "Ik ging ervan uit dat de achterzijde al gecontroleerd was.",
        "went_well": "De coordinatie tussen de eenheden verliep vlot.",
    },
)
session.add(report)
session.commit()
session.close()
print("OK: seeded commander report directly via service layer")

at.run()
assert not at.exception, f"Sources page raised after seeding: {at.exception}"
start_analysis_buttons = [b for b in at.button if "Analyse starten" in (b.label or "")]
assert start_analysis_buttons, "Start analysis button not found"
start_analysis_buttons[0].click().run()
assert not at.exception, f"Analysis page raised: {at.exception}"
assert at.session_state["route"] == "analysis"
print("OK: analysis page loaded")

run_buttons = [b for b in at.button if "Analyse" in (b.label or "") and "uitvoeren" in (b.label or "")]
assert run_buttons, "Run analysis button not found"
run_buttons[0].click().run()
assert not at.exception, f"Running analysis raised: {at.exception}"
print("OK: analysis executed without exception")

goto_aar_buttons = [b for b in at.button if "interactieve AAR" in (b.label or "")]
assert goto_aar_buttons, "Goto AAR button not found"
goto_aar_buttons[0].click().run()
assert not at.exception, f"AAR page raised: {at.exception}"
assert at.session_state["route"] == "aar"
print("OK: interactive AAR page loaded, tabs:", [t.label for t in at.tabs])

correction_text_areas = [w for w in at.text_area if w.key and w.key.startswith("correction_text_event_")]
assert correction_text_areas, "Correction text area not found"
correction_text_areas[0].set_value("Dit was in werkelijkheid geen tegenstelling.")
correction_submit_buttons = [b for b in at.button if b.label == "Correctie opslaan"]
assert correction_submit_buttons, "Correction submit button not found"
correction_submit_buttons[0].click().run()
assert not at.exception, f"Adding correction raised: {at.exception}"
print("OK: correction added")

reanalysis_buttons = [b for b in at.button if b.label == "Analyse opnieuw uitvoeren"]
assert reanalysis_buttons, "Re-analysis button not found"
reanalysis_buttons[0].click().run()
assert not at.exception, f"Re-analysis raised: {at.exception}"
print("OK: re-analysis after correction executed without exception")

goto_final_buttons = [b for b in at.button if "Definitieve AAR" in (b.label or "")]
assert goto_final_buttons, "Goto final AAR button not found"
goto_final_buttons[0].click().run()
assert not at.exception, f"Final AAR page raised: {at.exception}"
assert at.session_state["route"] == "final_aar"
print("OK: final AAR page loaded")

finalize_buttons = [b for b in at.button if "Markeer als afgerond" in (b.label or "")]
assert finalize_buttons, "Finalize button not found"
finalize_buttons[0].click().run()
assert not at.exception, f"Finalize raised: {at.exception}"
print("OK: incident finalized")

back_to_aar_buttons = [b for b in at.button if "interactieve AAR" in (b.label or "")]
assert back_to_aar_buttons, "Back-to-interactive-AAR button not found"
back_to_aar_buttons[0].click().run()
assert not at.exception, f"AAR page raised: {at.exception}"

back_buttons = [b for b in at.button if "Terug naar archief" in (b.label or "")]
assert back_buttons, "Back-to-archive button not found"
back_buttons[0].click().run()
assert not at.exception, f"Archive page raised: {at.exception}"
assert at.session_state["route"] == "archive"

search_inputs = [w for w in at.text_input if "Zoeken" in (w.label or "")]
assert search_inputs, "Search field not found"
search_inputs[0].set_value("Smoketest").run()
assert not at.exception, f"Archive search raised: {at.exception}"
found = any("Smoketest" in md.value for md in at.markdown)
assert found, "Finalized incident not found via archive search"
print("OK: archive search finds the finalized incident")

print("\nALL UI SMOKE CHECKS PASSED")
