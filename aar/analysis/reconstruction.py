"""Stage 3 — incident reconstruction (spec §35).

Groups observations from across all commander reports into candidate
`IncidentEvent`s with a relative order. The LLM output schema
(`ReconstructionOutput`) has no exact-timestamp field at all, so there is
nothing for it to fabricate a time into — exact times are attached
separately and deterministically in Stage 4 (`timeline.py`).
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from aar.config.logging_setup import get_logger
from aar.llm.base import LLMOutputValidationError, LLMProvider
from aar.llm.prompts.system_prompts import build_system_prompt
from aar.models import (
    CommanderReport,
    HumanCorrection,
    Incident,
    IncidentEvent,
    EventPerspective,
    Observation,
    ObservationType,
)
from aar.schemas.constants import CRUCIAL_SUMMARY_CATEGORIES, SECTION_ORDER
from aar.schemas.reconstruction import ReconstructionOutput

logger = get_logger("analysis.reconstruction")

# Only raw per-source material feeds reconstruction — CONFLICT/AI_OBSERVATION
# rows are themselves the output of later stages and must not be re-grouped
# as if they were fresh source evidence (would compound across re-analysis runs).
_SOURCE_TYPES = (
    ObservationType.FACT,
    ObservationType.HUMAN_OBSERVATION,
    ObservationType.ASSUMPTION,
    ObservationType.UNCERTAINTY,
)

_ADDENDUM = """\
TAAK: Reconstructie van het incidentverloop uit meerdere bevelvoerdersverslagen.

Je krijgt een lijst van waarnemingen (observations) uit verschillende \
bevelvoerdersverslagen, elk met een uniek id. Groepeer waarnemingen die \
waarschijnlijk naar hetzelfde operationele moment verwijzen tot één \
"event" (incidentmoment). Verschillende bevelvoerders mogen een ander \
perspectief hebben op hetzelfde moment — bewaar elk perspectief apart \
onder "perspectives", gekoppeld aan het juiste commander_report_id.

BELANGRIJK:
- Er is GEEN veld voor een exact tijdstip. Gebruik uitsluitend order_hint \
om de relatieve volgorde aan te geven (lager = eerder).
- HARDE REGEL, zonder uitzondering: de waarnemingen van EENZELFDE bevelvoerder \
staan al in de volgorde waarin die bevelvoerder ze zelf invulde — Actie 1, \
dan Actie 2, dan Actie 3, enzovoort. Dat volgnummer IS de tijdsvolgorde, \
gegeven door de bevelvoerder zelf, geen suggestie om te herwegen. Een latere \
actie van dezelfde bevelvoerder krijgt ALTIJD een hogere-of-gelijke order_hint \
dan een eerdere actie van diezelfde bevelvoerder — ook als die latere actie \
(bv. een reddingsactie met gevonden slachtoffers) narratief opvallender \
lijkt dan de eerdere (bv. een logistieke actie zoals voeding voorzien). \
"Belangrijker lijken" is GEEN geldige reden om de volgorde om te draaien.
  Concreet: als bevelvoerder X als Actie 1 "voeding voorzien" opgeeft en als \
  Actie 2 "SAR uitgevoerd, 2 slachtoffers gevonden", dan krijgt de \
  waarneming over voeding een LAGERE order_hint dan die over de SAR — ook \
  al is de SAR-vondst het opvallendere nieuws. Fout is: SAR eerst plaatsen \
  omdat het belangrijker leest.
