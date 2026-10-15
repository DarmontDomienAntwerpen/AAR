# HANDOFF.md — Fire Service AAR Tool v1

Practical guide for the person who will run this application. For product
rationale and engineering history, see [PROJECT_STATE.md](PROJECT_STATE.md).
For a one-paragraph overview, see [README.md](README.md).

---

## 1. What this application does

An internal, AI-assisted After Action Review (AAR) tool for real fire-service
incidents. A facilitator:

1. Creates an incident (date, location, type, short description — the
   "eindbalans", shown as its own callout throughout the app).
2. Uploads each commander's completed `.docx` report — or, alternatively,
   one Google-Forms responses sheet (`.xlsx`) covering multiple commanders
   at once (see `aar/ingestion/commander_sheet.py`) — plus the dispatch/
   control-room `.xlsx` export, and optionally reference photos/plans
   (uploadable from three places: Bronnen, Overzicht, or directly inside a
   bevelvoerder's own overlay, where a photo can also be linked straight to
   that bevelvoerder — independent of linking a photo to an
   Incidentverloop moment).
3. Runs the AI analysis pipeline, which extracts structured information from
   each report, reconstructs a shared chronological incident view, and
   proposes discussion points, positive findings, lessons, and improvements.
4. Reviews and edits everything in the interactive AAR screen — the AI's
   output is a starting point, never the final word. Corrections can trigger
   a re-analysis that takes them into account. Werkpunten and Extra
   opmerkingen are the two tabs that are never AI-filtered — a direct,
   complete pull-through of what each bevelvoerder wrote, plus whatever the
   facilitator adds manually.
5. Marks the AAR as "afgerond" (finalized) once satisfied — this locks
   every mutating action (edits, uploads, re-analysis) across the whole
   incident, with a clearly visible "Heropenen" button to lift that lock
   again if something still needs fixing. It's then searchable in the
   archive either way.

The AI never invents timestamps, never silently resolves conflicting
accounts between commanders, and never judges an individual's competence —
see `PROJECT_STATE.md` §2 for the full list of non-negotiable rules this
tool enforces.

---

## 2. Prerequisites

- Python 3.11 or newer (developed and tested on 3.14.5).
- No external services required to run the app or its test suite — the
  default LLM provider is a deterministic mock that needs no API key.
- Optional: an Anthropic API key, only if you want real AI-quality analysis
  instead of the mock's mechanical rule-based output (see §6).

---

## 3. Installation

```bash
cd /path/to/AAR
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## 4. Environment variables

```bash
cp -n .env.example .env   # -n: never overwrites an existing .env
```

`.env` fields:

| Variable | Default | Purpose |
|---|---|---|
| `AAR_LLM_PROVIDER` | `mock` | `mock` (no key needed) or `anthropic` (real AI) |
| `ANTHROPIC_API_KEY` | (empty) | Required only if `AAR_LLM_PROVIDER=anthropic` |
| `AAR_ANTHROPIC_MODEL` | `claude-sonnet-5` | Model id used for Anthropic calls |
| `AAR_DB_PATH` | `data/aar.db` | SQLite database file location |
| `AAR_LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR` |
| `AAR_ACCESS_PASSWORD` | (empty) | If set, gates every page behind a single shared login (`/login`) — no accounts, one password for every facilitator. Leave empty for local-only use where nothing beyond your own machine can reach the app. |
| `AAR_SESSION_SECRET` | auto-generated | Signs the login session cookie. Auto-generated and persisted to `data/.session_secret` (gitignored) on first run if left empty, so logins survive restarts. Only set explicitly if `data/` gets wiped on every deploy and you need sessions to survive that. |

Never commit `.env` (it's gitignored) or put a real API key or
`AAR_ACCESS_PASSWORD` in any file that gets committed.

---

## 5. Starting the application

```bash
source .venv/bin/activate
uvicorn app:app --reload
```

Opens at `http://127.0.0.1:8000`. (`python app.py` also works for a quick
dev run, on port 8000 as well.) The database and its tables are created
automatically on first request — no manual migration step. Uploaded
originals (reports, dispatch sheets, photos/plans) are stored under
`data/uploads/<incident_id>/`.

The UI is a server-rendered FastAPI + Jinja2 + Tailwind app — no separate
frontend build step, no Node.js required.

---

## 6. Configuring a real LLM provider

