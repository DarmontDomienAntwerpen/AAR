"""Stage 6 — lessons learned & improvement proposals (spec §42-43).

These are explicitly proposals, never organisational truth (spec §42) and
never tied to an owner/deadline/status — there is no action tracking in v1
(spec §44).
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from aar.config.logging_setup import get_logger
from aar.llm.base import LLMOutputValidationError, LLMProvider
from aar.llm.prompts.system_prompts import build_system_prompt
from aar.models import DiscussionPoint, Improvement, Incident, Lesson, PositiveFinding
from aar.schemas.lessons import LessonsOutput

logger = get_logger("analysis.lessons")

_ADDENDUM = """\
TAAK: Voorstellen van leerpunten en mogelijke verbeteringen.

Je krijgt de bespreekpunten en positieve punten die al werden vastgesteld. \
Stel op basis daarvan leerpunten (lessons) en mogelijke verbeteringen \
(improvements) voor. Dit zijn voorstellen ter bespreking, geen \
vaststaande conclusies. Ken geen eigenaar, deadline of status toe — dat \
valt buiten deze tool. Wijs geen schuld toe. Baseer je uitsluitend op de \
meegegeven bespreek- en positieve punten.\
"""


def build_lessons_payload(session: Session, incident: Incident) -> dict:
    discussion_points = session.query(DiscussionPoint).filter_by(incident_id=incident.id).all()
    positive_findings = session.query(PositiveFinding).filter_by(incident_id=incident.id).all()
    return {
        "discussion_points": [
            {"title": dp.title, "description": dp.description, "origin_category": dp.origin_category.value}
            for dp in discussion_points
        ],
        "positive_findings": [
            {"title": pf.title, "description": pf.description} for pf in positive_findings
        ],
    }


def build_lessons_prompt(session: Session, incident: Incident) -> tuple[str, str]:
    system_prompt = build_system_prompt(_ADDENDUM)
    payload = build_lessons_payload(session, incident)
    user_prompt = (
        "Hieronder de gegevens voor leerpunten.\n\nGEGEVENS (JSON):\n```json\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n```"
    )
    return system_prompt, user_prompt


def run_lessons(session: Session, incident: Incident, provider: LLMProvider) -> LessonsOutput:
    system_prompt, user_prompt = build_lessons_prompt(session, incident)

    try:
        result = provider.generate_structured(
            system_prompt=system_prompt, user_prompt=user_prompt, response_model=LessonsOutput
        )
    except LLMOutputValidationError as exc:
        logger.error("Lessons generation failed for incident %s: %s", incident.id, exc)
        raise

    dp_ids_by_title = {
        dp.title: dp.id for dp in session.query(DiscussionPoint).filter_by(incident_id=incident.id).all()
    }

    session.query(Lesson).filter_by(incident_id=incident.id, is_human_added=False).delete()
    session.query(Improvement).filter_by(incident_id=incident.id, is_human_added=False).delete()
    session.flush()

    lesson_ids_by_title: dict[str, int] = {}
    for lesson in result.lessons:
        row = Lesson(
            incident_id=incident.id,
            title=lesson.title,
            description=lesson.description,
            discussion_point_ids=[
                dp_ids_by_title[t] for t in lesson.discussion_point_titles if t in dp_ids_by_title
            ],
            is_human_added=False,
        )
        session.add(row)
        session.flush()
        lesson_ids_by_title[lesson.title] = row.id

    for improvement in result.improvements:
        session.add(
            Improvement(
                incident_id=incident.id,
                title=improvement.title,
                description=improvement.description,
                related_lesson_id=lesson_ids_by_title.get(improvement.related_lesson_title)
                if improvement.related_lesson_title
                else None,
                is_human_added=False,
            )
        )

    session.commit()
    logger.info(
        "Lessons complete for incident %s: %d lesson(s), %d improvement(s).",
        incident.id,
        len(result.lessons),
        len(result.improvements),
    )
    return result
