"""Stage 7 — situation narrative synthesis.

This is the one pipeline stage that is explicitly *not* meaningful on the
mock provider (spec §57 discussion): synthesising several commanders'
per-moment accounts into one coherent "what happened" overview requires
real language understanding, not rule-based grouping. The mock's
`_narrative()` therefore produces an honestly-labelled, non-synthesised
fallback rather than pretending — see `aar/llm/mock.py`.

Distinct from `aar_service.default_situation_summary`, which is a
deterministic per-event/per-commander listing used (a) as the fallback
before any real analysis has run, and (b) as what the mock provider itself
approximates here.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from aar.config.logging_setup import get_logger
from aar.llm.base import LLMOutputValidationError, LLMProvider
from aar.llm.prompts.system_prompts import build_system_prompt
from aar.models import HumanCorrection, Incident, IncidentEvent, Observation
from aar.schemas.constants import CRUCIAL_SUMMARY_CATEGORIES
from aar.schemas.narrative import SituationNarrativeOutput

logger = get_logger("analysis.narrative")

_ADDENDUM = """\
TAAK: Een korte situatieschets schrijven van het volledige incident.

Je krijgt de decision-relevante incidentmomenten (waarnemingen bij aankomst, \
beslissingen, acties, resultaten, doelstelling — puur de feitelijke lijn, \
GEEN evaluatie), chronologisch geordend, elk met het perspectief van de \
betrokken bevelvoerder(en). Schrijf hieruit een kort samenhangend verhaal — \
MAXIMAAL 4-6 zinnen in totaal — dat een lezer die niets van het incident \
weet in een oogopslag laat begrijpen wat er in totaal gebeurde, van \
aankomst tot afronding. Dit is een dashboard-samenvatting, geen volledig \
verslag: kies alleen de belangrijkste lijn, niet elk detail. Het volledige \
verhaal per bevelvoerder staat al elders in de tool; wat ging goed/minder \
goed en bespreekpunten staan op hun eigen tabblad — die horen hier niet in.

Verdeel de tekst in exact 3 korte alinea's, altijd in deze volgorde, met \
een lege regel ertussen (dus een dubbele newline \\n\\n in de output-string) \
— niet als één dicht blok tekst: (1) WAARNEMINGEN — wat er bij aankomst \
werd vastgesteld, (2) ACTIES — de kernbeslissing(en) en actie(s), in de \
volgorde waarin ze gebeurden, (3) RESULTATEN — wat daaruit volgde. Elke \
alinea is 1-2 zinnen, geen kopjes of opsommingstekens, gewoon lopende tekst \
per alinea.

