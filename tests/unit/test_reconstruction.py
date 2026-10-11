from types import SimpleNamespace

from aar.analysis.reconstruction import _enforce_per_commander_order, run_reconstruction
from aar.llm.mock import MockLLMProvider
from aar.models import (
    CommanderReport,
    CreatedBy,
    IncidentEvent,
    Observation,
    ObservationCategory,
    ObservationType,
    SourceDocument,
    SourceDocumentType,
)


def _make_report(session, incident, callsign) -> CommanderReport:
    doc = SourceDocument(
        incident_id=incident.id,
        doc_type=SourceDocumentType.COMMANDER_REPORT,
        original_filename=f"{callsign}.docx",
        stored_path=f"/tmp/{callsign}.docx",
        content_hash=f"hash-{callsign}",
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    report = CommanderReport(
        incident_id=incident.id,
        source_document_id=doc.id,
        callsign=callsign,
        unit_name="Eenheid",
        rank="Adjudant",
        surname="Janssens",
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def _add_observation(session, incident, report, content, category, obs_type=ObservationType.HUMAN_OBSERVATION):
    obs = Observation(
        incident_id=incident.id,
        commander_report_id=report.id,
        observation_type=obs_type,
        category=category,
        content=content,
        source_passage=content,
        attributed_to=report.display_name,
        created_by=CreatedBy.AI,
    )
    session.add(obs)
    session.commit()
    session.refresh(obs)
    return obs


def test_reconstruction_groups_observations_into_events(session, sample_incident):
    r1 = _make_report(session, sample_incident, "P12")
    r2 = _make_report(session, sample_incident, "P21")
    _add_observation(session, sample_incident, r1, "Zware rook zichtbaar bij aankomst.", ObservationCategory.OBSERVATION)
    _add_observation(session, sample_incident, r2, "Rook aan de achterzijde van het pand.", ObservationCategory.OBSERVATION)

    result = run_reconstruction(session, sample_incident, MockLLMProvider())
    assert len(result.events) >= 1

    events = session.query(IncidentEvent).filter_by(incident_id=sample_incident.id).all()
    assert len(events) == len(result.events)
    for event in events:
        assert event.exact_time is None  # reconstruction alone never sets exact time


def test_reconstruction_rerun_replaces_ai_events_but_keeps_human_added(session, sample_incident):
    r1 = _make_report(session, sample_incident, "P12")
    _add_observation(session, sample_incident, r1, "Zware rook zichtbaar.", ObservationCategory.OBSERVATION)

    run_reconstruction(session, sample_incident, MockLLMProvider())
    ai_event_count_first = (
        session.query(IncidentEvent).filter_by(incident_id=sample_incident.id, is_human_added=False).count()
    )

    manual_event = IncidentEvent(
        incident_id=sample_incident.id, title="Manueel toegevoegd moment", order_index=99, is_human_added=True
    )
    session.add(manual_event)
    session.commit()

    run_reconstruction(session, sample_incident, MockLLMProvider())

    ai_event_count_second = (
        session.query(IncidentEvent).filter_by(incident_id=sample_incident.id, is_human_added=False).count()
    )
    assert ai_event_count_second == ai_event_count_first  # replaced, not duplicated

    still_there = session.get(IncidentEvent, manual_event.id)
    assert still_there is not None
    assert still_there.title == "Manueel toegevoegd moment"


def test_reconstruction_excludes_conflict_and_ai_observation_types_from_input(session, sample_incident):
    r1 = _make_report(session, sample_incident, "P12")
    _add_observation(
        session, sample_incident, r1, "Dit is al een AI-observatie.", ObservationCategory.OTHER, ObservationType.AI_OBSERVATION
    )
    result = run_reconstruction(session, sample_incident, MockLLMProvider())
    assert result.events == []


def _event(observation_ids):
    return SimpleNamespace(observation_ids=observation_ids)


def test_enforce_per_commander_order_fixes_llm_reordering():
    """Reproduces the exact real-world case (spec discussion, real-LLM
    output): a commander's Actie 1 (logistics — "voeding") got sorted
    *after* their own Actie 2 (a more dramatic SAR) despite the prompt
    saying not to — the commander's own form order (position 0 before
    position 1) must win regardless of what order_hint the LLM assigned."""
    # obs 10 = commander A's Actie 1 (position 0), obs 11 = commander A's
    # Actie 2 (position 1). The LLM put the event containing Actie 2 first.
    positions = {10: (1, 0, 2), 11: (1, 1, 2)}
    events = [_event([11]), _event([10])]  # wrong: Actie 2 before Actie 1

    fixed = _enforce_per_commander_order(events, positions)

    assert fixed[0].observation_ids == [10]  # Actie 1 first
    assert fixed[1].observation_ids == [11]  # Actie 2 second


def test_enforce_per_commander_order_leaves_correct_order_untouched():
    positions = {10: (1, 0, 2), 11: (1, 1, 2), 20: (2, 0, 2)}
    events = [_event([10]), _event([20]), _event([11])]

    fixed = _enforce_per_commander_order(events, positions)

    assert [e.observation_ids for e in fixed] == [[10], [20], [11]]


def test_enforce_per_commander_order_ignores_unrelated_commanders():
    # Different commanders' events are free to interleave however the LLM
    # judged narratively sensible — only same-commander order is enforced.
    positions = {10: (1, 0, 2), 20: (2, 0, 2)}
    events = [_event([20]), _event([10])]

    fixed = _enforce_per_commander_order(events, positions)

    assert [e.observation_ids for e in fixed] == [[20], [10]]


def test_enforce_per_commander_order_resolves_genuine_conflict_via_section_rank():
    """Reproduces the exact real-world case found in live use: three
    commanders' observations split across two adjacent events with
    mutually conflicting per-commander orderings (commander 1 and 2 each
    want event B before event A, commander 3 wants event A before event
    B — no order satisfies everyone). Naively swapping on any violation
    oscillates forever and lands on an arbitrary side depending on the
    iteration budget; the fix falls back to section rank (situation=1,
    actions=2 — see SECTION_ORDER): an event that is still purely
    "situation" must sort before one that already includes an action."""
    # Event A: commander1's action (situation=1 already happened at pos 0,
    # this action is later); commander2's situation obs at pos 1 (later
    # than its own pos 0 used in event B); commander3's situation obs at
    # pos 0-1 (earlier than event B's commander3 obs).
    positions = {
        # commander 1: situation obs (pos0, rank1) in event B, action obs (pos1, rank2) in event A
        1: (1, 0, 1), 2: (1, 1, 2),
        # commander 2: situation obs (pos0, rank1) in event B, situation obs (pos1, rank1) in event A
        3: (2, 0, 1), 4: (2, 1, 1),
        # commander 3: situation obs (pos0, rank1) in event A, situation obs (pos1, rank1) in event B
        5: (3, 0, 1), 6: (3, 1, 1),
    }
    event_a = _event([2, 4, 5])  # includes commander1's action -> section rank 2
    event_b = _event([1, 3, 6])  # pure situation -> section rank 1
    events = [event_a, event_b]  # wrong: mixed/action event placed before the pure-situation one

    fixed = _enforce_per_commander_order(events, positions)

    assert fixed[0] is event_b  # pure situation first
    assert fixed[1] is event_a
