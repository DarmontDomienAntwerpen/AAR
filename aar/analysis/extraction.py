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
from aar.schemas.extraction import ReportExtraction

logger = get_logger("analysis.extraction")

_ADDENDUM = """\
TAAK: Structurele extractie van één commandantenverslag.

Je krijgt de secties van één commandantenverslag als JSON. Extraheer voor \
elke relevante uitspraak een item met:
- source_passage: de LETTERLIJKE brontekst (kopieer exact, verzin niets bij).
- content: een genormaliseerde/geïnterpreteerde versie van diezelfde uitspraak.
- observation_type: op dit niveau (één enkele bron) gebruik je uitsluitend \
"human_observation", "assumption" of "uncertainty" — nooit "fact" (dat is \
voorbehouden voor geregistreerde dispatchgegevens), "conflict" (dat vereist \
vergelijking met andere bronnen) of "ai_observation" (dat is een latere \
analysestap).
- category: observation / information_available / information_missing / \
assessment / decision / objective / action / result / went_well / \
went_less_well / why / other — kies wat het best past bij het type inhoud.
- reported_time_text: alleen invullen als de commandant zelf een tijdstip \
noemt (letterlijk overnemen, bv. "rond 14:20"). Laat leeg als er geen \
tijdstip vermeld wordt — verzin er nooit één bij.

Sla lege secties gewoon over. Maak geen items van secties zonder inhoud.\
"""


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

    for item in result.items:
        session.add(
            Observation(
                incident_id=report.incident_id,
                commander_report_id=report.id,
                observation_type=item.observation_type,
                category=item.category,
                content=item.content,
                source_passage=item.source_passage,
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
