"""Shared lookup tables used by both the analysis pipeline and the mock LLM
provider, so the two stay consistent without the mock depending on the
analysis package."""
from __future__ import annotations

from aar.models.enums import ObservationCategory

SECTION_TO_CATEGORY: dict[str, ObservationCategory] = {
    # Current (simplified, 5-section) template. "actions" is a fallback only
    # — the mock provider parses that section's table-derived text itself
    # (see aar.llm.mock._extraction_items_for_actions) to split each row
    # into its own Actie/Doel/Resultaat categories.
    "situation": ObservationCategory.OBSERVATION,
    "actions": ObservationCategory.ACTION,
    "went_well": ObservationCategory.WENT_WELL,
    "went_less_well": ObservationCategory.WENT_LESS_WELL,
    "other": ObservationCategory.OTHER,
    "difficulties": ObservationCategory.WENT_LESS_WELL,
    # Superseded template keys — kept so reports already ingested under an
    # older template still categorise sensibly under the mock provider if
    # re-analysed. Safe to drop once no stored CommanderReport.raw_sections
    # still uses these.
    "observations": ObservationCategory.OBSERVATION,
    "information_position": ObservationCategory.INFORMATION_AVAILABLE,
    "assessment": ObservationCategory.ASSESSMENT,
    "decision": ObservationCategory.DECISION,
    "objective": ObservationCategory.OBJECTIVE,
    "narrative": ObservationCategory.ACTION,
    "result": ObservationCategory.RESULT,
    "why": ObservationCategory.WHY,
    "doubts_assumptions": ObservationCategory.OTHER,
    "evaluation": ObservationCategory.WENT_WELL,  # briefly-used merged went_well+went_less_well+why box
}

CATEGORY_LABELS_NL: dict[ObservationCategory, str] = {
    ObservationCategory.OBSERVATION: "Waarnemingen bij aankomst",
    ObservationCategory.INFORMATION_AVAILABLE: "Beschikbare informatie",
    ObservationCategory.INFORMATION_MISSING: "Ontbrekende informatie",
    ObservationCategory.ASSESSMENT: "Inschatting",
    ObservationCategory.DECISION: "Beslissing",
    ObservationCategory.OBJECTIVE: "Doelstelling",
    ObservationCategory.ACTION: "Verloop van de actie",
    ObservationCategory.RESULT: "Resultaat",
    ObservationCategory.WENT_WELL: "Wat ging goed",
    ObservationCategory.WENT_LESS_WELL: "Wat ging minder goed",
    ObservationCategory.WHY: "Verklaring",
    ObservationCategory.OTHER: "Overige waarnemingen",
}

# Which observation categories are decision-relevant enough to belong in a
# *short* situation overview (used by both the deterministic fallback
# summary and Stage 7 narrative synthesis input). Deliberately excludes the
# more granular/procedural categories (raw observations, available/missing
# information, assessment, narrative action, general remarks) — those stay
# fully visible on "Waarnemingen & acties" and the Incidentverloop tab, just
# not repeated in the short overview.
CRUCIAL_SUMMARY_CATEGORIES: set[ObservationCategory] = {
    ObservationCategory.OBSERVATION,
    ObservationCategory.ACTION,
    ObservationCategory.DECISION,
    ObservationCategory.RESULT,
    ObservationCategory.OBJECTIVE,
    ObservationCategory.WENT_WELL,
    ObservationCategory.WENT_LESS_WELL,
}

