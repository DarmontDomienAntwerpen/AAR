"""Stage 1 — per-report structured extraction (spec §33).

Runs independently per commander report. Persists one `Observation` row per
extracted item, each carrying its verbatim source passage. Re-running this
stage for a report replaces that report's previous AI-generated observations
(idempotent — safe to call again after a re-upload of the same content).
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from aar.config.logging_setup import get_logger
from aar.llm.base import LLMOutputValidationError, LLMProvider
from aar.llm.prompts.system_prompts import build_system_prompt
from aar.models import CommanderReport, CreatedBy, Observation, ParseStatus
from aar.schemas.constants import SECTION_ORDER
from aar.schemas.extraction import ReportExtraction

logger = get_logger("analysis.extraction")

_ADDENDUM = """\
TAAK: Structurele extractie van één bevelvoerdersverslag.

Je krijgt de secties van één bevelvoerdersverslag als JSON. Extraheer voor \
elke relevante uitspraak een item met:
- source_passage: de LETTERLIJKE brontekst (kopieer exact, verzin niets bij).
- source_section: de exacte sleutelnaam van de sectie in de GEGEVENS waar dit \
item vandaan komt (bv. "situation", "actions", "went_well", "went_less_well", \
"other", "difficulties") — dit bepaalt onder welk tabblad-onderdeel het item \
getoond wordt, dus moet exact overeenkomen met de sectie waar de brontekst \
letterlijk stond, ONGEACHT welke category je hieronder kiest. Bv. een zin uit \
"other" die inhoudelijk als een inschatting leest, krijgt toch \
source_section "other" — categoriseer de INHOUD apart via category, verplaats \
het item niet naar een andere sectie.
- content: een korte, telegramstijl herformulering van diezelfde uitspraak — \
zie kernprincipe over beknoptheid en de vaste afkortingen (HD/LD/SAR/SO/V+nummer). \
Bv. "ik zag rookontwikkeling maar niet veel" wordt "Lichte rook". Dit veld is \
wat de facilitator scant om snel te weten wat er gebeurde; de volledige, \
letterlijke uitspraak blijft altijd apart bewaard in source_passage — er gaat \
dus niets verloren.
- observation_type: op dit niveau (één enkele bron) gebruik je uitsluitend \
"human_observation", "assumption" of "uncertainty" — nooit "fact" (dat is \
voorbehouden voor geregistreerde dispatchgegevens), "conflict" (dat vereist \
vergelijking met andere bronnen) of "ai_observation" (dat is een latere \
analysestap).
- category: observation / information_available / information_missing / \
assessment / decision / objective / action / result / went_well / \
went_less_well / why / other — kies wat het best past bij het type inhoud.
- reported_time_text: alleen invullen als de bevelvoerder zelf een tijdstip \
noemt (letterlijk overnemen, bv. "rond 14:20"). Laat leeg als er geen \
tijdstip vermeld wordt — verzin er nooit één bij.

Sla lege secties gewoon over. Maak geen items van secties zonder inhoud.

BELANGRIJK voor de sectie "actions": die bevat per actie de velden Actie, \
Doel, Resultaat en eventueel Toelichting, gescheiden door " | " op één \
regel. Maak hier GEEN apart item per veld van — voeg elke actie samen tot \
ÉÉN observatie per actie, met een kort maar samenhangend verhaaltje in \
content (dit is de uitzondering op de telegramstijl uit regel 12): wat er \
gebeurde, met welk doel, en wat het resultaat was — inclusief de reden bij \
een gedeeltelijk of niet geslaagde actie. Bv. "Interne aanval via voordeur \
ingezet om de brand snel te blussen — gedeeltelijk geslaagd, want de \
controle van de achterzijde gebeurde later dan bedoeld." Gebruik category \
"decision" als de actie een bewuste keuze beschrijft (bv. "besliste \
om..."/"besloten..."), anders "action". source_passage blijft de volledige \
originele regel (Actie: ... | Doel: ... | Resultaat: ... | Toelichting: ...).

BELANGRIJK voor de secties "went_less_well" en "other": dit zijn de tabs \
"Werkpunten" en "Extra opmerkingen" — daar wordt NOOIT geselecteerd of \
samengevoegd (elke losse uitspraak in deze secties wordt een eigen item, \
dus er gaat inhoudelijk niets verloren en er wordt niets herschikt of \
gegroepeerd). Wat wél mag: content is hier GEEN telegramstijl-fragment \
(dat is de uitzondering op regel 12), maar een normale, vlot leesbare volzin \
— corrigeer spelling/grammatica/interpunctie en maak er een nette zin van, \
zonder de inhoud te wijzigen, samen te vatten of weg te laten. \
Bv. "politie voertuig stond in de weg bij het plaatsen van de al" wordt \
"Het politievoertuig stond in de weg bij het plaatsen van de AL." — dezelfde \
uitspraak, gewoon netjes geschreven. source_passage blijft zoals altijd de \
letterlijke originele tekst.\
"""


def _source_order_key(report: CommanderReport, item, fallback_index: int) -> tuple:
    """Where an item's source_passage literally sits in its own raw section
    text — the LLM's emission order is not reliable evidence of the true
    sentence order within a section (seen in practice: two facts pulled
    from the same continuous paragraph coming back reversed), but the
    literal source text itself is a fixed, deterministic ground truth we
    already have. An unmatched passage (paraphrased instead of copied
    exactly) sorts to the end of its section rather than the front, so a
    mismatch can't jump ahead of correctly-matched items."""
    section_text = (report.raw_sections or {}).get(item.source_section, "") or ""
    idx = section_text.find(item.source_passage) if item.source_passage else -1
    if idx < 0:
        idx = len(section_text)
    return (SECTION_ORDER.get(item.source_section, 99), idx, fallback_index)


def build_extraction_payload(report: CommanderReport) -> dict:
    return {"commander_report_id": report.id, "sections": report.raw_sections}


def build_extraction_prompt(report: CommanderReport) -> tuple[str, str]:
    system_prompt = build_system_prompt(_ADDENDUM)
    payload = build_extraction_payload(report)
    user_prompt = (
        "Hieronder de gegevens voor extractie.\n\nGEGEVENS (JSON):\n```json\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n```"
    )
    return system_prompt, user_prompt


def run_extraction(
    session: Session, report: CommanderReport, provider: LLMProvider
) -> ReportExtraction:
    system_prompt, user_prompt = build_extraction_prompt(report)

    try:
        result = provider.generate_structured(
            system_prompt=system_prompt, user_prompt=user_prompt, response_model=ReportExtraction
        )
    except LLMOutputValidationError as exc:
        report.extraction_status = ParseStatus.ERROR
        report.extraction_error = str(exc)
        session.commit()
        logger.error("Extraction failed for report %s: %s", report.id, exc)
        raise

    session.query(Observation).filter_by(
        commander_report_id=report.id, created_by=CreatedBy.AI
    ).delete()

    ordered_items = sorted(
        enumerate(result.items),
        key=lambda pair: _source_order_key(report, pair[1], pair[0]),
    )
    for _, item in ordered_items:
        session.add(
            Observation(
                incident_id=report.incident_id,
                commander_report_id=report.id,
                observation_type=item.observation_type,
                category=item.category,
                content=item.content,
                source_passage=item.source_passage,
                source_section=item.source_section,
                attributed_to=report.display_name,
                reported_time_text=item.reported_time_text,
                created_by=CreatedBy.AI,
            )
        )

    report.extraction_status = ParseStatus.PARSED
    report.extraction_error = None
    session.commit()
    logger.info("Extraction complete for report %s: %d item(s).", report.id, len(result.items))
    return result
