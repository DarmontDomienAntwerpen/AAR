"""Shared lookup tables used by both the analysis pipeline and the mock LLM
provider, so the two stay consistent without the mock depending on the
analysis package."""
from __future__ import annotations

from aar.models.enums import ObservationCategory

SECTION_TO_CATEGORY: dict[str, ObservationCategory] = {
    "observations": ObservationCategory.OBSERVATION,
    "information_position": ObservationCategory.INFORMATION_AVAILABLE,
    "assessment": ObservationCategory.ASSESSMENT,
    "decision": ObservationCategory.DECISION,
    "objective": ObservationCategory.OBJECTIVE,
    "narrative": ObservationCategory.ACTION,
    "result": ObservationCategory.RESULT,
    "went_well": ObservationCategory.WENT_WELL,
    "went_less_well": ObservationCategory.WENT_LESS_WELL,
    "why": ObservationCategory.WHY,
    "doubts_assumptions": ObservationCategory.OTHER,
    "other": ObservationCategory.OTHER,
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
