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
    DECISION_MARKERS,
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


_PLACEHOLDER_RE = re.compile(r"^[\s\-–—.]*$")


def _split_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or _PLACEHOLDER_RE.match(line):
            continue  # e.g. a commander leaving a section as "-" / "n.v.t." to mean "nothing to report"
        for part in re.split(r"(?<=[.!?])\s+", line):
            part = part.strip()
            if part and not _PLACEHOLDER_RE.match(part):
                sentences.append(part)
    return sentences


def _headline(content: str) -> str:
    """A short, distinct label — not the full sentence — so title and
    description don't just duplicate each other in the UI."""
    words = content.split()
    short = " ".join(words[:8])
    return short + ("…" if len(words) > 8 else "")


def _attributed_quote(obs: dict) -> str:
    attributed_to = obs.get("attributed_to")
    if attributed_to:
        return f"{attributed_to}: „{obs['content']}”"
    return obs["content"]


def _evaluation_sentence_category(sentence: str) -> ObservationCategory:
    """The template's 'evaluation' section deliberately bundles wat-ging-goed
    / wat-kon-beter / waarom into one free-text box (spec: fewer, broader
    topics for the commander to fill in) — a real LLM reads the prose and
    tells these apart; the mock can only pattern-match the "Wat ging
    goed:" / "Wat kon beter:" / "Waarom:" prefixes a commander is likely to
    use, and falls back to WENT_WELL when no marker is present."""
    lowered = sentence.lower()
    if "kon beter" in lowered or "ging minder goed" in lowered:
        return ObservationCategory.WENT_LESS_WELL
    if lowered.startswith("waarom") or "waarom:" in lowered:
        return ObservationCategory.WHY
    return ObservationCategory.WENT_WELL


def _classify_sentence(sentence: str) -> ObservationType:
    lowered = sentence.lower()
    if any(phrase in lowered for phrase in ASSUMPTION_PHRASES):
        return ObservationType.ASSUMPTION
    if any(phrase in lowered for phrase in UNCERTAINTY_PHRASES):
        return ObservationType.UNCERTAINTY
    return ObservationType.HUMAN_OBSERVATION


def _parse_action_line_fields(line: str) -> dict[str, str]:
    """Splits one 'Actie: ... | Doel: ... | Resultaat: ... | Toelichting:
    ...' line (see aar.ingestion.commander_docx._extract_actions_table)
    back into its labelled fields."""
    fields: dict[str, str] = {}
    for part in line.split(" | "):
        label, sep, value = part.partition(": ")
        if sep:
            fields[label.strip().lower()] = value.strip()
    return fields