- Enkel wanneer je waarnemingen van VERSCHILLENDE bevelvoerders tegenover \
elkaar plaatst (bv. om te bepalen of bevelvoerder A's actie vóór of na \
bevelvoerder B's actie gebeurde), mag je op inhoud afgaan om ze narratief \
aannemelijk te interlijnen — maar de eigen volgorde van elke bevelvoerder \
afzonderlijk (Actie 1 vóór Actie 2 vóór Actie 3) blijft altijd behouden.
- approx_time_text mag je alleen invullen als een waarneming zelf een \
tijdsaanduiding bevat (reported_time_text) — neem die dan letterlijk over.
- observation_ids in een event moet een deelverzameling zijn van de \
meegegeven waarnemingen-ids.
- Als eerdere correcties van de facilitator zijn meegegeven, behandel die \
als gezaghebbend en pas de groepering daarop aan.\
"""


def build_reconstruction_payload(session: Session, incident: Incident) -> dict:
    observations = (
        session.query(Observation)
        .filter(
            Observation.incident_id == incident.id,
            Observation.observation_type.in_(_SOURCE_TYPES),
            Observation.commander_report_id.isnot(None),
            # The incident timeline is chronological: observations -> actions ->
            # results (+ objective), not evaluation (what went well / less
            # well). Evaluations belong on their own tab, but remain available
            # to the findings step below.
            Observation.category.in_(CRUCIAL_SUMMARY_CATEGORIES),
        )
        # Stable order = extraction order = the order each commander wrote
        # their own observations/actions in (see the addendum below: this
        # is a deliberate, meaningful signal, not incidental).
        .order_by(Observation.commander_report_id, Observation.id)
        .all()
    )
    reports_by_id = {
        r.id: r
        for r in session.query(CommanderReport).filter_by(incident_id=incident.id).all()
    }
    obs_payload = [
        {
            "id": o.id,
            "commander_report_id": o.commander_report_id,
            "commander_display_name": reports_by_id[o.commander_report_id].display_name
            if o.commander_report_id in reports_by_id
            else None,
            "observation_type": o.observation_type.value,
            "category": o.category.value,
            "content": o.content,
            "source_passage": o.source_passage,
            "reported_time_text": o.reported_time_text,
        }
        for o in observations
    ]
    corrections = (
        session.query(HumanCorrection).filter_by(incident_id=incident.id).all()
    )
    return {
        "observations": obs_payload,
        "human_corrections": [
            {"target_type": c.target_type, "correction_text": c.correction_text}
            for c in corrections
        ],
    }


def _observation_positions(session: Session, incident: Incident) -> dict[int, tuple[int, int, int]]:
    """Maps observation id -> (commander_report_id, position within that
    commander's own observations [extraction order = form order],
    section_order rank [situation < actions < ... — see SECTION_ORDER]).
    The section rank is a cross-commander tiebreaker for
    _enforce_per_commander_order: it has no notion of "commander A's actions
    section vs commander B's situation section" on its own, since position
    only resets to 0 per commander."""
    observations = (
        session.query(Observation)
        .filter(
            Observation.incident_id == incident.id,
            Observation.observation_type.in_(_SOURCE_TYPES),
            Observation.commander_report_id.isnot(None),
            # The incident timeline is chronological: observations -> actions ->
            # results (+ objective), not evaluation (what went well / less
            # well). Evaluations belong on their own tab, but remain available
            # to the findings step below.
            Observation.category.in_(CRUCIAL_SUMMARY_CATEGORIES),
        )
        .order_by(Observation.commander_report_id, Observation.id)
        .all()
    )
    positions: dict[int, tuple[int, int, int]] = {}
    counters: dict[int, int] = {}
    for o in observations:
        idx = counters.get(o.commander_report_id, 0)
        section_rank = SECTION_ORDER.get(o.source_section, 99)
        positions[o.id] = (o.commander_report_id, idx, section_rank)
        counters[o.commander_report_id] = idx + 1
    return positions


def _enforce_per_commander_order(events: list, positions: dict[int, tuple[int, int, int]]) -> list:
    """The LLM's order_hint is a strong signal but not a guaranteed one —
    seen in practice to occasionally reorder a commander's own actions by
    narrative weight (e.g. moving a dramatic SAR ahead of an earlier,
    duller logistics action) despite explicit instructions not to. Since
    "which of a commander's own actions came first" is a hard fact we
    already know (form/extraction order — see _observation_positions), fix
    any violation deterministically instead of hoping the prompt is obeyed
    every single run: stable-swap adjacent events until no event contains a
    later action from some commander while immediately preceding an event
    with an earlier action from that same commander."""
    events = list(events)
    n = len(events)

    def commander_ranges(event) -> dict[int, tuple[int, int]]:
        ranges: dict[int, tuple[int, int]] = {}
        for oid in event.observation_ids:
            info = positions.get(oid)
            if info is None:
                continue
            cid, pos, _section_rank = info
            lo, hi = ranges.get(cid, (pos, pos))
            ranges[cid] = (min(lo, pos), max(hi, pos))
        return ranges

    def max_section_rank(event) -> int:
        # The event's *furthest-along* observation, not its earliest one:
        # a single action item mixed in with otherwise-situation
        # observations still means this event represents a moment at least
        # that far along the situation -> action -> result pipeline. Using
        # the minimum instead would let one leftover situation observation
        # mask the fact that the event as a whole already includes an
        # action.
        ranks = [positions[oid][2] for oid in event.observation_ids if oid in positions]
        return max(ranks) if ranks else 0

    def violates(x: dict, y: dict) -> bool:
        return any(cid in y and x_hi > y[cid][0] for cid, (_x_lo, x_hi) in x.items())

    ranges_list = [commander_ranges(e) for e in events]
    section_ranks = [max_section_rank(e) for e in events]

    for _ in range(n * n):  # bounded: bubble-converges or we give up, never loop forever
        changed = False
        for i in range(n - 1):
            a, b = ranges_list[i], ranges_list[i + 1]
            a_clean_win = violates(a, b) and not violates(b, a)
            # Three or more commanders' observations can split across the
            # same two events with genuinely conflicting notions of which
            # came first — no order satisfies everyone. Swapping on ANY
            # violation regardless of what the swap itself would break can
            # flip such a pair back and forth every pass, landing on
            # whichever side the bounded iteration count happens to stop
            # on — i.e. the result silently depends on n, not on the data.
            # For that ambiguous case, fall back to a domain-level default
            # instead of an arbitrary one: an event whose observations are
            # all still at the "situation" stage sorts before one that
            # already includes an action, since you cannot act on
            # something before observing it — SECTION_ORDER encodes
            # exactly that stage ordering.
            ambiguous_conflict = violates(a, b) and violates(b, a)
            b_wins_tiebreak = ambiguous_conflict and section_ranks[i] > section_ranks[i + 1]
            if a_clean_win or b_wins_tiebreak:
                events[i], events[i + 1] = events[i + 1], events[i]
                ranges_list[i], ranges_list[i + 1] = ranges_list[i + 1], ranges_list[i]
                section_ranks[i], section_ranks[i + 1] = section_ranks[i + 1], section_ranks[i]
                changed = True
        if not changed:
            break
    return events


def build_reconstruction_prompt(session: Session, incident: Incident) -> tuple[str, str]:
    system_prompt = build_system_prompt(_ADDENDUM)
    payload = build_reconstruction_payload(session, incident)
    user_prompt = (
        "Hieronder de gegevens voor reconstructie.\n\nGEGEVENS (JSON):\n```json\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n```"
    )
    return system_prompt, user_prompt


def run_reconstruction(
    session: Session, incident: Incident, provider: LLMProvider
) -> ReconstructionOutput:
    system_prompt, user_prompt = build_reconstruction_prompt(session, incident)

    try:
        result = provider.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=ReconstructionOutput,
        )
    except LLMOutputValidationError as exc:
        logger.error("Reconstruction failed for incident %s: %s", incident.id, exc)
        raise

    # An event's observations always include its perspectives' observations.
    # The model sometimes fills observation_ids only per perspective and
    # leaves the event-level list empty; the per-commander ordering below and
    # the narrative stage both read the event-level list, so an empty one made
    # the narrative report "no incident moments" despite a full timeline.
    for reconstructed in result.events:
        merged = list(reconstructed.observation_ids)
        for perspective in reconstructed.perspectives:
            merged.extend(oid for oid in perspective.observation_ids if oid not in merged)
        reconstructed.observation_ids = merged

    # Re-analysis: drop previous AI-generated events, keep facilitator-added ones.
    old_events = (
        session.query(IncidentEvent)
        .filter_by(incident_id=incident.id, is_human_added=False)
        .all()
    )
    for event in old_events:
        session.query(EventPerspective).filter_by(event_id=event.id).delete()
        session.delete(event)
    session.flush()

    reports_by_id = {
        r.id: r
        for r in session.query(CommanderReport).filter_by(incident_id=incident.id).all()
    }

    positions = _observation_positions(session, incident)
    ordered_events = _enforce_per_commander_order(
        sorted(result.events, key=lambda e: e.order_hint), positions
    )
    for order_index, reconstructed in enumerate(ordered_events):
        event = IncidentEvent(
            incident_id=incident.id,
            title=reconstructed.title,
            order_index=order_index,
            approx_time_text=reconstructed.approx_time_text,
            ai_summary=reconstructed.ai_summary,
            involved_units=reconstructed.involved_units,
            involved_commanders=reconstructed.involved_commanders,
            observation_ids=reconstructed.observation_ids,
            is_human_added=False,
        )
        session.add(event)
        session.flush()

        for perspective in reconstructed.perspectives:
            report = reports_by_id.get(perspective.commander_report_id)
            session.add(
                EventPerspective(
                    event_id=event.id,
                    commander_report_id=perspective.commander_report_id,
                    commander_display_name=report.display_name if report else "",
                    perspective_text=perspective.perspective_text,
                    observation_ids=perspective.observation_ids,
                )
            )

    session.commit()
    logger.info(
        "Reconstruction complete for incident %s: %d event(s).", incident.id, len(result.events)
    )
    return result
