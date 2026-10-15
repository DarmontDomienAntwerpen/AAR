"""Headless visual smoke test: walks the main screens of the running app
with Playwright and saves a screenshot of each. Proves the pages actually
render correctly (not just that they return HTTP 200).

Requires the app to already be running (see README.md, Getting started) with the
synthetic demo incident loaded (`python scripts/run_synthetic_demo.py`).
Playwright is not a project dependency — install it separately:

    pip install playwright && playwright install chromium

Usage:
    python scripts/screenshot_smoke_test.py [base_url] [incident_id]

Defaults to http://127.0.0.1:8000 and incident id 1 (what
run_synthetic_demo.py creates on a fresh database).
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
INCIDENT_ID = sys.argv[2] if len(sys.argv) > 2 else "1"

SHOT_DIR = Path(__file__).resolve().parent / "screenshots"
SHOT_DIR.mkdir(exist_ok=True)

PAGES = [
    ("01_archief", "/"),
    ("02_bronnen", f"/incidents/{INCIDENT_ID}/sources"),
    ("03_analyse", f"/incidents/{INCIDENT_ID}/analysis"),
    ("04_aar_overzicht", f"/incidents/{INCIDENT_ID}/aar?tab=overzicht"),
    ("05_aar_verloop", f"/incidents/{INCIDENT_ID}/aar?tab=verloop"),
    ("06_aar_bespreken", f"/incidents/{INCIDENT_ID}/aar?tab=bespreken"),
    ("07_aar_positief", f"/incidents/{INCIDENT_ID}/aar?tab=positief"),
    ("08_aar_leerpunten", f"/incidents/{INCIDENT_ID}/aar?tab=leerpunten"),
    ("09_definitieve_aar", f"/incidents/{INCIDENT_ID}/final"),
]

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 1000})

    for name, path in PAGES:
        page.goto(f"{BASE_URL}{path}", wait_until="networkidle")
        page.wait_for_timeout(300)
        out = SHOT_DIR / f"{name}.png"
        page.screenshot(path=str(out), full_page=True)
        print(f"saved: {out}")

    browser.close()

print(f"\nDone. Screenshots in {SHOT_DIR}")