def _extraction_items_for_actions(text: str) -> list[dict]:
    """The 'actions' section comes from the Actie/Doel/Resultaat/Toelichting
    table (structured rows), not free prose. Each row becomes ONE observation
    — actie, doel, resultaat and toelichting joined into a single short,
    readable mini-story, so it reads as one coherent thing that happened
    instead of three disconnected fragments scattered across different
    "Waarnemingen & acties" categories. A real LLM would write this as a
    genuine sentence; the mock can only join the fields with light
    punctuation — same structure, cruder prose (a documented, accepted mock
    limitation, like its other simplifications). Falls back to the old
    sentence-by-sentence heuristic for legacy free-text 'actions' content
    (reports ingested before this table existed)."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or not all(line.lower().startswith("actie:") for line in lines):
        items = []
        for sentence in _split_sentences(text):
            category = (
                ObservationCategory.DECISION
                if any(marker in sentence.lower() for marker in DECISION_MARKERS)
                else ObservationCategory.ACTION
            )
            time_match = _TIME_RE.search(sentence)
            items.append(
                {
                    "content": sentence,
                    "source_passage": sentence,
                    "observation_type": _classify_sentence(sentence).value,
                    "category": category.value,
                    "reported_time_text": time_match.group(0) if time_match else None,
                }
            )
        return items

    items = []
    for line in lines:
        fields = _parse_action_line_fields(line)
        actie = fields.get("actie", "")
        if not actie:
            continue
        doel = fields.get("doel", "")
        resultaat = fields.get("resultaat", "")
        toelichting = fields.get("toelichting", "")

        action_category = (
            ObservationCategory.DECISION
            if any(marker in actie.lower() for marker in DECISION_MARKERS)
            else ObservationCategory.ACTION
        )
        content_parts = [actie.rstrip(".")]
        if doel:
            content_parts.append(f"doel: {doel.rstrip('.').lower()}")
        if resultaat:
            content_parts.append(f"resultaat: {resultaat.lower()}")
        combined_content = ". ".join(content_parts) + "."
        if toelichting:
            combined_content += f" {toelichting}"

        time_match = _TIME_RE.search(actie)
        items.append(
            {
                "content": combined_content,
                "source_passage": line,
                "observation_type": _classify_sentence(actie).value,
                "category": action_category.value,
                "reported_time_text": time_match.group(0) if time_match else None,
            }
        )
    return items


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
        if title == "SituationNarrativeOutput":
            return json.dumps(self._narrative(payload))
        if title == "TextCleanupOutput":
            return json.dumps(self._cleanup(user_prompt))

        logger.warning("MockLLMProvider has no rule set for schema %r; returning empty result.", title)
        return json.dumps({})

    # -- Stage 1: extraction --------------------------------------------
    def _extraction(self, payload: dict) -> dict:
        from aar.schemas.constants import SECTION_TO_CATEGORY
        from aar.schemas.ingestion import COMMANDER_REPORT_SECTION_KEYS

        items = []
        for section_key, text in (payload.get("sections") or {}).items():
            # Legacy pre-template-revision section keys (e.g. "narrative",
            # "evaluation") aren't valid source_section values any more —
            # fall back to "other" for those so old stored reports still
            # extract cleanly.
            source_section = section_key if section_key in COMMANDER_REPORT_SECTION_KEYS else "other"
            if section_key == "actions":
                for item in _extraction_items_for_actions(text):
                    item["source_section"] = source_section
                    items.append(item)
                continue
            category = SECTION_TO_CATEGORY.get(section_key, ObservationCategory.OTHER)
            for sentence in _split_sentences(text):
                obs_type = _classify_sentence(sentence)
                effective_category = category
                if category in (ObservationCategory.OBSERVATION, ObservationCategory.INFORMATION_AVAILABLE) and any(
                    marker in sentence.lower() for marker in INFORMATION_MISSING_MARKERS
                ):
                    effective_category = ObservationCategory.INFORMATION_MISSING
                if section_key == "evaluation":
                    effective_category = _evaluation_sentence_category(sentence)
                time_match = _TIME_RE.search(sentence)
                items.append(
                    {
                        "content": sentence,
                        "source_passage": sentence,
                        "source_section": source_section,
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
            attributed_segments = []
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
                if perspective_text:
                    attributed_segments.append(
                        f"{name}: {perspective_text}" if name else perspective_text
                    )
                for o in report_obs:
                    if not approx_time_text and o.get("reported_time_text"):
                        approx_time_text = o["reported_time_text"]

            # Show actual reported content, per commander, instead of a
            # meta-description or an unattributed run-on paragraph — merging
            # multiple commanders' wording into one voiceless narrative would
            # misrepresent it as a single agreed-upon account.
            summary_text = "  |  ".join(attributed_segments)
            if not summary_text:
                summary_text = f"Geen inhoud gerapporteerd voor '{label.lower()}'."

            events.append(
                {
                    "title": label,
                    "order_hint": order_hint,
                    "ai_summary": summary_text,
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
            discussion_points.append(
                {
                    "title": _headline(obs["content"]),
                    "description": _attributed_quote(obs),
                    "origin_category": origin.value,
                    "confidence_state": type_to_confidence[obs["observation_type"]].value,
                    "observation_ids": [obs["id"]],
                    "event_title": event_title_for(obs["id"]),
                }
            )

        positive_findings = [
            {
                "title": _headline(obs["content"]),
                "description": _attributed_quote(obs),
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
                        "Mogelijk patroon: meerdere bevelvoerdersverslagen bevatten "
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
        from aar.models.enums import DiscussionOrigin
        from aar.ui.labels import DISCUSSION_ORIGIN_LABELS_NL

        discussion_points = payload.get("discussion_points") or []

        # Group by theme (origin category) instead of emitting one lesson
        # per discussion point — nine near-identical uncertainty statements
        # don't need nine near-identical lessons, they need one lesson about
        # that recurring pattern, evidenced by all of them.
        by_category: dict[str, list[dict]] = defaultdict(list)
        for dp in discussion_points:
            by_category[dp.get("origin_category", "other")].append(dp)

        lessons = []
        improvements = []
        for category_value, dps in by_category.items():
            try:
                category = DiscussionOrigin(category_value)
            except ValueError:
                category = DiscussionOrigin.OTHER
            label = DISCUSSION_ORIGIN_LABELS_NL.get(category, category_value)

            # The mock cannot actually synthesise what these dps have in
            # common (that needs real language understanding) — say so
            # honestly in one short sentence rather than faking a summary
            # by pasting example descriptions together with semicolons.
            lesson_title = f"{label} ({len(dps)}x aangetroffen)"
            description = (
                f"Dit thema ({label.lower()}) kwam {len(dps)}x voor bij "
                f"verschillende bevelvoerders. Zie de gekoppelde bespreekpunten "
                f"hieronder voor de specifieke gevallen."
            )
            lessons.append(
                {
                    "title": lesson_title,
                    "description": description,
                    "discussion_point_titles": [dp["title"] for dp in dps],
                }
            )
            improvements.append(
                {
                    "title": f"Mogelijke verbetering: {label.lower()}",
                    "description": (
                        f"Overweeg een concrete werkafspraak om herhaling van dit type "
                        f"situatie ({label.lower()}) te voorkomen."
                    ),
                    "related_lesson_title": lesson_title,
                }
            )
        return {"lessons": lessons, "improvements": improvements}

    # -- Stage 7: situation narrative ---------------------------------------
    def _narrative(self, payload: dict) -> dict:
        """Honest, explicitly-labelled fallback: this mock has no semantic
        understanding, so it cannot actually merge accounts into one
        narrative (that needs a real LLM — see `aar/analysis/narrative.py`
        module docstring). It joins the per-event, per-commander lines
        instead of pretending to synthesise them."""
        events = payload.get("events") or []
        blocks: list[str] = []
        for event in events:
            lines = [
                f"{p['commander_display_name']}: {p['perspective_text']}" if p.get("commander_display_name")
                else p["perspective_text"]
                for p in event.get("perspectives") or []
                if p.get("perspective_text")
            ]
            if lines:
                blocks.append(event.get("title", "") + " — " + " ".join(lines))
        narrative = "\n\n".join(blocks) if blocks else "Geen incidentmomenten beschikbaar voor een situatieschets."
        return {"narrative": narrative}

    # -- on-demand text cleanup --------------------------------------------
    def _cleanup(self, user_prompt: str) -> dict:
        """Honest no-op: proofreading/typo-fixing needs real language
        understanding this mock doesn't have — return the text unchanged
        rather than pretending to improve it."""
        marker = "Op te schonen tekst:\n\n"
        text = user_prompt.split(marker, 1)[1] if marker in user_prompt else user_prompt
        return {"text": text.strip()}
