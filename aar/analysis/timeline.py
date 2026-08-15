"""Stage 4 — dispatch enrichment (spec §36).

Purely deterministic, no LLM. Attaches an authoritative dispatch timestamp to
an `IncidentEvent` only when the overlap between the event's text and a
dispatch record's description is strong and unambiguous. This is a
conservative heuristic, not semantic understanding — when in doubt it leaves
`exact_time` unset, per the absolute-time rule (spec §22): a missed match is
acceptable, a wrong or invented one is not.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from aar.config.logging_setup import get_logger
from aar.models import DispatchRecord, Incident, IncidentEvent

logger = get_logger("analysis.timeline")

_STOPWORDS = {
    "de", "het", "een", "en", "van", "in", "op", "te", "was", "werd", "wordt",
    "voor", "naar", "met", "aan", "bij", "er", "dat", "die", "dit", "we",
    "wij", "zij", "hij", "zijn", "is", "als", "om", "door", "over", "geen",
    "niet", "ook", "nog", "al", "dan", "of", "maar", "uit",
}
_WORD_RE = re.compile(r"[a-zà-ÿ0-9]+", re.IGNORECASE)
_MIN_SHARED_WORDS = 2


def _significant_words(text: str) -> set[str]:
    words = {w.lower() for w in _WORD_RE.findall(text or "")}
    return {w for w in words if len(w) >= 4 and w not in _STOPWORDS}


def _event_text(event: IncidentEvent) -> str:
    parts = [event.title, event.ai_summary]
    parts.extend(event.involved_units or [])
    parts.extend(event.involved_commanders or [])
    return " ".join(p for p in parts if p)


def enrich_with_dispatch_times(session: Session, incident: Incident) -> int:
    """Attach exact_time to events with a clear, unambiguous dispatch match.
    Returns the number of events enriched."""
    events = (
        session.query(IncidentEvent)
        .filter_by(incident_id=incident.id, exact_time_source=None)
        .all()
    )
    records = (
        session.query(DispatchRecord)
        .filter(
            DispatchRecord.incident_id == incident.id,
            DispatchRecord.is_valid.is_(True),
            DispatchRecord.timestamp.isnot(None),
        )
        .all()
    )
    if not events or not records:
        return 0

    record_words = [(r, _significant_words(r.event_description)) for r in records]
    enriched = 0

    for event in events:
        event_words = _significant_words(_event_text(event))
        if not event_words:
            continue

        scored = []
        for record, words in record_words:
            overlap = event_words & words
            if len(overlap) >= _MIN_SHARED_WORDS:
                scored.append((len(overlap), record))

        if not scored:
            continue
        scored.sort(key=lambda pair: pair[0], reverse=True)
        best_score = scored[0][0]
        top_matches = [r for score, r in scored if score == best_score]
        if len(top_matches) != 1:
            continue  # ambiguous — leave unset rather than guess

        best_record = top_matches[0]
        event.exact_time = best_record.timestamp
        event.exact_time_source = f"dispatch_record:{best_record.id}"
        enriched += 1

    session.commit()
    logger.info(
        "Dispatch enrichment for incident %s: %d/%d event(s) enriched.",
        incident.id,
        enriched,
        len(events),
    )
    return enriched