# Broader thematic grouping for "Waarnemingen & acties": the 12 raw
# categories are too fine-grained to read as one story — group into the
# narrative arc a commander's account naturally follows (what I saw/knew →
# what I decided → what I did → what happened → how it went), rendered
# top-to-bottom in a single column so reading order == chronological order.
# Wat ging goed / minder goed stay their own groups (not folded into a
# generic "evaluation" bucket) so the existing green/red distinction isn't lost.
CATEGORY_SUPERGROUP: dict[ObservationCategory, str] = {
    ObservationCategory.OBSERVATION: "feiten",
    ObservationCategory.INFORMATION_AVAILABLE: "feiten",
    ObservationCategory.INFORMATION_MISSING: "feiten",
    ObservationCategory.ASSESSMENT: "inschatting",
    ObservationCategory.DECISION: "inschatting",
    ObservationCategory.OBJECTIVE: "inschatting",
    ObservationCategory.ACTION: "acties",
    ObservationCategory.RESULT: "resultaat",
    ObservationCategory.WENT_WELL: "goed",
    ObservationCategory.WENT_LESS_WELL: "minder_goed",
    ObservationCategory.WHY: "overig",
    ObservationCategory.OTHER: "overig",
}

SUPERGROUP_LABELS_NL: dict[str, str] = {
    "feiten": "Feiten & informatie",
    "inschatting": "Inschatting & beslissing",
    "acties": "Acties",
    "resultaat": "Resultaat",
    "goed": "Wat ging goed",
    "minder_goed": "Wat ging minder goed",
    "overig": "Verklaring & overig",
}

SUPERGROUP_ORDER: dict[str, int] = {
    "feiten": 1,
    "inschatting": 2,
    "acties": 3,
    "resultaat": 4,
    "goed": 5,
    "minder_goed": 6,
    "overig": 7,
}

CATEGORY_ORDER: dict[ObservationCategory, int] = {
    ObservationCategory.OBSERVATION: 1,
    ObservationCategory.INFORMATION_AVAILABLE: 2,
    ObservationCategory.INFORMATION_MISSING: 2,
    ObservationCategory.ASSESSMENT: 3,
    ObservationCategory.DECISION: 4,
    ObservationCategory.OBJECTIVE: 5,
    ObservationCategory.ACTION: 6,
    ObservationCategory.RESULT: 7,
    ObservationCategory.WENT_WELL: 8,
    ObservationCategory.WENT_LESS_WELL: 8,
    ObservationCategory.WHY: 8,
    ObservationCategory.OTHER: 9,
}

# Spec §27/§28 example phrasing — used by the mock provider's rule-based
# tagging. The real LLM does this semantically; these are a coarse stand-in.
ASSUMPTION_PHRASES = [
    "ik ging ervan uit",
    "ik dacht dat",
    "ik veronderstelde",
    "ik nam aan",
    "ervan uitgaande dat",
]
UNCERTAINTY_PHRASES = [
    "volgens mij",
    "waarschijnlijk",
    "ik weet niet zeker",
    "mogelijk",
    "vermoedelijk",
    "ik vermoed",
]
INFORMATION_MISSING_MARKERS = ["niet geweten", "onbekend", "ontbrak", "geen informatie", "niet duidelijk"]

# The template's "actions" section bundles what a commander decided AND what
# they then did (spec: fewer, broader topics) — these markers let the mock
# still pick the decision-specific sentences out of that free text, matching
# what a real LLM would infer from content regardless of section.
DECISION_MARKERS = ["besliste", "besloten", "koos ervoor", "kozen ervoor"]

# Identity fields (callsign, officiële eenheidsnaam) are never run through an
# LLM — deterministic ingestion only, so spelling/casing/full-name variants
# of the same real unit ("1HPLO", "1h plo", "eerste hulp plo") would
# otherwise show up as different-looking rows on the roster. These alias
# tables canonicalise known variants; add to them as new ones turn up in
# real reports — there's no way to predict every zone's naming conventions
# up front. Matched on whitespace-collapsed, lowercased text (see
# aar.ingestion.commander_docx.canonicalize_unit_name / canonicalize_callsign).
UNIT_NAME_ALIASES: dict[str, str] = {
    "1hplo": "1H PLO",
    "1h plo": "1H PLO",
    "eerste hulp plo": "1H PLO",
}
CALLSIGN_ALIASES: dict[str, str] = {}
