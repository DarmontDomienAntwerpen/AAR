"""Dutch display labels for enums — keeps AI/model terminology out of the
facilitator-facing UI (spec §57, §69)."""
from __future__ import annotations

from aar.models.enums import ConfidenceState, DiscussionOrigin, ObservationType

OBSERVATION_TYPE_LABELS_NL = {
    ObservationType.FACT: "Feit (dispatch)",
    ObservationType.HUMAN_OBSERVATION: "Waarneming",
    ObservationType.ASSUMPTION: "Veronderstelling",
    ObservationType.UNCERTAINTY: "Onzekerheid",
    ObservationType.CONFLICT: "Tegenstrijdigheid",
    ObservationType.AI_OBSERVATION: "AI-observatie",
}

DISCUSSION_ORIGIN_LABELS_NL = {
    DiscussionOrigin.UNCERTAINTY: "Onzekerheid",
    DiscussionOrigin.ASSUMPTION: "Veronderstelling",
    DiscussionOrigin.CONFLICT: "Tegenstrijdige perspectieven",
    DiscussionOrigin.GOAL_NOT_ACHIEVED: "Doel niet behaald",
    DiscussionOrigin.UNEXPECTED_RESULT: "Onverwacht resultaat",
    DiscussionOrigin.COORDINATION_ISSUE: "Mogelijk coördinatieprobleem",
    DiscussionOrigin.COMMUNICATION_ISSUE: "Mogelijk communicatieprobleem",
    DiscussionOrigin.SUCCESSFUL_PRACTICE: "Effectieve werkwijze",
    DiscussionOrigin.PATTERN: "Patroon",
    DiscussionOrigin.UNEXPLAINED_DECISION: "Onverklaarde beslissing",
    DiscussionOrigin.MISSING_INFORMATION: "Ontbrekende informatie",
    DiscussionOrigin.OTHER: "Overig",
}

CONFIDENCE_STATE_LABELS_NL = {
    ConfidenceState.ONDERSTEUND: "Ondersteund door bronnen",
    ConfidenceState.DEELS_ONDERSTEUND: "Deels ondersteund",
    ConfidenceState.ONZEKER: "Onzeker",
    ConfidenceState.CONFLICTEREND: "Conflicterend",
    ConfidenceState.ONVOLDOENDE_BEWIJS: "Onvoldoende bewijs",
}
