"""Stage 5 — analysis / findings (spec §39-41).

Actively looks for positive practices, things that went less well, explicit/
implicit assumptions, uncertainty, conflicting perspectives, and candidate
discussion points — not only failures. A detected conflict becomes a
DiscussionPoint with origin_category=CONFLICT rather than the system
silently picking a side (spec §29).
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from aar.config.logging_setup import get_logger
from aar.llm.base import LLMOutputValidationError, LLMProvider
from aar.llm.prompts.system_prompts import build_system_prompt
from aar.models import (
    CreatedBy,
    DiscussionPoint,
    HumanCorrection,
    Incident,
    IncidentEvent,
    Observation,
    ObservationType,
    PositiveFinding,
)
from aar.schemas.findings import FindingsOutput

logger = get_logger("analysis.findings")

_SOURCE_TYPES = (
    ObservationType.FACT,
    ObservationType.HUMAN_OBSERVATION,
    ObservationType.ASSUMPTION,
    ObservationType.UNCERTAINTY,
)

_ADDENDUM = """\
TAAK: Analyse van het gereconstrueerde incidentverloop.

Je krijgt de waarnemingen en de gegroepeerde incidentmomenten (events). Zoek \
actief naar:
- discussion_points: mogelijke bespreekpunten — vanuit onzekerheid, \
veronderstellingen, tegenstrijdigheden tussen bronnen, niet-behaalde \
doelen, onverwachte resultaten, mogelijke coördinatie- of \
communicatieproblemen, patronen, onverklaarde beslissingen, of \
ontbrekende informatie. Vul origin_category en confidence_state zo goed \
mogelijk in. Als twee bronnen elkaar tegenspreken, kies GEEN kant — \
beschrijf het verschil neutraal met origin_category "conflict".
- positive_findings: mogelijke positieve punten, ook als niemand expliciet \
zegt dat iets goed ging — bijvoorbeeld merkbaar effectieve coördinatie.
- ai_observations: patronen die je zelf opmerkt maar die geen enkele bron \
expliciet benoemt. Wees hier terughoudend en alleen concreet onderbouwd \
door de meegegeven observation_ids.

Gebruik uitsluitend de meegegeven observation_ids als bewijs. Verzin geen \
gebeurtenissen, oorzaken of personen die niet in de gegevens voorkomen. \
Wijs nooit schuld toe aan een individu. Beoordeel nooit de professionele \
competentie van een individu. Analyseer beslissingen op basis van de \
informatie die op dat moment beschikbaar was (geen hindsight bias).\
"""


def build_findings_payload(session: Session, incident: Incident) -> dict:
    observations = (
        session.query(Observation)
        .filter(Observation.incident_id == incident.id, Observation.observation_type.in_(_SOURCE_TYPES))
        .all()
    )
    events = session.query(IncidentEvent).filter_by(incident_id=incident.id).all()
    corrections = session.query(HumanCorrection).filter_by(incident_id=incident.id).all()

    return {
        "observations": [
            {
                "id": o.id,
                "commander_report_id": o.commander_report_id,
                "attributed_to": o.attributed_to,
                "observation_type": o.observation_type.value,
                "category": o.category.value,
                "content": o.content,
            }
            for o in observations
        ],
        "events": [
            {"id": e.id, "title": e.title, "ai_summary": e.ai_summary, "observation_ids": e.observation_ids}
            for e in events
        ],
        "human_corrections": [
            {"target_type": c.target_type, "correction_text": c.correction_text} for c in corrections
        ],
    }


def build_findings_prompt(session: Session, incident: Incident) -> tuple[str, str]:
    system_prompt = build_system_prompt(_ADDENDUM)
    payload = build_findings_payload(session, incident)
    user_prompt = (
        "Hieronder de gegevens voor analyse.\n\nGEGEVENS (JSON):\n```json\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n```"
    )
    return system_prompt, user_prompt


def run_findings(session: Session, incident: Incident, provider: LLMProvider) -> FindingsOutput:
    system_prompt, user_prompt = build_findings_prompt(session, incident)

    try:
        result = provider.generate_structured(
            system_prompt=system_prompt, user_prompt=user_prompt, response_model=FindingsOutput
        )
    except LLMOutputValidationError as exc:
        logger.error("Findings analysis failed for incident %s: %s", incident.id, exc)
        raise

    session.query(DiscussionPoint).filter_by(incident_id=incident.id, is_human_added=False).delete()
    session.query(PositiveFinding).filter_by(incident_id=incident.id, is_human_added=False).delete()
    session.query(Observation).filter_by(
        incident_id=incident.id, observation_type=ObservationType.AI_OBSERVATION, created_by=CreatedBy.AI
    ).delete()
    session.flush()

    events_by_title = {
        e.title: e.id for e in session.query(IncidentEvent).filter_by(incident_id=incident.id).all()
    }

    for dp in result.discussion_points:
        session.add(
            DiscussionPoint(
                incident_id=incident.id,
                event_id=events_by_title.get(dp.event_title) if dp.event_title else None,
                title=dp.title,
                description=dp.description,
                origin_category=dp.origin_category,
                confidence_state=dp.confidence_state,
                observation_ids=dp.observation_ids,
                is_human_added=False,
            )
        )

    for pf in result.positive_findings:
        session.add(
            PositiveFinding(
                incident_id=incident.id,
                event_id=events_by_title.get(pf.event_title) if pf.event_title else None,
                title=pf.title,
                description=pf.description,
                observation_ids=pf.observation_ids,
                is_human_added=False,
            )
        )

    for ai_obs in result.ai_observations:
        session.add(
            Observation(
                incident_id=incident.id,
                commander_report_id=None,
                observation_type=ObservationType.AI_OBSERVATION,
                content=ai_obs.content,
                evidence_refs=[{"observation_id": oid} for oid in ai_obs.evidence_observation_ids],
                created_by=CreatedBy.AI,
            )
        )

    session.commit()
    logger.info(
        "Findings complete for incident %s: %d discussion point(s), %d positive finding(s), "
        "%d AI observation(s).",
        incident.id,
        len(result.discussion_points),
        len(result.positive_findings),
        len(result.ai_observations),
    )
    return result