Hoe om te gaan met de verschillende bronnen:
- Waar bevelvoerders elkaar aanvullen (verschillende stukjes van hetzelfde \
geheel): voeg samen tot vloeiende tekst, zonder overal "volgens X" bij te \
zetten — dat hoeft alleen waar het onderscheid ertoe doet.
- Waar bevelvoerders elkaar ECHT tegenspreken (dezelfde plek/hetzelfde \
moment, onverenigbare lezingen): kies GEEN kant en verzin geen verzoening \
— benoem het verschil expliciet ("volgens P12 ..., terwijl P21 meldde dat \
..."). Noem het NOOIT "tegenspraak" of "spreken elkaar tegen" als het \
gewoon twee verschillende, best verenigbare feiten zijn — bv. twee \
commandanten die een ANDERE locatie doorzochten en dus logischerwijze een \
ander resultaat vonden, is geen tegenspraak, dat is gewoon twee aparte \
zoekacties. Vraag jezelf af: gaat dit over exact dezelfde plek/hetzelfde \
moment met onverenigbare beweringen? Zo niet, beschrijf het gewoon als wat \
het is (twee acties, elk met hun eigen resultaat), zonder het woord \
tegenspraak/tegenstrijdig erbij te zoeken.
- Gebruik uitsluitend de meegegeven incidentmomenten als bron. Verzin geen \
tijdstippen, gebeurtenissen, oorzaken of personen die niet in de gegevens \
voorkomen. Als iets onduidelijk blijft, zeg dat expliciet in de tekst in \
plaats van het stilzwijgend op te vullen.
- Dit mag, in tegenstelling tot titels elders in de tool, gewone lopende \
zinnen zijn — geen telegramstijl. De vaste afkortingen (HD/LD/SAR/SO/V+nummer) \
blijven wel gelden.
- Respecteer de volgorde waarin een bevelvoerder zijn eigen acties/beslissingen \
opgeeft: die volgorde IS de tijdsvolgorde. Herschik acties van dezelfde \
bevelvoerder niet naar wat dramatisch belangrijker lijkt — een actie die als \
eerste genoemd wordt, gebeurde als eerste en hoort dus vooraan in het \
verhaal, ook als een latere actie (bv. SAR) inhoudelijk opvallender is.
- Pas op met kale getallen die niet naar een verdieping verwijzen (bv. \
"ploeg 3 en 4", "nummer 3 van de ploeg") — laat het verduidelijkende woord \
(ploeg/nummer/persoon/...) er altijd bijstaan. Zonder dat woord lijkt een \
getal een verdieping (V+nummer), wat een schijncontradictie met andere \
bronnen kan geven waar wél expliciet over verdiepingen gesproken wordt.
- Laat concrete inzet van middelen/personeel nooit stilzwijgend weg, ook al \
verkort je de rest: als een bevelvoerder vermeldt dat iets "met de hele ploeg" \
of "met N personen" gebeurde, of expliciet de reden geeft (bv. "wegens de \
lange afstand"), hoort dat erbij — dat is operationeel relevant (het toont \
hoeveel capaciteit ergens aan vastzat), geen overbodig detail om in te \
korten.\
"""


def build_narrative_payload(session: Session, incident: Incident) -> dict:
    all_events = (
        session.query(IncidentEvent)
        .filter_by(incident_id=incident.id)
        .order_by(IncidentEvent.order_index)
        .all()
    )
    # Only decision-relevant moments (same filter as the deterministic
    # fallback, spec-consistent) — sending every category (raw observations,
    # assessments, procedural detail) produces a long, unfocused dump even
    # when the model is told to keep it short; a tighter, more relevant
    # input naturally keeps the output tight too.
    crucial_obs_ids = {
        oid
        for (oid,) in session.query(Observation.id)
        .filter(Observation.incident_id == incident.id, Observation.category.in_(CRUCIAL_SUMMARY_CATEGORIES))
        .all()
    }
    events = [
        e
        for e in all_events
        if e.is_human_added or any(oid in crucial_obs_ids for oid in (e.observation_ids or []))
    ]
    corrections = session.query(HumanCorrection).filter_by(incident_id=incident.id).all()
    return {
        "events": [
            {
                "title": e.title,
                "approx_time_text": e.approx_time_text,
                "perspectives": [
                    {
                        "commander_display_name": p.commander_display_name,
                        "perspective_text": p.perspective_text,
                    }
                    for p in e.perspectives
                    if p.perspective_text
                ]
                or ([{"commander_display_name": None, "perspective_text": e.ai_summary}] if e.ai_summary else []),
            }
            for e in events
        ],
        "human_corrections": [
            {"target_type": c.target_type, "correction_text": c.correction_text} for c in corrections
        ],
    }


def build_narrative_prompt(session: Session, incident: Incident) -> tuple[str, str]:
    system_prompt = build_system_prompt(_ADDENDUM)
    payload = build_narrative_payload(session, incident)
    user_prompt = (
        "Hieronder de gegevens voor de situatieschets.\n\nGEGEVENS (JSON):\n```json\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n```"
    )
    return system_prompt, user_prompt


def run_narrative(session: Session, incident: Incident, provider: LLMProvider) -> SituationNarrativeOutput:
    system_prompt, user_prompt = build_narrative_prompt(session, incident)

    try:
        result = provider.generate_structured(
            system_prompt=system_prompt, user_prompt=user_prompt, response_model=SituationNarrativeOutput
        )
    except LLMOutputValidationError as exc:
        logger.error("Narrative synthesis failed for incident %s: %s", incident.id, exc)
        raise

    incident.ai_situation_narrative = result.narrative.strip()
    session.commit()
    logger.info("Narrative synthesis complete for incident %s.", incident.id)
    return result
