# PROJECT_STATE.md — Fire Service AAR Tool v1

Living engineering source of truth. Read before starting a phase; update after
completing or materially changing one. Last updated: 2026-08-15 — **all
phases (0-13) complete, Definition of Done satisfied** (see §11 for the
checklist and the two explicitly-documented UNVERIFIED items), **plus two
post-handoff changes made at the user's explicit request: a full UI rewrite
from Streamlit to FastAPI+Jinja2+Tailwind (Phase 14), and a photo/plan
attachment feature (Phase 15).** See §7 and §8 for details.

---

## 1. Product Objective

Internal AI-assisted After Action Review (AAR) tool for real fire-service
incidents. Ingests structured commander DOCX reports + dispatch/control-room
Excel data, uses an LLM for semantic extraction and analysis (never for
deterministic bookkeeping), and produces an interactive, chronological,
evidence-traceable AAR that a human facilitator runs and finalises. The AI is
an analytical assistant, never the final authority. Full requirements are the
master build prompt supplied by the user (verbatim product spec — do not
deviate from it without documenting why here).

## 2. Non-Negotiable Principles (do not relitigate)

- Hindsight bias rule: analyse decisions using only information available at
  that moment; later information is never projected backward.
- Absolute time rule: never invent/interpolate exact timestamps. Unknown stays
  unknown; narrative-only events get relative order, not a clock time.
- Never silently resolve a conflict between sources; surface it.
- Never present an AI inference as a fact. Preserve attribution to source.
- No blame, no individual performance scoring, no competence rating.
- No action-item/task tracking — the AAR ends at conclusions/improvements.
- LLM used only for semantic understanding/analysis; everything deterministic
  (file IO, parsing, timestamp math, DB, filtering, search) stays in plain
  Python.
- Priority order under trade-offs: reliability > source fidelity > fabrication
  prevention > useful analysis > facilitator usability > completeness >
  performance > visual polish.

## 3. Technical Decisions Log

| Decision | Choice | Rationale |
|---|---|---|
| Language/runtime | Python 3.11+ (dev machine has 3.14.5, compatible) | spec requirement |
| UI | ~~Streamlit~~ **FastAPI + Jinja2 + Tailwind (CDN) + a little vanilla JS** — changed in Phase 14 at the user's explicit request ("modern, lighter, professional... not Streamlit or Gradio"). Server-rendered HTML, no Node build step, no SPA framework. | spec originally said Streamlit for MVP simplicity; superseded by direct user feedback after seeing it running — see Phase 14 notes in §8 for the full rationale and alternatives considered |
| DB | SQLite file at `data/aar.db` via SQLAlchemy 2.0 ORM | spec requirement |
| Validation | Pydantic v2 at every boundary (LLM output, ingestion, forms) | spec requirement |
| DOCX | `python-docx`, heading-tagged sections parsed by exact heading text | deterministic structure needed for reliable parsing |
| Excel | `pandas` + `openpyxl`, defensive header-normalisation parser | spec requirement, real spreadsheets vary |
| LLM abstraction | `LLMProvider` ABC in `aar/llm/base.py`; `MockLLMProvider` (deterministic, rule-based) + `AnthropicProvider` (optional, needs `ANTHROPIC_API_KEY`) | spec requirement, ordinary tests must not need a paid key |
| LLM structured output | Provider returns raw text/JSON; caller validates through Pydantic; Anthropic path uses tool-use forced JSON schema | reliability over trust |
| Packaging | plain `aar/` package, no pip install of itself; `requirements.txt` for deps; `pytest.ini` sets `pythonpath = .` | simplest for a non-packaging-savvy operator |
| Confidence representation | semantic enum (`ondersteund`/`deels_ondersteund`/`onzeker`/`conflicterend`/`onvoldoende_bewijs`), never a float score | spec §56 |
| Re-analysis after correction | full pipeline re-run from Stage 3 onward using corrections as authoritative context, not dependency-aware partial re-analysis | spec §49 explicitly allows this for v1 |
| Audit trail of AI-vs-human edits | not stored; only current validated content persists | spec §50 |
| Git | local repo initialised for change tracking during build; no remote | engineering hygiene, reversible |

## 4. Directory Structure

```
AAR/
├── app.py                     # entrypoint — re-exports aar.web.app:app (uvicorn app:app)
├── requirements.txt
├── pytest.ini
├── .env.example
├── README.md
├── PROJECT_STATE.md
├── HANDOFF.md
├── aar/
│   ├── config/                # settings, logging setup
│   ├── db/                    # SQLAlchemy engine/session, init
│   ├── models/                # SQLAlchemy ORM models
│   ├── schemas/                # Pydantic schemas (boundary contracts)
│   ├── ingestion/              # commander_docx.py, dispatch_excel.py
│   ├── llm/                    # base.py, mock.py, provider_anthropic.py, prompts/
│   ├── analysis/               # extraction, normalisation, reconstruction,
│   │                           # timeline, findings, lessons, pipeline orchestrator
│   ├── services/                # incident/report/dispatch/media/analysis/aar services
│   ├── ui/                      # labels.py only — Dutch enum display labels,
│   │                             shared by the web templates (Streamlit pages removed
│   │                             in Phase 14; this dir kept just for the label module)
│   └── web/                     # FastAPI app (Phase 14): app.py, deps.py, flash.py,
│                                 templating.py, routes/*.py, templates/*.html
├── templates/                   # commander_report_template.docx generator + generated file
├── fixtures/synthetic_incident/ # golden fixture: 4 DOCX reports, 1 dispatch xlsx
├── data/                        # sqlite db + uploaded originals (gitignored)
└── tests/{unit,integration}/
```

## 5. Data Model (conceptual — see `aar/models/*.py` for actual columns)

`Incident(1) -- (N) SourceDocument -- (0..1) CommanderReport` (SourceDocument
also covers dispatch XLSX and, since Phase 15, `PHOTO_OR_PLAN` reference
files — the latter carry a `caption` and an optional `event_id` FK so a
photo can be pinned to a specific `IncidentEvent`; photos are never parsed
or fed to the AI pipeline)
`Incident(1) -- (N) DispatchRecord`
`Incident(1) -- (N) Observation` (each tagged FACT/HUMAN_OBSERVATION/ASSUMPTION/UNCERTAINTY/CONFLICT/AI_OBSERVATION, linked to source report + source passage)
`Incident(1) -- (N) IncidentEvent` (chronological moment) `-- (N) EventPerspective` (per-commander view of that moment, linked to Observations)
`Incident(1) -- (N) DiscussionPoint / PositiveFinding / Lesson / Improvement` (each with evidence links to Observations/Events)
`Incident(1) -- (N) HumanCorrection` (facilitator edits, fed back into re-analysis as authoritative context)
`Incident(1) -- (N) AnalysisRun` (bookkeeping: when the pipeline ran, on top of which corrections)

JSON columns used only for: source-passage evidence lists, and free-form
LLM-extracted sub-structures that don't need independent querying. All
searchable/filterable fields (date, location, incident_type, status, source
report id, event ordering) are explicit columns.

## 6. AI Pipeline Stages (implemented in `aar/analysis/`)

1. **Extraction** (`extraction.py`) — per report, LLM extracts structured
   `ReportExtraction` Pydantic model (observations, information available/
   missing, assessment, decision, objective, actions, result, went well/less
   well, why, assumptions/uncertainties, other) with source passage for each
   item. Runs independently per report.
2. **Normalisation** (`normalisation.py`) — deterministic: converts each
   extraction item into an `Observation` DB row with its semantic type,
   without discarding original wording.
3. **Reconstruction** (`reconstruction.py`) — LLM groups observations across
   reports into candidate `IncidentEvent`s with relative order; never invents
   timestamps.
