"""Deterministic, rule-based mock LLM provider.

Used by default and by the entire automated test suite so nothing requires a
paid API call (spec §12). It is intentionally simple: it does not attempt
real semantic understanding, only consistent, inspectable, rule-based
behaviour so pipeline mechanics (persistence, evidence linking, the
absolute-time rule, hindsight-bias handling) can be tested without an LLM.
Analytical *quality* (real grouping, real judgement) is the job of a real
provider such as `AnthropicProvider` — this is documented, not hidden.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict

from aar.config.logging_setup import get_logger
from aar.llm.base import LLMProvider
from aar.models.enums import ConfidenceState, DiscussionOrigin, ObservationCategory, ObservationType
from aar.schemas.constants import (
    ASSUMPTION_PHRASES,
    CATEGORY_LABELS_NL,
    CATEGORY_ORDER,
    INFORMATION_MISSING_MARKERS,
    UNCERTAINTY_PHRASES,
)

logger = get_logger("llm.mock")

_JSON_BLOCK_RE = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL)
_TIME_RE = re.compile(r"\b([01]?\d|2[0-3])[:.][0-5]\d\b")


def _extract_payload(user_prompt: str) -> dict:
    match = _JSON_BLOCK_RE.search(user_prompt)
    if not match:
        return {}
    return json.loads(match.group(1))


def _split_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for part in re.split(r"(?<=[.!?])\s+", line):
            part = part.strip()
            if part:
                sentences.append(part)
    return sentences


def _classify_sentence(sentence: str) -> ObservationType:
    lowered = sentence.lower()
    if any(phrase in lowered for phrase in ASSUMPTION_PHRASES):
        return ObservationType.ASSUMPTION
    if any(phrase in lowered for phrase in UNCERTAINTY_PHRASES):
        return ObservationType.UNCERTAINTY
    return ObservationType.HUMAN_OBSERVATION


class MockLLMProvider(LLMProvider):
    def _complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict,
        attempt: int,
        previous_error: str | None,
    ) -> str:
        title = schema.get("title", "")
        payload = _extract_payload(user_prompt)

        if title == "ReportExtraction":
            return json.dumps(self._extraction(payload))
        if title == "ReconstructionOutput":
            return json.dumps(self._reconstruction(payload))
        if title == "FindingsOutput":
            return json.dumps(self._findings(payload))
        if title == "LessonsOutput":
            return json.dumps(self._lessons(payload))

        logger.warning("MockLLMProvider has no rule set for schema %r; returning empty result.", title)
        return json.dumps({})

    # -- Stage 1: extraction --------------------------------------------
    def _extraction(self, payload: dict) -> dict:
        from aar.schemas.constants import SECTION_TO_CATEGORY

        items = []
        for section_key, text in (payload.get("sections") or {}).items():
            category = SECTION_TO_CATEGORY.get(section_key, ObservationCategory.OTHER)
            for sentence in _split_sentences(text):
                obs_type = _classify_sentence(sentence)
                effective_category = category
                if category == ObservationCategory.INFORMATION_AVAILABLE and any(
                    marker in sentence.lower() for marker in INFORMATION_MISSING_MARKERS
                ):
                    effective_category = ObservationCategory.INFORMATION_MISSING
                time_match = _TIME_RE.search(sentence)
                items.append(
                    {
                        "content": sentence,
                        "source_passage": sentence,
                        "observation_type": obs_type.value,
                        "category": effective_category.value,
                        "reported_time_text": time_match.group(0) if time_match else None,
                    }
                )
        return {"commander_report_id": payload.get("commander_report_id"), "items": items}

    # -- Stage 3: reconstruction -----------------------------------------
    def _reconstruction(self, payload: dict) -> dict:
        observations = payload.get("observations") or []
        by_category: dict[str, list[dict]] = defaultdict(list)
        for obs in observations:
            by_category[obs["category"]].append(obs)

        events = []
        for category_value, obs_list in by_category.items():
            try:
                category = ObservationCategory(category_value)
            except ValueError:
                category = ObservationCategory.OTHER
            label = CATEGORY_LABELS_NL.get(category, category_value)
            order_hint = CATEGORY_ORDER.get(category, 99)

            by_report: dict[int, list[dict]] = defaultdict(list)
            for obs in obs_list:
                by_report[obs["commander_report_id"]].append(obs)

            perspectives = []
            commanders = []
            approx_time_text = None
            for report_id, report_obs in by_report.items():
                perspective_text = " ".join(o["content"] for o in report_obs)
                perspectives.append(
                    {
                        "commander_report_id": report_id,
                        "perspective_text": perspective_text,
                        "observation_ids": [o["id"] for o in report_obs],
                    }
                )
                name = report_obs[0].get("commander_display_name")
                if name and name not in commanders:
                    commanders.append(name)
                for o in report_obs:
                    if not approx_time_text and o.get("reported_time_text"):
                        approx_time_text = o["reported_time_text"]

            events.append(
                {
                    "title": label,
                    "order_hint": order_hint,
                    "ai_summary": (
                        f"{len(obs_list)} waarneming(en) van {len(by_report)} "
                        f"commandant(en) met betrekking tot '{label.lower()}'."
                    ),
                    "involved_units": [],
                    "involved_commanders": commanders,
                    "observation_ids": [o["id"] for o in obs_list],
                    "perspectives": perspectives,
                    "approx_time_text": approx_time_text,
                }
            )

        events.sort(key=lambda e: e["order_hint"])
        return {"events": events}

    # -- Stage 5: findings -------------------------------------------------
    def _findings(self, payload: dict) -> dict:
        observations = payload.get("observations") or []
        events = payload.get("events") or []

        def event_title_for(obs_id: int) -> str | None:
            for event in events:
                if obs_id in (event.get("observation_ids") or []):
                    return event.get("title")
            return None

        type_to_origin = {
            ObservationType.ASSUMPTION.value: DiscussionOrigin.ASSUMPTION,
            ObservationType.UNCERTAINTY.value: DiscussionOrigin.UNCERTAINTY,
            ObservationType.CONFLICT.value: DiscussionOrigin.CONFLICT,
        }
        type_to_confidence = {
            ObservationType.ASSUMPTION.value: ConfidenceState.ONZEKER,
            ObservationType.UNCERTAINTY.value: ConfidenceState.ONZEKER,
            ObservationType.CONFLICT.value: ConfidenceState.CONFLICTEREND,
        }

        discussion_points = []
        report_ids_involved: set[int] = set()
        for obs in observations:
            origin = type_to_origin.get(obs["observation_type"])
            if origin is None:
                continue
            report_ids_involved.add(obs.get("commander_report_id"))
            title = obs["content"][:80]
            discussion_points.append(
                {
                    "title": title,
                    "description": obs["content"],
                    "origin_category": origin.value,
                    "confidence_state": type_to_confidence[obs["observation_type"]].value,
                    "observation_ids": [obs["id"]],
                    "event_title": event_title_for(obs["id"]),
                }
            )

        positive_findings = [
            {
                "title": obs["content"][:80],
                "description": obs["content"],
                "observation_ids": [obs["id"]],
                "event_title": event_title_for(obs["id"]),
            }
            for obs in observations
            if obs["category"] == ObservationCategory.WENT_WELL.value
        ]

        ai_observations = []
        if len(report_ids_involved) >= 2:
            ai_observations.append(
                {
                    "content": (
                        "Mogelijk patroon: meerdere commandantenverslagen bevatten "
                        "veronderstellingen, onzekerheden of tegenstrijdigheden over "
                        "gerelateerde momenten — mogelijk de moeite waard om te bespreken."
                    ),
                    "evidence_observation_ids": [
                        obs["id"]
                        for obs in observations
                        if obs["observation_type"] in type_to_origin
                    ],
                }
            )

        return {
            "discussion_points": discussion_points,
            "positive_findings": positive_findings,
            "ai_observations": ai_observations,
        }

    # -- Stage 6: lessons ---------------------------------------------------
    def _lessons(self, payload: dict) -> dict:
        discussion_points = payload.get("discussion_points") or []
        lessons = []
        improvements = []
        for dp in discussion_points:
            lesson_title = f"Leerpunt: {dp['title'][:70]}"
            lessons.append(
                {
                    "title": lesson_title,
                    "description": dp["description"],
                    "discussion_point_titles": [dp["title"]],
                }
            )
            improvements.append(
                {
                    "title": f"Mogelijke verbetering n.a.v.: {dp['title'][:60]}",
                    "description": (
                        f"Overweeg een concrete werkafspraak rond: {dp['description']}"
                    ),
                    "related_lesson_title": lesson_title,
                }
            )
        return {"lessons": lessons, "improvements": improvements}
