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
TAAK: Reconstructie van het incidentverloop uit meerdere commandantenverslagen.

Je krijgt een lijst van waarnemingen (observations) uit verschillende \
commandantenverslagen, elk met een uniek id. Groepeer waarnemingen die \
waarschijnlijk naar hetzelfde operationele moment verwijzen tot één \
"event" (incidentmoment). Verschillende commandanten mogen een ander \
perspectief hebben op hetzelfde moment — bewaar elk perspectief apart \
onder "perspectives", gekoppeld aan het juiste commander_report_id.

BELANGRIJK:
- Er is GEEN veld voor een exact tijdstip. Gebruik uitsluitend order_hint \
om de relatieve volgorde aan te geven (lager = eerder), gebaseerd op wat \
narratief aannemelijk is. Verzin nooit een exact tijdstip.
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
        )
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

    for order_index, reconstructed in enumerate(
        sorted(result.events, key=lambda e: e.order_hint)
    ):
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