4. **Dispatch enrichment** (`timeline.py`) — deterministic: attaches a
   dispatch timestamp to an event only when a dispatch record clearly
   corresponds; keeps provenance; leaves everything else unset.
5. **Findings** (`findings.py`) — LLM proposes DiscussionPoints,
   PositiveFindings, AI_OBSERVATION-type Observations, per event and overall.
6. **Lessons** (`lessons.py`) — LLM proposes Lessons/Improvements from the
   accumulated findings.

Orchestrated by `aar/analysis/pipeline.py::run_analysis(incident_id, provider)`.
Human corrections (Stage 9 / spec §49) are re-injected as an explicit
"eerdere correcties door de facilitator" context block and the pipeline is
re-run from Stage 3 onward (extraction stays cached since raw reports didn't
change).

## 7. Implementation Phases & Status

| Phase | Description | Status |
|---|---|---|
| 0 | Inspect & plan | DONE |
| 1 | Foundation (project skeleton, config, logging, DB, schemas, Streamlit shell, pytest) | DONE |
| 2 | Commander DOCX template + parser | DONE |
| 3 | Dispatch Excel ingestion | DONE |
| 4 | LLM abstraction (base/mock/anthropic) | DONE |
| 5 | Report AI extraction | DONE |
| 6 | Incident reconstruction | DONE |
| 7 | Analysis engine (findings/lessons) | DONE |
| 8 | Interactive AAR (Streamlit workflow) | DONE |
| 9 | Re-analysis after correction | DONE |
| 10 | Archive/search | DONE (built in Phase 1, exercised in Phase 8 smoke test) |
| 11 | Synthetic end-to-end validation | DONE |
| 12 | Hardening (full regression) | DONE |
| 13 | Handoff | DONE |
| 14 | *(post-handoff)* UI rewrite: Streamlit → FastAPI + Jinja2 + Tailwind | DONE |
| 15 | *(post-handoff)* Photo/plan attachments | DONE |

## 8. Completed Work

- Phase 0: environment inspected (empty dir, Python 3.14.5, no git). Directory
  skeleton created. Git repo initialised locally (no remote).
- Phase 1: venv + `requirements.txt` install verified. `aar/config` (settings
  from env/.env, logging). `aar/db/session.py` (engine/session, test-isolated
  via explicit-engine pattern — no shared global DB state between tests).
  Full SQLAlchemy model set in `aar/models/` (Incident, SourceDocument,
  CommanderReport, DispatchRecord, Observation, IncidentEvent,
  EventPerspective, DiscussionPoint, PositiveFinding, Lesson, Improvement,
  HumanCorrection, AnalysisRun) with shared enums in `aar/models/enums.py`.
  Pydantic boundary schemas in `aar/schemas/`: `forms.py` (incident creation),
  `ingestion.py` (deterministic DOCX/XLSX parse output), `extraction.py`
  (stage 1 LLM contract — every item requires a verbatim `source_passage`),
  `reconstruction.py` (stage 3 LLM contract — **no exact-timestamp field
  exists on this schema at all**, a structural enforcement of the absolute
  time rule, not just a prompt instruction), `findings.py` (stage 5),
  `lessons.py` (stage 6). `aar/services/incident_service.py` (create/list/
  search/update-status). Minimal Streamlit shell (`app.py` + `aar/ui/`):
  working Screen 1 (archive/search) and Screen 2 (new incident); Screens 3-6
  are explicit placeholders pending Phases 2/3/8 (not faked). 14 unit tests
  passing (`pytest -q`). Manually verified `streamlit run app.py` boots and
  serves HTTP 200.