By default the app uses `MockLLMProvider` — a deterministic, rule-based
stand-in that lets the whole app and test suite run with zero external
dependencies, but which only does mechanical keyword-based detection (exact
Dutch assumption/uncertainty phrases, category-based grouping). It does
**not** do real cross-report semantic reasoning — notably, it cannot detect
a conflict between two commanders' accounts of the same event, and it
cannot infer an unlabelled positive pattern across reports (see
`PROJECT_STATE.md` §9 for the two specific documented limitations).

To get real AI-quality analysis:

1. Get an Anthropic API key (https://console.anthropic.com).
2. In `.env`, set:
   ```
   AAR_LLM_PROVIDER=anthropic
   ANTHROPIC_API_KEY=sk-ant-...
   ```
3. Restart the app. Every subsequent "Analyse (opnieuw) uitvoeren" click
   will call the real model instead of the mock.

This path has been exercised repeatedly against the live API on real
(non-synthetic) incidents — see `PROJECT_STATE.md` §7-9 (Phases 21-24) for
what that surfaced and fixed. Each call logs its input/output token count
(`aar/llm/provider_anthropic.py`) so actual cost is visible in the server
log, not just estimated. If something breaks, check
`aar/llm/provider_anthropic.py` and `aar/llm/base.py::_repair_double_encoded_json`
first — the latter fixes a real, recurring schema-encoding quirk seen under
load.

---

## 7. Running tests

```bash
source .venv/bin/activate
pytest                    # full suite — no API key needed, no network calls
```

Expect ~142 tests, all passing except one intentionally-skipped test
(`test_synthetic_incident_conditions_c_and_e_require_real_provider`) that
documents the mock-provider limitation from §6 rather than silently omitting
the check.

Test layout:
- `tests/unit/` — schemas, models, parsers, LLM abstraction/mock, individual
  pipeline stages, service-layer CRUD.
- `tests/integration/` — multi-component flows: ingestion → DB, the full
  6-stage pipeline end to end, the synthetic golden fixture, adversarial
  hallucination checks, and `tests/integration/test_web_app.py` — the full
  web UI driven through FastAPI's `TestClient` against the real ASGI app
  (create incident → upload → analyse → review/correct/re-analyse →
  finalise → search archive; also covers photo upload/linking).

A real-provider integration test is intentionally not part of the default
suite (would require a paid API key); see §6 for how to exercise that path
manually.

### Headless visual smoke test (screenshots)

For an actual rendered-pixels check (not just HTTP status codes), there's a
Playwright-based script that walks the same flow as `test_web_app.py` and
saves a screenshot at every screen. Playwright's browser isn't a project
dependency (it's a one-time ~270MB download), so install it separately if
you want to use this:

```bash
pip install playwright && playwright install chromium
python scripts/run_synthetic_demo.py   # seed data first
uvicorn app:app &                       # start the server
python scripts/screenshot_smoke_test.py # screenshots land next to the script
```

---

## 8. Running the synthetic demonstration incident

A fictional but realistic incident (a house fire with four commander
reports and one dispatch export — see `fixtures/synthetic_incident/
build_fixture.py`) can be loaded straight into your running database:

```bash
python scripts/run_synthetic_demo.py
```

This creates a new incident, ingests all four reports and the dispatch
sheet, and runs the full analysis pipeline (using whatever
`AAR_LLM_PROVIDER` is configured — the mock by default). Then start the app
and open it from the archive. Safe to re-run — each run adds a new incident
rather than touching a previous one.

---

## 9. Where data is stored

- **Database**: `data/aar.db` (SQLite; path configurable via `AAR_DB_PATH`).
  All incidents, reports, observations, events, findings, lessons, etc.
- **Uploaded originals**: `data/uploads/<incident_id>/<uuid>_<filename>`.
  The original `.docx`/`.xlsx`/photo/plan files are kept for traceability
  even after parsing.
- Both `data/*.db` and `data/uploads/` are gitignored — never committed.

## 10. Resetting development data

```bash
rm -f data/aar.db
rm -rf data/uploads
```

The next app start recreates an empty database automatically. **Also do
this after pulling a change that alters `aar/models/*.py`** — there is no
migration system (Alembic) in v1; `Base.metadata.create_all()` only creates
tables that don't exist yet, it does not alter existing ones. An old
`data/aar.db` from before a schema change will be missing columns and
needs to be recreated. This is accepted technical debt for a single-
operator local MVP tool.

---

## 11. The commander report template

`templates/commander_report_template.docx` is the standard form every
commander fills in. It's generated by code
(`aar/ingestion/commander_docx.py::generate_commander_report_template`), not
hand-authored, so it always matches what the parser expects. Regenerate it
after any change to the section headings:

```bash
python scripts/generate_template.py
```

Do not rename section headings or the identification table labels without
updating `aar/ingestion/commander_docx.py` in the same change — the parser
matches on exact (normalised) text. It's also available for download
directly from the running app's "Bronnen" screen.

The Google Form path (`aar/ingestion/commander_sheet.py`) mirrors the same
5 sections but matches by normalised header *prefix* rather than exact
text — a facilitator building the Form manually will not word every
question identically to the DOCX template, and real-world drift already
broke the original exact-match assumption once (see `PROJECT_STATE.md`
Phase 23). If a real Form's questions stop being recognised, check
`IDENTITY_COLUMN_PREFIXES`/`SECTION_COLUMN_PREFIXES`/`_ACTION_COLUMN_RE` in
that file first.

---

## 12. Known limitations (v1, by design — see PROJECT_STATE.md §2/§9 for why)

- **Mock provider can't do cross-report semantic reasoning.** Conflict
  detection between two commanders' accounts, and inferring an unlabelled
  positive pattern, both require a real LLM (§6).
- **No action-item tracking.** The AAR ends at lessons/improvements — no
  owners, deadlines, or status, by explicit product decision (spec §44).
- **No event merge/split.** Facilitators can add/edit/delete incident
  moments but can't merge two into one or split one apart — add/remove
  covers the practical need without that extra complexity.
- **Dispatch-to-event timestamp matching is a conservative heuristic**
  (shared-significant-word overlap, `aar/analysis/timeline.py`), not
  semantic understanding. It will under-attach (leave a time unset when a
  human would recognise the match) before it will ever mis-attach — that's
  intentional per the absolute-time rule.
- **Full pipeline re-run on re-analysis**, not dependency-aware partial
  re-analysis — explicitly allowed by the spec for v1 (§49).
- **No AI-vs-human audit trail.** Only the current, facilitator-validated
  content is kept — not a history of what the AI originally proposed vs.
  what was changed (spec §50, deliberate).
- **Photos/plans are reference material only.** They are not analysed by
  the AI pipeline — purely visual context the facilitator can caption and
  pin to an incident moment. This was an explicit scope decision when the
  feature was added (not in the original spec).
- **No database migration system.** See §10 — reset `data/aar.db` after any
  model schema change.
- **`AnthropicProvider` is unverified against the live API** in this build
  environment — see §6.

## 13. Unresolved issues

All planned phases (0-13) are complete, plus 11 post-handoff phases
(14-24) — see `PROJECT_STATE.md` §7 for the phase-by-phase status. The
known, currently-open items (real-LLM non-determinism as a recurring
characteristic — not fully eliminable, only individually caught where
checkable; no automated backup of `data/aar.db`/`data/uploads/`, an
explicit accepted trade-off — see below) are tracked in
`PROJECT_STATE.md` §9, kept current there rather than duplicated here.

---

## 14. Project structure

```
AAR/
├── app.py                       Entrypoint — re-exports aar.web.app:app
├── requirements.txt
├── pytest.ini
├── .env.example
├── README.md / PROJECT_STATE.md / HANDOFF.md
├── aar/
│   ├── config/                  settings, logging
│   ├── db/                      SQLAlchemy engine/session
│   ├── models/                  ORM models + shared enums
│   ├── schemas/                 Pydantic boundary contracts (forms,
│   │                            ingestion output, LLM I/O per stage)
│   ├── ingestion/                commander_docx.py, commander_sheet.py
│   │                             (Google Form/Sheet export), dispatch_excel.py
│   ├── llm/                      base.py, mock.py, provider_anthropic.py,
│   │                             factory.py, prompts/
│   ├── analysis/                 extraction, reconstruction, timeline,
│   │                             findings, lessons, narrative (AI situation
│   │                             synthesis), cleanup (on-demand text
│   │                             proofreading, not a pipeline stage),
│   │                             pipeline (orchestrator)
│   ├── services/                 incident/report/dispatch/media/analysis/
│   │                             aar services — all business logic, no
│   │                             web-framework code
│   ├── ui/                       labels.py — Dutch enum display labels,
│   │                             shared by the web templates
│   └── web/                      FastAPI app: app.py, deps.py, flash.py,
│                                 templating.py, routes/*.py,
│                                 templates/*.html (Jinja2 + Tailwind CDN)
├── templates/                    commander_report_template.docx
├── fixtures/synthetic_incident/  golden fixture generator
├── scripts/                      generate_template.py, run_synthetic_demo.py
├── data/                         sqlite db + uploads (gitignored)
└── tests/{unit,integration}/
```
