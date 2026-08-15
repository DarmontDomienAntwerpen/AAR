"""Phase 11 — synthetic end-to-end validation (spec §62-64) against the
golden fixture, run through the full pipeline with the mock LLM provider.

Honest disclosure of what this run can and cannot verify: the mock provider
is deterministic and rule-based (see aar/llm/mock.py), so it can only ever
detect single-report assumption/uncertainty phrasing and category-based
grouping — it does NOT do genuine cross-report semantic comparison. Two
specific spec §63 conditions are therefore structurally out of the mock's
reach and are explicitly marked UNVERIFIED here rather than faked:

- C (conflicting perspectives between P12 and P21 about whether an order to
  check the rear of the building was given/received) requires comparing two
  different reports' narratives semantically.
- E (an effective-coordination positive practice that no single report
  explicitly labels as positive) requires inferring a pattern across
  reports that no source states outright.

Both require a real LLM (AnthropicProvider) to verify — see
`test_synthetic_incident_conditions_c_and_e_require_real_provider` below,
and HANDOFF.md for how to run this fixture with a real API key.
"""
from __future__ import annotations

import datetime as dt

import pytest

from aar.analysis.pipeline import run_analysis
from aar.llm.mock import MockLLMProvider
from aar.models import (
    AnalysisRunStatus,
    CommanderReport,
    DispatchRecord,
    IncidentEvent,
    ObjectiveAchieved,
    Observation,
    ObservationCategory,
    ObservationType,
)
from aar.services.dispatch_service import ingest_dispatch_excel
from aar.services.report_service import ingest_commander_report
from fixtures.synthetic_incident.build_fixture import (
    DISPATCH_ROWS,
    build_commander_reports,
    build_dispatch_excel,
)

KNOWN_DISPATCH_TIMESTAMPS = {
    dt.datetime.fromisoformat(row["Tijdstip"]) for row in DISPATCH_ROWS if row["Tijdstip"]
}


@pytest.fixture()
def synthetic_run(tmp_path, session, sample_incident, monkeypatch):
    monkeypatch.setattr(
        "aar.services.report_service.get_settings",
        lambda: type("S", (), {"project_root": tmp_path})(),
    )
    monkeypatch.setattr(
        "aar.services.dispatch_service.get_settings",
        lambda: type("S", (), {"project_root": tmp_path})(),
    )

    report_paths = build_commander_reports(tmp_path / "reports")
    for path in report_paths:
        ingest_commander_report(session, sample_incident, path.read_bytes(), path.name)

    dispatch_path = build_dispatch_excel(tmp_path / "dispatch")
    ingest_dispatch_excel(session, sample_incident, dispatch_path.read_bytes(), dispatch_path.name)

    run = run_analysis(session, sample_incident, MockLLMProvider())
    return run


def test_pipeline_succeeds_on_golden_fixture(synthetic_run):
    assert synthetic_run.status == AnalysisRunStatus.SUCCESS, synthetic_run.error_message


def test_ingestion_recognises_all_four_commanders_and_identities(synthetic_run, session, sample_incident):
    reports = session.query(CommanderReport).filter_by(incident_id=sample_incident.id).all()
    assert len(reports) == 4
    display_names = {r.display_name for r in reports}
    assert "P12 (1ste Hulpcentrum) — Adjudant Janssens" in display_names
    assert "P21 (2de Hulpcentrum) — Sergeant Willems" in display_names


def test_dispatch_ingestion_skips_blank_row(synthetic_run, session, sample_incident):
    records = session.query(DispatchRecord).filter_by(incident_id=sample_incident.id).all()
    assert len(records) == 5  # 6 rows in the fixture minus 1 fully blank row


# -- A: explicit assumption -------------------------------------------------
def test_condition_a_assumptions_detected(synthetic_run, session, sample_incident):
    assumptions = (
        session.query(Observation)
        .filter_by(incident_id=sample_incident.id, observation_type=ObservationType.ASSUMPTION)
        .all()
    )
    assert len(assumptions) >= 1
    assert all(o.source_passage for o in assumptions)  # traceability preserved


# -- B: explicit uncertainty -------------------------------------------------
def test_condition_b_uncertainty_detected_not_treated_as_fact(synthetic_run, session, sample_incident):
    uncertain = (
        session.query(Observation)
        .filter_by(incident_id=sample_incident.id, observation_type=ObservationType.UNCERTAINTY)
        .all()
    )
    assert len(uncertain) >= 1
    assert all(o.observation_type != ObservationType.FACT for o in uncertain)