- Phase 2: `aar/ingestion/commander_docx.py` — template generator
  (`generate_commander_report_template`, also runnable via
  `scripts/generate_template.py`; checked-in output at
  `templates/commander_report_template.docx`) and deterministic parser
  (`parse_commander_report`). Template uses two label/value tables
  (identification; objective-achieved) plus 12 fixed `Heading 1` sections
  matching spec §16 B-H,J-N exactly (`SECTION_HEADINGS`, asserted equal to
  `COMMANDER_REPORT_SECTION_KEYS` at import time so the two can't drift).
  Parsing is fully deterministic — no LLM involved — matching happens on
  normalised heading/label text, not semantics; corrupt files or
  unrecognisable documents raise `CommanderReportParseError`, while
  missing/empty optional content produces non-fatal warnings instead of
  failing. `aar/services/report_service.py::ingest_commander_report` stores
  the original file under `data/uploads/<incident_id>/`, hashes it
  (sha256) for duplicate-upload detection (raises `DuplicateReportError`
  without creating a second row), and persists `SourceDocument` +
  `CommanderReport`. A parse failure still creates the `SourceDocument`
  (status=ERROR, message recorded) so nothing is silently discarded, but no
  `CommanderReport` row is created for it. 17 new tests (11 parser edge
  cases incl. corrupt file, wrong document, missing identification, empty/
  long narrative, unusual punctuation, Dutch uncertainty phrasing preserved
  verbatim; 3 service-level incl. duplicate detection). 28/28 tests passing.
- Phase 3: `aar/ingestion/dispatch_excel.py::parse_dispatch_excel` — header
  detection via a normalised synonym lookup (`TIMESTAMP_SYNONYMS`,
  `EVENT_SYNONYMS`, `UNIT_SYNONYMS`), so column order and exact naming don't
  matter as long as a header is recognisable. Picks the best-matching sheet
  when a workbook has multiple. Blank rows are skipped silently; rows with
  an unparsable timestamp are kept with `is_valid=False` and a message
  (never discarded); a workbook with no recognisable event/description
  column raises `DispatchExcelParseError` with the recognised columns
  listed, an empty sheet returns `records=[]` with a warning instead of
  raising. `aar/services/dispatch_service.py::ingest_dispatch_excel` mirrors
  the commander-report service (dedup by sha256, stores original file,
  persists `DispatchRecord` rows including invalid ones). Introduced shared
  `aar/services/errors.py::DuplicateSourceError` (used by both ingestion
  services — was `DuplicateReportError`, renamed since dispatch uploads hit
  the same duplicate-detection path). Screen 3 (`aar/ui/sources_page.py`)
  now fully wired into `app.py`: upload commander DOCX / dispatch XLSX via
  forms, see per-file parse status and warnings, "Analyse starten" button
  (routes to the still-placeholder analysis screen — pipeline lands in
  Phases 4-7). 9 new tests (7 Excel parser edge cases incl. empty workbook,
  unsupported layout, invalid/missing timestamp, reordered columns; 2
  service-level incl. duplicate detection). 37/37 tests passing. Manually
  re-verified `streamlit run app.py` boots and serves HTTP 200 with the new
  route wired in.
- Phase 4: `aar/llm/base.py::LLMProvider` — template-method abstract class:
  `generate_structured()` handles JSON-parse + Pydantic validation + one
  retry (passing the previous error back to the provider) and raises
  `LLMOutputValidationError` if still invalid; subclasses only implement
  `_complete()` returning raw text. `aar/llm/prompts/system_prompts.py`
  centralises the mandatory safety/reliability rules (spec §55, Dutch,
  verbatim translation of all 11 rules incl. hindsight bias and the
  no-fabricated-timestamps rule) via `build_system_prompt(stage_addendum)`.
  `aar/llm/mock.py::MockLLMProvider` — deterministic rule-based
  implementation covering all four pipeline-stage schemas (extraction,
  reconstruction, findings, lessons); reads a fenced ```json payload block
  from the user prompt (shared convention documented below) rather than
  parsing prose. Explicitly documented as a mechanics-testing tool, not a
  quality stand-in for a real provider. `aar/llm/provider_anthropic.py::
  AnthropicProvider` — forces JSON-schema-matching output via tool-use
  (`tool_choice={"type":"tool", ...}`) so the tool's `input` already matches
  the Pydantic schema; only imports the `anthropic` SDK lazily so it's never
  loaded unless selected. `aar/llm/factory.py::get_llm_provider()` reads
  `AAR_LLM_PROVIDER` and instantiates the right one; raises a clear
  `RuntimeError` if `anthropic` is selected without `ANTHROPIC_API_KEY`
  rather than silently falling back. **Prompt payload convention** (shared
  by every stage's prompt builder in `aar/analysis/*.py`, Phase 5+, and by
  the mock): instructions in prose, then a fenced ` ```json ` block holding
  the stage's structured input data — both the mock and a real provider
  read the same block, keeping them interchangeable. 20 new tests (base
  retry/failure behaviour with a fake provider; mock coverage of all 4
  stages incl. assumption/uncertainty tagging, "never invents a time not in
  the text" / "captures a time that IS in the text" pair, conflict →
  discussion point, went_well → positive finding; factory default/fallback/
  missing-key-raises). **BLOCKED (documented, not faked):** `AnthropicProvider`
  has no automated test against the real API — no `ANTHROPIC_API_KEY` is
  configured in this environment. To verify manually: set
  `AAR_LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` in `.env`, then run
  the pipeline (Phase 5+) once built; a `live_llm`-marked pytest hook can be
  added at that point (pytest.ini already excludes `live_llm` from default
  runs). 49/49 tests passing.
- Phase 5: `aar/analysis/extraction.py::run_extraction` — builds the Stage 1
  prompt (system addendum explicitly restricts `observation_type` to
  human_observation/assumption/uncertainty at this stage — fact/conflict/
  ai_observation are reserved for later stages that can actually establish
  them), calls the provider, and persists one `Observation` row per
  extracted item with `attributed_to` set to the report's display name.
  Idempotent: reruns replace that report's previous AI-generated
  observations rather than accumulating duplicates. 3 new tests.
- Phase 6: `aar/analysis/reconstruction.py::run_reconstruction` (Stage 3) —
  gathers all `FACT/HUMAN_OBSERVATION/ASSUMPTION/UNCERTAINTY`-typed
  observations that have a `commander_report_id` (deliberately excludes
  `CONFLICT`/`AI_OBSERVATION` rows so a later analysis run never re-groups
  its own prior output as if it were fresh source material), includes any
  `HumanCorrection` rows as authoritative context, and asks the LLM to group
  them into `IncidentEvent`s with relative order only. Re-running replaces
  previous AI-generated events (`is_human_added=False`) but never touches
  facilitator-added ones. `aar/analysis/timeline.py::enrich_with_dispatch_times`
  (Stage 4, fully deterministic, no LLM) attaches `exact_time` to an event
  only when its title/summary/units/commanders text has a clear, singular
  best-scoring word-overlap match (≥2 shared significant words, no tie)
  against a valid dispatch record's description — ambiguous or weak matches
  are left unset on purpose. This is a documented conservative heuristic, not
  semantic matching; it will under-attach before it will ever mis-attach.
  7 new tests covering both stages, incl. explicit regression tests that
  reconstruction alone never sets `exact_time`, and that timeline enrichment
  leaves times unset on no-overlap, ambiguous-tie, and invalid-record cases.
  59/59 tests passing.
- Phase 7: `aar/analysis/findings.py::run_findings` (Stage 5) — analyses
  source-type observations + reconstructed events, produces
  `DiscussionPoint`s (a detected conflict becomes `origin_category=conflict`
  describing both sides neutrally, never picking one — spec §29), candidate
  `PositiveFinding`s, and new `AI_OBSERVATION`-typed `Observation` rows for
  patterns no single source names explicitly (spec §30). Idempotent re-run
  (clears prior AI-generated rows of all three kinds, keeps
  `is_human_added=True` ones). `aar/analysis/lessons.py::run_lessons`
  (Stage 6) turns current discussion points + positive findings into
  `Lesson`/`Improvement` proposals, linking each improvement back to its
  lesson by id (looked up via a title→id map built at insert time — not
  stored as raw titles). No owner/deadline/status fields exist on either
  model, structurally enforcing the no-action-tracking rule (spec §44).
  `aar/analysis/pipeline.py::run_analysis` orchestrates all six stages
  behind one `AnalysisRun` bookkeeping row (`stage_reached` updated per
  stage; on any exception the run is marked `ERROR` with the message and
  stage recorded rather than raising — the caller/UI reads the run's status
  instead of needing try/except); skips Stage 1 for reports already
  successfully extracted (cheap re-analysis). Sets `Incident.status =
  ANALYZED` on success. **Bug found and fixed during testing:** `Lesson`
  ORM model's evidence column is `discussion_point_ids` (int ids, matching
  every other evidence-link column in the schema) but `lessons.py` was
  writing `discussion_point_titles` (a leftover from the LLM schema's
  title-based cross-referencing) — caught immediately by the first
  lessons-stage test run (`TypeError: invalid keyword argument`), fixed by
  resolving titles to ids via a lookup built from the incident's current
  discussion points before insert. Also fixed a `datetime.utcnow()`
  deprecation warning surfaced by the same test run. 12 new tests (findings
  incl. idempotency and multi-source AI-observation creation; lessons incl.
  lesson→improvement id linking and idempotency; full pipeline end-to-end
  incl. a no-reports failure path and a rerun-doesn't-duplicate check, plus
  an explicit assertion that no event ends up with a fabricated exact time
  when no dispatch data was supplied). 67/67 tests passing.
- Phase 8-9: `aar/services/aar_service.py` — all facilitator CRUD (edit/add/
  delete events, discussion points, positive findings, lessons,
  improvements; `add_correction` which also bumps `Incident.status` from
  ANALYZED to IN_REVIEW; `default_situation_summary`/`update_situation_summary`;
  `finalize_incident`). Deliberate scope cut, documented here per spec §48's
  "if practical": event merge/split is NOT implemented — add/remove/edit
  covers the facilitator's practical needs for v1 without the extra
  complexity of re-deriving perspectives/evidence links across a merge.
  `aar/services/analysis_service.py` wraps `get_llm_provider()` +
  `run_analysis()` for the UI. `aar/ui/labels.py` centralises Dutch display
  labels for enums so no English/AI terminology leaks into the facilitator
  UI (spec §57, §69). Built out Screens 4-6 for real (replacing the Phase
  1-3 placeholders): `analysis_page.py` (trigger pipeline, show per-stage
  Dutch error on failure), `aar_page.py` (tabbed interactive workspace —
  Overzicht/Incidentverloop/Te bespreken/Positieve punten/Leerpunten per
  spec §46 — with inline edit/delete forms, evidence-inspection expanders,
  per-event/point correction notes, and an explicit "Analyse opnieuw
  uitvoeren" re-analysis trigger fulfilling spec §49), `final_aar_page.py`
  (read-oriented compiled AAR + "Markeer als afgerond"). Removed the now-
  dead `placeholder_page.py`. **UI verification method:** no real browser is
  available in this environment, so the full facilitator flow was verified
  headlessly with Streamlit's own `AppTest` framework (`streamlit.testing.v1
  .AppTest`) rather than skipped — this actually runs `app.py` and clicks
  real widgets, not a mock. Script checked in at `scripts/ui_smoke_test.py`
  (run standalone: `python scripts/ui_smoke_test.py`; not part of the
  pytest suite because `st.cache_resource`/engine singletons make repeated
  AppTest runs inside one pytest process fragile — see note below) walked: archive →
  new incident → create → sources (seeded a commander report directly via
  the service layer, since AppTest can't simulate real file uploads) →
  analysis → run pipeline → interactive AAR (all 5 tabs render without
  exception) → add a correction on an event → re-run analysis (Phase 9 path)
  → final AAR → finalize → back to archive → search finds the finalized
  incident by free text. All steps passed with zero exceptions. 8 new
  pytest unit/integration tests for the service layer (`test_aar_service.py`,
  `test_analysis_service.py`). 74/74 automated tests passing.
  **Known engineering note (not a bug, a documented constraint):** the
  AppTest-based UI walkthrough is not wired into the regular `pytest`
  suite — `st.cache_resource` and the `aar/db/session.py` engine singleton
  are process-global, so a second `AppTest.from_file()` run in the same
  pytest process can silently reuse a previous run's cached engine/db
  even after `AAR_DB_PATH` changes, unless internals
  (`get_settings.cache_clear()`, `aar.db.session._engine = None`,
  `st.cache_resource.clear()`) are reset by hand first. Documented here so
  a future contributor doesn't "fix" a flaky repeat run by disabling
  caching in production code — the fix belongs in the test harness, not
  the app.
- Phase 11: `fixtures/synthetic_incident/build_fixture.py` — a fictional
  woningbrand (Kerkstraat 45, Antwerpen, 2026-03-04, all names/callsigns
  invented) with 4 commander reports (P12 Adjudant Janssens, P21 Sergeant
  Willems, O01 Luitenant Peeters, P34 Onderluitenant De Smet) and 1 dispatch
  sheet, generated on demand via the real template generator + python-docx/
  pandas rather than checked in as binary files (keeps the fixture
  auto-consistent with template changes). Engineered to contain spec §63's
  test conditions A/B/D/F/G/H/I/J; `tests/integration/test_synthetic_incident.py`
  asserts each one against the full pipeline output. **Conditions C
  (cross-report conflicting-order detection) and E (unlabelled positive
  coordination pattern) are explicitly marked UNVERIFIED for the mock
  provider** — both require genuine cross-report semantic comparison, which
  the deterministic mock cannot do by design (documented in Phase 4/7 notes
  already); a dedicated skipped test
  (`test_synthetic_incident_conditions_c_and_e_require_real_provider`)
  documents this rather than silently omitting the check, with instructions
  to verify manually via `AnthropicProvider`. `tests/integration/
  test_hallucination.py` adds spec §65's adversarial checks (no cause
  mentioned → none fabricated; no victim mentioned → none invented;
  conflicting accounts from two reports → both preserved, neither silently
  dropped/resolved; no narrative time at all → zero events get an exact
  time). **Real bug found and fixed by this fixture:**
  `aar/ingestion/dispatch_excel.py` was parsing every timestamp with
  `pandas.to_datetime(..., dayfirst=True)` unconditionally; pandas applies
  `dayfirst` even to unambiguous ISO `YYYY-MM-DD` strings, which silently
  turned `2026-03-04` (4 March) into `2026-04-03` (3 April) — a real
  timestamp-corruption bug that the earlier Phase 3 unit tests (which only
  checked `.hour`, never the date) didn't catch. Fixed with
  `_parse_timestamp_value()`: `dayfirst` is now only applied to strings that
  don't already match an unambiguous `^\d{4}-\d{1,2}-\d{1,2}` ISO prefix (or
  are already a real datetime/Timestamp, which has no ambiguity at all).
  Added a regression test for the exact failure
  (`test_parse_iso_timestamp_not_day_month_swapped`) plus a test confirming
  genuinely ambiguous European `DD/MM/YYYY` dates still parse correctly.
  This directly matters for the absolute-time rule (spec §22) — a
  corrupted-but-present timestamp is arguably worse than a missing one,
  since it looks authoritative. 17 new tests. 92/93 tests passing (1
  documented skip, not a failure).
- Phase 12: full regression pass. Ran the suite with
  `-W error::DeprecationWarning` — zero warnings anywhere. Ran `pyflakes`
  across `aar/`, `app.py`, `scripts/`, `fixtures/`, `tests/` — the only
  real findings were unused imports left over from earlier edits (cleaned
  up in `aar/services/aar_service.py` and five test files); the
  "undefined name" hits in `aar/models/*.py` are false positives from
  pyflakes not understanding SQLAlchemy's `Mapped[list["ClassName"]]`
  string-based forward references (a standard, correct SQLAlchemy 2.0
  pattern — resolved at runtime once every model module is imported via
  `aar/models/__init__.py`), not real bugs. Verified the Anthropic SDK's
  exception hierarchy directly (`anthropic==0.122.0`): `APIConnectionError`,
  `APITimeoutError`, `RateLimitError`, `APIStatusError`,
  `APIResponseValidationError`, and `AuthenticationError` all subclass
  `AnthropicError` — widened `provider_anthropic.py`'s except clause from
  `anthropic.APIError` to `anthropic.AnthropicError` so no real-provider
  failure mode (timeout, rate limit, auth, connection) can escape as an
  unhandled exception; all of them now surface as an `AnalysisRun` with
  status=ERROR and a Dutch message, same as every other failure path.
  Added: a pipeline test proving a mid-run provider failure (findings stage)
  is recorded on the `AnalysisRun` with the correct `stage_reached`, doesn't
  mark the incident ANALYZED, and — importantly — does NOT discard the
  already-committed earlier-stage work (extraction/reconstruction results
  survive; this is a deliberate architectural choice, not a bug: each stage
  commits independently, so a later failure doesn't roll back earlier
  progress, consistent with the idempotent/resumable design used for
  re-analysis). Added a cascade-delete test confirming deleting an
  `Incident` removes all its `SourceDocument`/`CommanderReport`/`Observation`
  rows (validates the `cascade="all, delete-orphan"` relationships actually
  work against SQLite, not just that they're declared). 4 new tests.
  94/95 tests passing (1 documented skip). Re-ran the full headless UI
  smoke test (`scripts/ui_smoke_test.py`) after all hardening changes —
  still passes end to end.
- **Phase 14 (post-handoff, user-requested):** after seeing the finished
  Streamlit MVP running, the user asked for a "modern, lighter,
  professional" interface, explicitly ruling out Streamlit/Gradio, and
  asked for a recommendation aimed at looking good presented to colleagues.
  Presented three options (NiceGUI; FastAPI+HTMX+Tailwind; FastAPI+React);
  user asked for a recommendation, so **FastAPI + Jinja2 + Tailwind (CDN) +
  a little vanilla JS** was chosen and built — full design control for a
  genuinely polished look without a Node/React build pipeline, and the
  entire existing `aar/services/*` / `aar/analysis/*` / `aar/models/*`
  business logic layer carries over completely unchanged (only the view
  layer was rebuilt, proving out the original layering decision from
  Phase 1). New `aar/web/` package: `app.py` (FastAPI factory + lifespan-
  based DB init, replacing the deprecated `@app.on_event`), `deps.py`
  (per-request DB session + shared `incident_or_404` helper), `flash.py`
  (stateless flash messages via URL query params — no session/cookie
  middleware needed for a single-operator local tool), `templating.py`
  (Jinja2 env + Dutch-formatting filters, reusing `aar/ui/labels.py`
  unchanged), `templates/_icons.html` (hand-authored inline SVG icon set —
  no icon-font CDN dependency), `templates/_components.html` (badge/empty-
  state/evidence-disclosure macros shared across pages), `templates/base.html`
  (sidebar-nav shell, Tailwind config with a custom `brand` color + Inter
  font via Google Fonts CDN), and one route module + template set per
  screen (`archive`, `incidents` [new-incident form], `sources`,
  `analysis`, `interactive_aar` [5 tabs: Overzicht/Incidentverloop/Te
  bespreken/Positieve punten/Leerpunten, each a real page-load, not a JS
  partial-swap — deliberately simple and robust over SPA-like polish given
  the time budget], `final_aar`). Root `app.py` now just re-exports
  `aar.web.app:app`; run with `uvicorn app:app`. Removed the six Streamlit
  page modules from `aar/ui/` (kept only `labels.py`, which the new
  templates still import), removed `streamlit` from `requirements.txt`, and
  removed the now-obsolete `scripts/ui_smoke_test.py` (Streamlit `AppTest`-
  based). **Two real bugs found and fixed while building this:** (1) module
  name collision — a route module was named `aar.py`, which as
  `aar.web.routes.aar` silently shadowed the top-level `aar` package name
  inside `app.py`'s local namespace after `from aar.web.routes import aar`;
  renamed to `interactive_aar.py` before it could cause a real failure. (2)
  Starlette/FastAPI treats an **empty-valued form field as absent** for a
  required `Form(...)` parameter — confirmed independently via raw `curl`
  against the running dev server, not just the test client — so a real user
  submitting a blank required text input (e.g. "Locatie" on the new-incident
  form) got a raw FastAPI 422 JSON error instead of the intended Dutch
  validation message. Fixed everywhere by switching required user-typed
  text fields from `Form(...)` to `Form("")` and validating blankness
  explicitly in the handler (`_require_title()` helper in
  `interactive_aar.py`; inline check in `incidents.py`) — now surfaces as a
  normal flash-message error on the correct page. New
  `tests/integration/test_web_app.py`: the full facilitator flow driven
  through FastAPI's `TestClient` against the real ASGI app (not mocked) —
  create → upload 4 reports + dispatch → analyse → all 5 AAR tabs → add
  correction → re-analyse → finalize → archive search finds it — plus the
  empty-location-rejected and duplicate-upload-warning regression cases.
  **Visual verification:** no real browser in this environment, so
  installed Playwright + Chromium (one-time, not a project dependency) and
  captured full-page screenshots of all 9 screens against the seeded demo
  incident; inspected them directly (not just asserted no-exception) to
  confirm the sidebar/cards/badges/tabs actually render as designed in both
  the archive list and every AAR tab. Checked in as
  `scripts/screenshot_smoke_test.py` (parameterised by base URL/incident id)
  for repeatable use — documented in `HANDOFF.md` §7 as an optional install
  since Playwright's browser download is heavy. 110/111 tests passing (1
  documented skip, same as before — this phase didn't touch pipeline logic).
- **Phase 15 (post-handoff, user-requested):** user asked, mid-rewrite, for
  the ability to attach photos/plans and asked where they'd surface in the
  AAR — answered (general incident-level upload, shown in an "Overzicht"
  gallery, optionally linkable to a specific incident moment in
  "Incidentverloop"), then asked to "just build it in". Not in the original
  spec — an explicit, scoped, user-approved addition, not silent scope
  creep. Extended `SourceDocument` (rather than a new table) with
  `SourceDocumentType.PHOTO_OR_PLAN`, a nullable `caption` field, and a
  nullable `event_id` FK to `incident_events` — photos are uploaded/stored/
  deduplicated through the exact same mechanism as reports/dispatch sheets,
  just without a parsing step (`parse_status` is set straight to `PARSED`).
  Deliberately **not** fed to the AI pipeline — pure reference material, an
  explicitly scoped decision recorded here so it isn't mistaken for an
  oversight later. New `aar/services/media_service.py` (`ingest_photo`
  with an extension allowlist — `.jpg/.jpeg/.png/.webp/.pdf` — and the same
  sha256 dedup pattern as `report_service.py`; `list_photos`; `set_caption`;
  `link_to_event`/unlink via `event=None`; `delete_photo`, which removes
  both the DB row and the file on disk). `aar/services/aar_service.py::
  delete_event` updated to null out any photos' `event_id` before deleting
  the event (SQLite doesn't enforce FK constraints by default, so this was
  a real dangling-reference risk, not just tidiness — caught by writing
  `test_deleting_event_unlinks_but_keeps_photo` before it could ship as a
  latent bug). New `aar/web/routes/media.py`: upload, serve
  (`GET .../media/{doc_id}`, content-type inferred via `mimetypes`),
  caption, link (photo id now passed in the form body rather than the URL
  path — the first draft tried rewriting the form's POST target with inline
  JS from a `<select>`, which was fragile; moved the id into the request
  body instead and deleted the JS), and delete. UI: a third upload card on
  the Sources screen (thumbnail grid, inline-editable caption, delete);
  an "Beeldmateriaal" gallery on the AAR Overzicht tab; per-event thumbnail
  strip + an unlinked-photos picker on the Incidentverloop tab. 7 new unit
  tests for `media_service.py` (incl. the unlink-on-event-delete case and
  an unsupported-extension rejection) plus photo-upload/link/serve coverage
  folded into `test_web_app.py`'s full-flow test. 110/111 tests passing.
- **Phase 16 (post-handoff, user-requested):** user feedback after seeing
  Phase 14's first pass: "looks like it was built by a kid learning to
  program" and "I work at a very professional organisation." Full visual
  redesign of the design system in `aar/web/templates/base.html` +
  `_components.html` + a sweep across every template: replaced the generic
  Tailwind-tutorial indigo palette with a restrained monochrome `ink` scale
  (near-black primary buttons/active states) plus a single muted desaturated
  `accent` steel-blue for focus rings/links, removed the 🚒 emoji brand mark
  in favour of a small geometric SVG mark, switched the sidebar to dark
  (`ink-950`) with a subtle left-accent active state instead of a filled
  colour pill, tightened border radii (`rounded-2xl`→`rounded-lg`
  everywhere) and the whole typographic scale (custom `text-[13px]`-family
  sizes instead of Tailwind's default `text-sm`/`text-xs`), and rebuilt the
  archive page (was mostly dead whitespace below a single row) with a stats
  row and a proper table-style list. Verified via fresh Playwright
  screenshots, inspected directly, not just asserted no-exception.
- **Phase 17 (post-handoff, user-requested):** user feedback on content
  quality after the redesign: "the results are quite poor", "who said this
  and when isn't shown", "there's no overview of which commander has which
  callsign/unit". Three concrete fixes, not just polish:
  1. **Mock content duplication bug**: `DiscussionPointCandidate`/
     `PositiveFindingCandidate.title` was literally `content[:80]` while
     `.description` was the same `content` unsliced — for any observation
     under 80 characters these were identical, which is exactly the
     "title equals the text" complaint. Fixed in `aar/llm/mock.py` with
     `_headline()` (a genuinely short label, first ~8 words) and
     `_attributed_quote()` (full quote prefixed with the commander's display
     name, e.g. `P12 (1ste Hulpcentrum) — Adjudant Janssens: „...”`).
     `aar/analysis/findings.py::build_findings_payload` now includes
     `attributed_to` per observation so the mock has it to work with.
  2. **Attribution surfaced in the UI, not just embedded in text**: added
     `_components.html::attributed_to()` macro (person icon + name) shown
     directly on every discussion-point/positive-finding card in
     `_bespreken.html`/`_positief.html`, plus the linked event's title
     ("Moment: ...") and a colour-coded left border by origin category
     (`templating.py::ORIGIN_BORDER_CLASSES`) — previously attribution only
     existed inside the collapsed "Bewijs bekijken" disclosure.
  3. **Commander roster added** to the Overzicht tab (`aar/web/templates/
     aar/_overzicht.html`): callsign / unit / rank+surname / objective-
     achieved per report — this existed as data (`CommanderReport`) since
     Phase 2 but was never surfaced as a standalone roster anywhere.
     Discussion points and positive findings are now also sorted by their
     linked event's `order_index` (the tool's only legitimate notion of
     "chronological" — relative narrative order, never a fabricated clock
     time) instead of arbitrary insertion order.
  **A real regression was introduced and caught during this work**: making
  `ai_summary` show real quoted content (fix 1) broke the Stage 4
  dispatch-matching heuristic (`aar/analysis/timeline.py`) — richer event
  text meant generic fire-incident vocabulary ("eerste", "verdieping")
  started coincidentally overlapping with unrelated dispatch rows, and the
  demo went from 1/12 events correctly timestamped to 9/12, most of them
  spurious. Root cause: the matcher used `title + ai_summary + involved_*`
  as its text, so its input size was no longer bounded once `ai_summary`
  became a full paragraph. Fixed by an architectural decoupling rather than
  threshold tuning: matching now uses **only the event title**, never
  `ai_summary` or `involved_commanders`/`involved_units` (the latter are
  proper nouns that pad the word count without ever genuinely matching
  dispatch phrasing) — what's *displayed* to the facilitator and what's
  *used for matching* are deliberately different things now. The overlap
  requirement is a ratio of the *shorter* side's word count
  (`max(2, ceil(min(len(event_words), len(dispatch_words)) * 0.66))`) rather
  than a fixed count, since a short title (1-3 words) can never satisfy a
  requirement sized off a longer dispatch description. Added a dedicated
  regression test (`test_enrich_ignores_generic_overlap_in_long_ai_summary`)
  that fails if this ever regresses again. Verified via `scripts/
  run_synthetic_demo.py` logs (back to the expected 1/12) and fresh
  screenshots, not just the test suite. 111/112 tests passing (1 documented
  skip).
- **Started, not finished: single shared-password login gate.** User asked
  "only the AAR leader should be able to get in, right?" — correctly noted
  there is no authentication at all (an explicit v1 scope exclusion per the
  original spec). Began implementing an opt-in gate: `Settings.access_password`
  / `Settings.session_secret` (auto-generated and persisted to
  `data/.session_secret`, gitignored, if not set via env — so restarts don't
  silently log everyone out), `aar/web/routes/auth.py` (`/login`, `/logout`,
  constant-time password comparison via `hmac.compare_digest`), and
  `aar/web/templates/login.html` (matches the Phase 16 design system, no
  sidebar). **Not yet wired into `aar/web/app.py`** — no `SessionMiddleware`,
  no auth-gate middleware, no `auth.router` registration, so none of this
  code is reachable or active yet. Fully inert in its current state (doesn't
  affect any existing route or test). Needs: `SessionMiddleware` added
  before an `@app.middleware("http")` gate that checks `request.session`
  and redirects unauthenticated requests to `/login` when `settings.
  auth_enabled` is true; a "Uitloggen" link in the sidebar; a test covering
  gated-vs-open behaviour; `.env.example`/HANDOFF.md documentation (the
  `.env.example` entries for `AAR_ACCESS_PASSWORD`/`AAR_SESSION_SECRET`
  were already added). Pick this back up before considering it done.
- **Phase 18 (post-handoff, user-requested):** further content-structure
  feedback: "the situation summary reads like a little story — whose point
  of view is it from?", "lots of duplicates in the lessons", "needs a short
  summary per commander too, organised in boxes, not just a flat list."
  Three more fixes:
  1. **Unattributed narrative voice**: the situation summary/event summaries
     joined every commander's perspective text into one run-on paragraph
     with no indication of who said which part — reads as one coherent
     account when it's actually several, possibly divergent, ones stitched
     together (undermines the whole multi-perspective-preservation
     principle). Fixed in `aar/llm/mock.py::_reconstruction`: each
     commander's segment is now prefixed with their display name and
     segments are joined with a visible `  |  ` separator.
  2. **Lesson/improvement duplication**: the mock emitted one lesson +
     one improvement per discussion point with no grouping — 9 discussion
     points meant 9 near-identical "Leerpunt: ..." entries. `_lessons()`
     now clusters by `origin_category` first (one lesson per *theme*, e.g.
     "Onzekerheid (7x aangetroffen)", not per individual quote), showing up
     to 3 representative attributed examples plus a count of the rest.
     Fixed a duplicate-label rendering bug found along the way — the
     "Mogelijke verbetering: ..." prefix was being added both by the mock
     (in the title) and again by the template, so the linked-improvement
     line under a lesson read "Mogelijke verbetering: Mogelijke
     verbetering: ...".
  3. **Commander overview restructured into a proper card grid**
     (`aar/web/templates/aar/_overzicht.html`): was a flat stacked list with
     just identity + one narrative excerpt; now a 2-column grid of cards,
     each with a callsign avatar mark, a colour-coded objective-achieved
     badge (`templating.py::OBJECTIVE_BADGE_CLASSES`), and a labelled
     mini-grid of key template answers (`commander_section_fields`:
     Waarnemingen/Inschatting/Beslissing/Resultaat/Wat ging goed/Wat ging
     minder goed, `line-clamp-2`'d) with a "Volledig verslag lezen"
     disclosure underneath showing every section verbatim. This is the
     direct answer to "I don't see who had which callsign/unit" combined
     with "I want their story too", done as one coherent per-commander unit
     rather than two separate flat lists.
  All three fixes are mock-output/UI-structure fixes, not something that
  requires a real LLM — verified via `scripts/run_synthetic_demo.py` +
  fresh Playwright screenshots (inspected directly), full suite green.
  111/112 tests passing (1 documented skip, unrelated).
- **Phase 19 (post-handoff, user-requested):** "Definitieve AAR is a mess,
  a run-on story, observations run together — one commander says 'I see
  smoke', another already describes an attack underway, that can happen if
  he arrived later but it's odd to read like that." Root cause: the
  read-only Final AAR page rendered each event's flattened `ai_summary`
  string as one `<p>` — even after Phase 18 attributed each segment inline,
  multiple commanders' accounts of the same category-bucket ("Waarnemingen
  bij aankomst") still read as one run-on paragraph, and — unlike the
  interactive AAR — this page has no edit step to clean it up before a
  facilitator reads it. Fixed properly rather than re-formatting the same
  string: `final_aar.html`'s Incidentverloop section now renders
  `event.perspectives` directly (already-structured per-commander data that
  existed since Phase 8 and was already used correctly in the interactive
  AAR's "Perspectieven" disclosure) as visually separate attributed lines,
  falling back to `ai_summary` only for events with no perspectives (manually
  facilitator-added ones). Added an explanatory caption ("different
  commanders may have a different perspective on the same moment — shown
  separately on purpose, not merged into one story"). Applied the same fix
  to `aar_service.py::default_situation_summary` (used both as the Overzicht
  tab's editable draft and, if left unedited, the Final AAR's "Situatie"
  text) — rebuilt to group per incident moment with each commander's line
  separately attributed, instead of joining raw `ai_summary` strings.
  **Follow-up user request in the same exchange**: "a big overview with
  those [commander] boxes like at the start is great — the LLM should then
  try to sketch the situation from all the boxes together, roughly, only
  the crucial things." Explicitly named as a real-LLM-only capability (mock
  cannot judge "crucial" — no semantic importance-ranking is possible
  without genuine language understanding), so implemented the deterministic
  version of that idea instead of pretending to: `default_situation_summary`
  now filters to only the decision-relevant categories
  (`_CRUCIAL_SUMMARY_TITLES` = Beslissing/Doelstelling/Resultaat/Wat ging
  goed/Wat ging minder goed — a fixed category allowlist, not importance
  judgement) plus any facilitator-added event, instead of dumping all ~12
  category buckets. Also fixed a small but real content-quality bug found
  while reviewing the output: commander reports that leave an optional
  section as "-" (this fixture's convention for "nothing to report") were
  being extracted as a literal one-character "observation", cluttering
  every downstream view with stray "P34: -" lines —
  `aar/llm/mock.py::_split_sentences` now filters lines/sentences that are
  just punctuation/dashes before they ever become an `Observation`.
  111/112 tests passing (1 documented skip, unrelated); verified via fresh
  screenshots of the Final AAR page specifically (both the "Situatie"
  section and "Incidentverloop"), not just the test suite.
- **Phase 20 (post-handoff, user-requested):** feedback on the Phase 18
  commander card grid: wanted "a bit clearer with colour, professional but
  not boring and not flashy", every field fully readable (the `line-clamp-2`
  truncation was cutting fields off mid-sentence), and "let the LLM
  summarise the story so everything is visible in the card at a glance."
  Fixed: (1) added `templating.py::OBJECTIVE_BORDER_CLASSES` — a
  `border-l-4` accent per card colour-coded by that commander's
  objective-achieved status (emerald/amber/rose/slate), meaningful colour
  tied to actual content, not decoration; (2) removed `line-clamp-2` and
  switched the card body from a cramped 2-column grid to a single column so
  every field's full text is readable, no truncation; (3) for "let the LLM
  summarise at a glance" — named this explicitly as a real-LLM-only
  capability again (genuine synthesis needs judgement the mock doesn't
  have), and built the honest deterministic version instead: a one-line
  "Besliste: ... Resultaat: ..." gist (first sentence of each) in a
  highlighted band at the top of each card, visually distinct from the full
  fields below so it doesn't pretend to be more than what it is. Also
  caught and fixed the same "-"-placeholder-leaking-through bug from
  Phase 19, in a second code path: the commander cards read
  `CommanderReport.raw_sections` directly (the deterministic DOCX-parse
  output) rather than going through the mock's `_split_sentences` filter,
  so empty "-" sections were still appearing verbatim there. Added a
  reusable Jinja test (`templates.env.tests["placeholder_text"]`) instead of
  duplicating the regex, used in both the compact and full-report views.
  111/112 tests passing (1 documented skip, unrelated); verified via fresh
  screenshots.
- **Phase 21 (post-handoff, user-requested): first real-provider run,
  found/fixed real bugs, dedup + UX cleanup.** The user obtained a real
  `ANTHROPIC_API_KEY` and asked to run the actual pipeline for the first
  time (`AAR_LLM_PROVIDER=anthropic`, model `claude-sonnet-5`). This
  surfaced two genuine reliability bugs that the mock provider could never
  have exposed:
  1. **`max_tokens` truncation, silently swallowed.** `AnthropicProvider`
     defaulted to `max_tokens=4096`; the reconstruction stage on the demo
     incident (47 observations) needed 4057 of them — a single larger
     incident would silently truncate mid-JSON. Worse, `generate_structured`'s
     retry path (`aar/llm/base.py`) asks the model to "try again", and the
     model's second attempt returned syntactically *valid* JSON with an
     empty `events: []` rather than failing loudly — Pydantic validation
     passed, so the pipeline reported `SUCCESS` with a silently empty
     result. Fixed by raising the default to `max_tokens=16000`
     (`aar/llm/provider_anthropic.py`).
  2. **Real model was too literal about "never invent things."** The
     findings and lessons stages consistently returned empty
     `discussion_points`/`positive_findings`/`lessons` even with rich input
     data (7 uncertainty + 2 assumption observations) — not truncation
     (output stayed well under the token limit), the model was
     over-applying core safety rule 5 ("if evidence is insufficient, say so
     explicitly") to *interpretive* judgement calls it was actually asked
     to make. Fixed by adding explicit addenda to `aar/analysis/findings.py`
     and `aar/analysis/lessons.py` clarifying that rule 5 is about
     fabricating *facts*, not about declining to synthesize from
     already-labelled input, plus a "returning an empty list when the input
     clearly supports output is a mistake" instruction. Verified by direct
     `count_tokens`/`messages.create` calls before and after, then by a
     full pipeline run through the running app.
  Separately, the user reported real duplication in the output: the same
  point from two commanders' reports was appearing as two near-identical
  `discussion_point`/`positive_finding`/`lesson` entries instead of one.
  The schemas already supported multi-report attribution
  (`observation_ids: list[int]`, and `_components.html::attributed_to`
  already de-duplicates/joins names) — the gap was purely in the prompt:
  `findings.py`'s addendum now explicitly instructs merging waarnemingen
  from *different* `commander_report_id`s that describe the same
  underlying point into one entry with combined `observation_ids`, and
  `lessons.py`'s addendum instructs clustering by theme instead of one
  near-identical lesson per discussion point. Verified live: a positive
  finding ("SO tijdig aangetroffen en overgedragen aan MUG") now correctly
  attributes to all three commanders who reported it in one entry.
  Also added, per explicit user request, output-style rules to the shared
  system prompt (`aar/llm/prompts/system_prompts.py`): titles/summaries
  must be short "telegram style" (full rationale given to the model: the
  detailed explanation happens verbally during the AAR meeting itself, this
  text is a scannable index, not the full report) with the user's exact
  worked example, plus fixed domain abbreviations (HD/LD/SAR/SO, and
  V+number for floors, e.g. V2).
  Then, reviewing the resulting real output end-to-end (screenshots of
  every screen) surfaced three more issues, unrelated to the LLM:
  - **`default_situation_summary` was permanently empty for any real
    analysis** (previously listed below as spec §63 "UNVERIFIED" — now
    verified, and found broken). It filtered incident events by
    `event.title in _CRUCIAL_SUMMARY_TITLES`, a set of bare category labels
    ("Beslissing", "Resultaat", ...) — that only ever matched because the
    *mock* happens to title every event after its category. A real LLM
    gives events specific, content-derived titles ("Beslissing opschaling
    en zoekactie P34") that never equal a bare label, so the filter matched
    zero events on every real run. Fixed in `aar/services/aar_service.py`
    to instead check each event's linked `Observation.category` (via
    `observation_ids`) — semantically correct and works for both providers
    (regression test added:
    `test_default_situation_summary_matches_on_observation_category_not_title`).
  - Description `<textarea rows="2">` fields in `_bespreken.html`,
    `_positief.html`, `_leerpunten.html` clipped real (longer) LLM output
    mid-sentence with no visual indication more text existed. Bumped to
    `rows="5"` for the pre-filled fields (the empty "add manually" forms
    were left at `rows="2"`, they start empty).
  - The commander-card body on the Overzicht tab showed the exact same
    beslissing/resultaat sentences three times over (gist band → full
    WAARNEMINGEN/INSCHATTING/BESLISSING/RESULTAAT/WAT GING (MINDER) GOED
    block → "Volledig verslag lezen" disclosure repeats all six again).
    Trimmed the always-visible block to just WAT GING GOED/MINDER GOED
    (`commander_section_fields[-2:]`) — the two fields not already covered
    by the gist and most directly relevant to an AAR — moving
    waarnemingen/inschatting/beslissing/resultaat exclusively into
    "Volledig verslag lezen". Also gave the Definitieve AAR page's
    "Situatie" section a helpful empty-state message with a direct link
    instead of a bare "—" when nothing has been saved yet.
  112/112 tests passing (1 documented skip, unrelated — see below).
  Switched back to `AAR_LLM_PROVIDER=mock` at the user's explicit request
  before further UI iteration, to stop spending API budget on repeated
  re-analysis runs while tuning the interface.
- **Phase 22 (post-handoff, user-requested): dedicated narrative-synthesis
  stage; free-form report fallback.** Even after the Phase 21 category-match
  fix, the user pushed back that the situation summary was still "loose
  stories, not a global overview" — correctly: `default_situation_summary`
  is, and always was, a deterministic per-event/per-commander *listing*,
  never real synthesis (documented as a real-LLM-only capability since
  Phase 19, but never actually built). Built it properly this time instead
  of patching the listing again:
  - New Stage 7 (`aar/analysis/narrative.py`, `SituationNarrativeOutput` in
    `aar/schemas/narrative.py`): takes every reconstructed event with all
    its commander perspectives, chronologically, and asks for ONE flowing
    prose account — merge where sources complement each other, but
    explicitly name (not silently resolve) genuine disagreements, grounded
    only in given data. Result stored in a new
    `Incident.ai_situation_narrative` column (separate from the
    facilitator-owned `situation_summary` field — same "AI proposes, human
    finalises" pattern as everything else in this tool).
  - `MockLLMProvider._narrative()` added for schema-dispatch completeness,
    but deliberately kept as an honestly-labelled non-synthesis fallback
    (module docstring is explicit about this) — the mock has no semantic
    understanding to actually merge accounts with.
  - Wired into `run_analysis()` after the lessons stage; both AAR routes
    now resolve the summary as `situation_summary or ai_situation_narrative
    or default_situation_summary(...)` (facilitator edit > AI synthesis >
    old deterministic listing, in that priority order).
  - Added `ai_situation_narrative` column via a manual `ALTER TABLE` on the
    local dev DB (no migration framework in this project — `create_all`
    only creates missing tables, not missing columns on an existing one;
    note this for any future schema change against the existing
    `data/aar.db`).
  - Verified end-to-end via the mock provider (confirms the wiring/DB/route
    priority all work); genuine prose-synthesis *quality* is explicitly
    unverified until run once against the real provider — see §9.
  Separately, the user shared a realistic commander-report example that
  used none of the template's section headings at all (free-form prose
  with the writer's own headers). Confirmed this would have hit the
  existing hard rejection (`CommanderReportParseError`, "geen enkele sectie
  herkend"). Fixed `aar/ingestion/commander_docx.py::_extract_sections` to
  fall back to capturing the whole document as one passage under the
  "narrative" section key (→ `ObservationCategory.ACTION`) instead of
  rejecting the upload, with an explicit warning shown to the facilitator —
  the real-provider extraction stage classifies each item's category from
  its content already, not from which section it arrived in, so it can
  still do useful work on this fallback text (the mock's cruder
  section-derived categorisation loses granularity here, an accepted
  mock-only trade-off). Still raises `CommanderReportParseError` for a
  genuinely empty/unreadable document. The user then clarified they will
  enforce template compliance operationally going forward, so this is a
  safety net rather than the primary path — no further investment planned
  here unless it resurfaces.
  115/115 tests passing (1 documented skip, unrelated).

## 9. Open Work / Known Bugs / Blocked / Unverified / Technical Debt

- **RESOLVED in Phase 21** (previously listed here as unverified/blocked):
  the real `AnthropicProvider` path has now been exercised end-to-end
  multiple times against the live API (model `claude-sonnet-5`), including
  spec §63 condition C (conflicting order between P12/P21 was correctly
  surfaced as a `discussion_point` with `origin_category=conflict`,
  attributed to both commanders) and condition E (an unlabelled positive
  pattern — the SO handoff — was correctly surfaced as a `positive_finding`
  attributed to all three involved commanders). Two real reliability bugs
  were found in the process and fixed — see Phase 21 above.
- **Still open:** the merge/dedup and conciseness prompt instructions
  (Phase 21) have only been spot-verified on the one synthetic demo
  incident, across a handful of real runs — not covered by an automated
  regression test (that would require either a recorded API fixture or
  accepting non-determinism in CI, neither done here). If duplication
  reappears on a different incident, check `aar/analysis/findings.py` and
  `aar/analysis/lessons.py`'s addenda first.
- **UNVERIFIED (by design, needs real provider):** Stage 7 narrative
  synthesis (`aar/analysis/narrative.py`, Phase 22) has only been exercised
  against the mock provider so far, which — by design, see the module's
  docstring — cannot actually produce a synthesised narrative, only an
  honestly-labelled concatenated fallback. The user explicitly asked to
  hold off on further real-API spend while iterating on the UI; run one
  real analysis (`AAR_LLM_PROVIDER=anthropic`) to verify the actual prose
  synthesis quality before considering this feature done.
- **Technical debt, accepted for v1:** pipeline stages commit independently
  rather than the whole `run_analysis()` call being one transaction — a
  mid-run failure leaves earlier stages' results persisted rather than
  rolling everything back. This is intentional (matches the idempotent/
  resumable re-analysis design, see Phase 5-7 notes) but is worth knowing
  if this is ever generalized beyond a single-operator local tool.

## 10. Important Implementation Notes

- Dutch is the UI language; internal identifiers/code/enums are English.
- Standard commander report sections map 1:1 to spec §16 A–N; do not rename
  or reorder without updating both the DOCX template generator and the
  parser's heading-matching table together.
- Uncertainty/assumption phrase lists (spec §27/§28) live in
  `aar/analysis/prompts` as an explicit reference list fed to the LLM, plus a
  deterministic keyword pre-tagger used only as a test aid, not as the
  primary detector (semantic detection is the LLM's job; keyword matching
  alone is a known weak signal and is documented as such).

## 11. Definition of Done (spec §71) — final checklist

| Requirement | Status |
|---|---|
| Application starts | DONE — `uvicorn app:app` (post-Phase-14 FastAPI UI), verified clean-slate boot to HTTP 200, via `TestClient`-driven full-flow tests, and via Playwright screenshots of every screen |
| Incident can be created | DONE — Screen 2, tested |
| Multiple commander reports can be uploaded | DONE — Screen 3, tested with 4 in the golden fixture |
| Reports are parsed | DONE — deterministic DOCX parser, 11 edge-case tests |
| Commander identity is recognised | DONE — identification table parsing, `display_name` property |
| Dispatch Excel can be uploaded | DONE — Screen 3 |
| Dispatch data is parsed | DONE — defensive header-synonym parser, 9 edge-case tests |
| AI pipeline can process structured reports | DONE — 6-stage pipeline, mock provider by default |
| Chronological incident view is generated | DONE — Screen 5 "Incidentverloop" tab |
| Reliable important timestamps are displayed | DONE — dispatch enrichment (Stage 4), conservative heuristic |
| Missing times remain missing | DONE — structural (no exact-time field in the reconstruction LLM schema) + explicitly tested |
| Assumptions can be identified | DONE — spec §63-A, golden fixture test passes |
| Uncertainty can be identified | DONE — spec §63-B, golden fixture test passes |
| Conflicts can be surfaced | PARTIAL — schema/model/UI fully support it (origin_category=conflict); **mock provider cannot detect it** (needs real LLM, documented UNVERIFIED) |
| Multiple perspectives are preserved | DONE — `EventPerspective` per commander per event |
| AI can propose positive findings | DONE — explicit went-well content confirmed; implicit/unlabelled patterns need real LLM (documented) |
| AI can propose discussion points | DONE |
| AI can propose lessons | DONE |
| AI can propose improvements | DONE, linked to their source lesson |
| Evidence remains traceable | DONE — every finding carries `observation_ids` back to source passages |
| Facilitator can correct content | DONE — edit/add/delete on every entity type in Screen 5 |
| Re-analysis can incorporate correction | DONE — spec §49, full pipeline re-run with corrections as authoritative context, tested via UI smoke test |
| Final AAR can be stored | DONE — Screen 6, `finalize_incident` |
| Archive can be searched | DONE — Screen 1, date/type/free-text filters |
| Synthetic fixture works | DONE — Phase 11, 12/13 golden conditions verified (2 documented UNVERIFIED) |
| Automated tests pass | DONE — 94 passed, 1 documented skip |
| No known critical bug remains undocumented | DONE — one real bug found (dispatch date parsing) and fixed with a regression test; nothing else outstanding |
| Setup instructions work | DONE — followed HANDOFF.md §3-5 verbatim during this build |
| PROJECT_STATE.md is current | DONE — this document |
| HANDOFF.md exists | DONE |
