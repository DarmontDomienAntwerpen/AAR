# PROJECT_STATE.md — Fire Service AAR Tool v1

Living engineering source of truth. Read before starting a phase; update after
completing or materially changing one. Last updated: 2026-08-15 (Phase 0/1 start).

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
| UI | Streamlit, multipage via `st.session_state` router in `app.py` | spec requirement, simplest for MVP |
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
├── app.py                     # Streamlit entrypoint / router
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
│   ├── services/                # incident_service, report_service, analysis_service, archive_service
│   └── ui/                      # streamlit page modules (thin, call services only)
├── templates/                   # commander_report_template.docx generator + generated file
├── fixtures/synthetic_incident/ # golden fixture: 4 DOCX reports, 1 dispatch xlsx, expectations.json
├── data/                        # sqlite db + uploaded originals (gitignored)
└── tests/{unit,integration,fixtures}/
```

## 5. Data Model (conceptual — see `aar/models/*.py` for actual columns)

`Incident(1) -- (N) SourceDocument -- (0..1) CommanderReport`
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
| 5 | Report AI extraction | TODO |
| 6 | Incident reconstruction | TODO |
| 7 | Analysis engine (findings/lessons) | TODO |
| 8 | Interactive AAR (Streamlit workflow) | TODO |
| 9 | Re-analysis after correction | TODO |
| 10 | Archive/search | TODO |
| 11 | Synthetic end-to-end validation | TODO |
| 12 | Hardening (full regression) | TODO |
| 13 | Handoff | TODO |

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

## 9. Open Work / Known Bugs / Blocked / Unverified / Technical Debt

- Nothing implemented yet beyond skeleton — this section will fill in as
  phases complete.
- **Expected BLOCKED item (documented in advance):** live `AnthropicProvider`
  calls require `ANTHROPIC_API_KEY` in the environment. If not present when
  Phase 4/13 run, integration tests hitting the real API will be marked
  BLOCKED, not faked. Ordinary unit/integration tests never depend on this.

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
