# HANDOFF.md — Fire Service AAR Tool v1

Practical guide for the person who will run this application. For product
rationale and engineering history, see [PROJECT_STATE.md](PROJECT_STATE.md).
For a one-paragraph overview, see [README.md](README.md).

---

## 1. What this application does

An internal, AI-assisted After Action Review (AAR) tool for real fire-service
incidents. A facilitator:

1. Creates an incident (date, location, type, short description).
2. Uploads each commander's completed `.docx` report and the dispatch/
   control-room `.xlsx` export.
3. Runs the AI analysis pipeline, which extracts structured information from
   each report, reconstructs a shared chronological incident view, and
   proposes discussion points, positive findings, lessons, and improvements.
4. Reviews and edits everything in the interactive AAR screen — the AI's
   output is a starting point, never the final word. Corrections can trigger
   a re-analysis that takes them into account.
5. Marks the AAR as finished; it's then searchable in the archive.

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
cp .env.example .env
```

`.env` fields:

| Variable | Default | Purpose |
|---|---|---|
| `AAR_LLM_PROVIDER` | `mock` | `mock` (no key needed) or `anthropic` (real AI) |
| `ANTHROPIC_API_KEY` | (empty) | Required only if `AAR_LLM_PROVIDER=anthropic` |
| `AAR_ANTHROPIC_MODEL` | `claude-sonnet-5` | Model id used for Anthropic calls |
| `AAR_DB_PATH` | `data/aar.db` | SQLite database file location |
| `AAR_LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR` |

Never commit `.env` (it's gitignored) or put a real API key in any file
that gets committed.

---

## 5. Starting the application

```bash
source .venv/bin/activate
streamlit run app.py
```

Opens in your browser (default `http://localhost:8501`). The database and
its tables are created automatically on first run — no manual migration
step. Uploaded original files are stored under `data/uploads/<incident_id>/`.

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

**This path is UNVERIFIED in this handoff** — no API key was available in
the build environment, so `AnthropicProvider` has never actually been
exercised against the live API. Everything around it (prompt construction,
JSON-schema-forced tool use, retry-on-invalid-output, error handling) is
implemented and unit-tested with a fake provider standing in for the SDK
call, but the real network call itself needs to be verified by whoever has
a key. If something breaks, check `aar/llm/provider_anthropic.py` first —
it's a single, short file.

---

## 7. Running tests

```bash
source .venv/bin/activate
pytest                    # full suite — no API key needed, no network calls
```

Expect ~95 tests, all passing except one intentionally-skipped test
(`test_synthetic_incident_conditions_c_and_e_require_real_provider`) that
documents the mock-provider limitation from §6 rather than silently omitting
the check.

Test layout:
- `tests/unit/` — schemas, models, parsers, LLM abstraction/mock, individual
  pipeline stages, service-layer CRUD.
- `tests/integration/` — multi-component flows: ingestion → DB, the full
  6-stage pipeline end to end, the synthetic golden fixture, adversarial
  hallucination checks.

A real-provider integration test is intentionally not part of the default
suite (would require a paid API key); see §6 for how to exercise that path
manually.

### Headless UI smoke test

There's also a standalone script that drives the actual Streamlit app (not
just the service layer) through the full facilitator workflow using
Streamlit's own `AppTest` framework — create incident → analyse → review →
correct → re-analyse → finalise → search archive:

```bash
python scripts/ui_smoke_test.py
```

It's not part of the `pytest` suite because Streamlit's caching is
process-global and makes repeated `AppTest` runs inside one pytest process
fragile (see `PROJECT_STATE.md` §8-9 for why). Run it standalone whenever
you touch anything under `aar/ui/`.

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
  The original `.docx`/`.xlsx` files are kept for traceability even after
  parsing.
- Both `data/*.db` and `data/uploads/` are gitignored — never committed.

## 10. Resetting development data

```bash
rm -f data/aar.db
rm -rf data/uploads
```

The next app start recreates an empty database automatically.

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

Do not rename section headings or the identification/objective-achieved
table labels without updating `aar/ingestion/commander_docx.py` in the same
change — the parser matches on exact (normalised) text.

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
- **`AnthropicProvider` is unverified against the live API** in this build
  environment — see §6.

## 13. Unresolved issues

None known. All planned phases (0-13) are complete; see `PROJECT_STATE.md`
§7 for the phase-by-phase status and §9 for the (small, all-documented)
list of things that need a real API key to verify further.

---

## 14. Project structure

```
AAR/
├── app.py                       Streamlit entrypoint / page router
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
│   ├── ingestion/                commander_docx.py, dispatch_excel.py
│   ├── llm/                      base.py, mock.py, provider_anthropic.py,
│   │                             factory.py, prompts/
│   ├── analysis/                 extraction, reconstruction, timeline,
│   │                             findings, lessons, pipeline (orchestrator)
│   ├── services/                 incident/report/dispatch/analysis/aar
│   │                             services — all business logic, no
│   │                             Streamlit code
│   └── ui/                       thin Streamlit page modules, call
│                                 services only
├── templates/                    commander_report_template.docx
├── fixtures/synthetic_incident/  golden fixture generator
├── scripts/                      generate_template.py, run_synthetic_demo.py,
│                                 ui_smoke_test.py
├── data/                         sqlite db + uploads (gitignored)
└── tests/{unit,integration}/
```
