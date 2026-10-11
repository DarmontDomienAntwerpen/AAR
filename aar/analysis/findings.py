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
    ConfidenceState,
    CreatedBy,
    DiscussionOrigin,
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

Je krijgt de waarnemingen en de gegroepeerde incidentmomenten (events). Elke \
waarneming heeft al een observation_type. Dit is GEEN vrijblijvende \
suggestie: een waarneming met observation_type "assumption", "uncertainty" \
of "conflict" IS per definitie een bespreekpunt — die moet je vrijwel altijd \
opnemen als discussion_point, tenzij de inhoud triviaal is (bv. een \
tijdsaanduiding die niemand ter discussie stelt). Rule 5 uit de \
kernprincipes ("als bewijs onvoldoende is, zeg dat expliciet") gaat over het \
verzinnen van FEITEN — niet over terughoudendheid bij het signaleren van \
bespreekpunten die al als onzeker/veronderstelling/tegenstrijdig \
gelabeld zijn. Lege lijsten teruggeven terwijl de data zulke waarnemingen \
bevat, is een fout.

Zoek daarnaast actief naar:
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

BELANGRIJK — combineer, dupliceer niet: als meerdere waarnemingen van \
VERSCHILLENDE bevelvoerders (verschillende commander_report_id) hetzelfde \
onderliggende punt beschrijven — ook al is de bewoording anders — maak daar \
dan ÉÉN discussion_point of positive_finding van, met alle betrokken \
observation_ids samen in observation_ids (dus niet één punt per \
bevelvoerder). Zo blijft het overzicht kort en zie je meteen welke \
bevelvoerders hetzelfde punt maakten, in plaats van hetzelfde punt twee of \
drie keer na elkaar te lezen.

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

    # Deterministic safety net: the addendum above is explicit that every
    # assumption/uncertainty observation must become a discussion_point
    # ("vrijwel altijd... lege lijsten teruggeven... is een fout") — seen in
    # practice to not always be followed (the LLM sometimes returns none at
    # all for a run where such observations clearly exist). Rather than
    # silently losing a flagged assumption/uncertainty because the LLM
    # missed it this run, catch anything it didn't reference and add a
    # minimal fallback point for it — same principle as the reconstruction
    # ordering fix: don't rely purely on prompt compliance for something
    # this tool already claims to guarantee.
    referenced_observation_ids = {oid for dp in result.discussion_points for oid in dp.observation_ids}
    fallback_origin = {
        ObservationType.ASSUMPTION: DiscussionOrigin.ASSUMPTION,
        ObservationType.UNCERTAINTY: DiscussionOrigin.UNCERTAINTY,
    }
    flagged_observations = (
        session.query(Observation)
        .filter(
            Observation.incident_id == incident.id,
            Observation.observation_type.in_(list(fallback_origin.keys())),
        )
        .all()
    )
    missed_observations = [o for o in flagged_observations if o.id not in referenced_observation_ids]
    for o in missed_observations:
        session.add(
            DiscussionPoint(
                incident_id=incident.id,
                event_id=None,
                title=o.content,
                description=(
                    f"Automatisch gesignaleerd ({o.observation_type.value}), niet apart opgenomen "
                    f"door de AI-analyse zelf. Brontekst: „{o.source_passage}”"
                    if o.source_passage
                    else f"Automatisch gesignaleerd ({o.observation_type.value}), niet apart opgenomen "
                    "door de AI-analyse zelf."
                ),
                origin_category=fallback_origin[o.observation_type],
                confidence_state=ConfidenceState.ONZEKER,
                observation_ids=[o.id],
                is_human_added=False,
            )
        )
    if missed_observations:
        logger.warning(
            "Findings for incident %s: %d assumption/uncertainty observation(s) missed by the "
            "LLM, added as fallback discussion points.",
            incident.id,
            len(missed_observations),
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

    # Same deterministic safety net as the discussion_points fallback above:
    # a "went_well" observation is a literal, structural signal (the form's
    # own section, not an LLM judgement call) that something positive was
    # reported — seen in practice to sometimes be dropped entirely by the
    # LLM in a given run (positive_findings coming back empty despite clear
    # went_well content). Catch anything not referenced and add a minimal
    # fallback finding for it, rather than silently losing it.
    referenced_pf_observation_ids = {oid for pf in result.positive_findings for oid in pf.observation_ids}
    went_well_observations = (
        session.query(Observation)
        .filter(Observation.incident_id == incident.id, Observation.source_section == "went_well")
        .all()
    )
    missed_went_well = [o for o in went_well_observations if o.id not in referenced_pf_observation_ids]
    for o in missed_went_well:
        session.add(
            PositiveFinding(
                incident_id=incident.id,
                event_id=None,
                title=o.content,
                description=(
                    f"Automatisch gesignaleerd (wat ging goed), niet apart opgenomen door de "
                    f"AI-analyse zelf. Brontekst: „{o.source_passage}”"
                    if o.source_passage
                    else "Automatisch gesignaleerd (wat ging goed), niet apart opgenomen door de AI-analyse zelf."
                ),
                observation_ids=[o.id],
                is_human_added=False,
            )
        )
    if missed_went_well:
        logger.warning(
            "Findings for incident %s: %d went_well observation(s) missed by the LLM, "
            "added as fallback positive findings.",
            incident.id,
            len(missed_went_well),
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