# -- D: partially achieved objective -----------------------------------------
def test_condition_d_partially_achieved_objective_recognised(synthetic_run, session, sample_incident):
    p12 = (
        session.query(CommanderReport)
        .filter_by(incident_id=sample_incident.id, callsign="P12")
        .one()
    )
    assert p12.objective_achieved == ObjectiveAchieved.GEDEELTELIJK


# -- F: hidden pattern across reports -----------------------------------------
def test_condition_f_ai_observation_from_cross_report_pattern(synthetic_run, session, sample_incident):
    ai_observations = (
        session.query(Observation)
        .filter_by(incident_id=sample_incident.id, observation_type=ObservationType.AI_OBSERVATION)
        .all()
    )
    assert len(ai_observations) >= 1
    assert all(o.commander_report_id is None for o in ai_observations)  # not attributed to one source


# -- G: important dispatch timestamps correctly attached ----------------------
def test_condition_g_dispatch_timestamp_attached_where_supported(synthetic_run, session, sample_incident):
    timed_events = (
        session.query(IncidentEvent)
        .filter(IncidentEvent.incident_id == sample_incident.id, IncidentEvent.exact_time.isnot(None))
        .all()
    )
    assert len(timed_events) >= 1
    for event in timed_events:
        assert event.exact_time in KNOWN_DISPATCH_TIMESTAMPS  # never an invented/interpolated value
        assert event.exact_time_source and event.exact_time_source.startswith("dispatch_record:")


# -- H: untimed narrative events stay untimed, no invented time --------------
def test_condition_h_untimed_events_have_no_fabricated_time(synthetic_run, session, sample_incident):
    events = session.query(IncidentEvent).filter_by(incident_id=sample_incident.id).all()
    untimed = [e for e in events if e.exact_time is None]
    assert len(untimed) >= 1
    for event in untimed:
        assert event.approx_time_text is None  # nothing in this fixture's narrative states a clock time


# -- I: later-known information is not backdated onto an earlier decision ----
def test_condition_i_decision_ordered_before_result_no_hindsight_backdating(
    synthetic_run, session, sample_incident
):
    from aar.schemas.constants import CATEGORY_LABELS_NL

    decision_event = (
        session.query(IncidentEvent)
        .filter_by(incident_id=sample_incident.id, title=CATEGORY_LABELS_NL[ObservationCategory.DECISION])
        .one_or_none()
    )
    result_event = (
        session.query(IncidentEvent)
        .filter_by(incident_id=sample_incident.id, title=CATEGORY_LABELS_NL[ObservationCategory.RESULT])
        .one_or_none()
    )
    assert decision_event is not None and result_event is not None
    assert decision_event.order_index < result_event.order_index


# -- J: reasonable decision with imperfect outcome — no injected judgment ----
def test_condition_j_decision_content_preserved_without_injected_judgement(
    synthetic_run, session, sample_incident
):
    p12 = session.query(CommanderReport).filter_by(incident_id=sample_incident.id, callsign="P12").one()
    decision_obs = (
        session.query(Observation)
        .filter_by(
            incident_id=sample_incident.id,
            commander_report_id=p12.id,
            category=ObservationCategory.DECISION,
        )
        .all()
    )
    assert len(decision_obs) >= 1
    for obs in decision_obs:
        assert obs.content == obs.source_passage  # verbatim, nothing rewritten in hindsight
        for judgemental_word in ("fout", "verkeerd", "had moeten weten"):
            assert judgemental_word not in obs.content.lower()


def test_source_traceability_for_all_discussion_points(synthetic_run, session, sample_incident):
    from aar.models import DiscussionPoint

    points = session.query(DiscussionPoint).filter_by(incident_id=sample_incident.id).all()
    assert len(points) >= 1
    for dp in points:
        for obs_id in dp.observation_ids:
            obs = session.get(Observation, obs_id)
            assert obs is not None
            assert obs.incident_id == sample_incident.id


def test_synthetic_incident_conditions_c_and_e_require_real_provider():
    """Documents, rather than silently skips, a real MVP limitation: the
    deterministic mock cannot do cross-report semantic comparison, so it
    cannot detect the P12/P21 conflicting-order conflict (condition C) or
    the unlabelled-positive rescue coordination (condition E). Verify these
    manually by setting AAR_LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY in
    .env, then re-running this fixture through the Streamlit UI or
    `run_analysis` directly with AnthropicProvider — see HANDOFF.md."""
    pytest.skip(
        "UNVERIFIED with the mock provider by design — requires AnthropicProvider "
        "and a real ANTHROPIC_API_KEY; see docstring and HANDOFF.md."
    )
