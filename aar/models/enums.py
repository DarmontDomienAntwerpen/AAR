"""Shared enums used by both the SQLAlchemy models and the Pydantic schemas.

Kept as plain `str` enums (not SQLAlchemy-specific) so they have zero
framework coupling and can be imported anywhere in the codebase.
"""
from __future__ import annotations

from enum import Enum


class IncidentType(str, Enum):
    BRAND = "Brand"
    TECHNISCHE_HULPVERLENING = "Technische hulpverlening"
    GEVAARLIJKE_STOFFEN = "Incident gevaarlijke stoffen"
    WATERONGEVAL = "Waterongeval"


class IncidentStatus(str, Enum):
    DRAFT = "draft"
    SOURCES_UPLOADED = "sources_uploaded"
    ANALYZED = "analyzed"
    IN_REVIEW = "in_review"
    FINALIZED = "finalized"


class SourceDocumentType(str, Enum):
    COMMANDER_REPORT = "commander_report"
    DISPATCH_EXCEL = "dispatch_excel"


class ParseStatus(str, Enum):
    PENDING = "pending"
    PARSED = "parsed"
    ERROR = "error"


class ObjectiveAchieved(str, Enum):
    JA = "Ja"
    GEDEELTELIJK = "Gedeeltelijk"
    NEE = "Nee"
    NIET_TE_BEOORDELEN = "Niet te beoordelen"


class ObservationType(str, Enum):
    """The six semantic information categories required by spec §24-30."""

    FACT = "fact"
    HUMAN_OBSERVATION = "human_observation"
    ASSUMPTION = "assumption"
    UNCERTAINTY = "uncertainty"
    CONFLICT = "conflict"
    AI_OBSERVATION = "ai_observation"


class ObservationCategory(str, Enum):
    """Maps to the decision-analysis model in spec §17."""

    OBSERVATION = "observation"
    INFORMATION_AVAILABLE = "information_available"
    INFORMATION_MISSING = "information_missing"
    ASSESSMENT = "assessment"
    DECISION = "decision"
    OBJECTIVE = "objective"
    ACTION = "action"
    RESULT = "result"
    WENT_WELL = "went_well"
    WENT_LESS_WELL = "went_less_well"
    WHY = "why"
    OTHER = "other"


class ConfidenceState(str, Enum):
    """Semantic confidence states — no fabricated numeric precision (spec §56)."""

    ONDERSTEUND = "ondersteund"
    DEELS_ONDERSTEUND = "deels_ondersteund"
    ONZEKER = "onzeker"
    CONFLICTEREND = "conflicterend"
    ONVOLDOENDE_BEWIJS = "onvoldoende_bewijs"


class DiscussionOrigin(str, Enum):
    """Candidate discussion point origins, per spec §41."""

    UNCERTAINTY = "uncertainty"
    ASSUMPTION = "assumption"
    CONFLICT = "conflict"
    GOAL_NOT_ACHIEVED = "goal_not_achieved"
    UNEXPECTED_RESULT = "unexpected_result"
    COORDINATION_ISSUE = "coordination_issue"
    COMMUNICATION_ISSUE = "communication_issue"
    SUCCESSFUL_PRACTICE = "successful_practice"
    PATTERN = "pattern"
    UNEXPLAINED_DECISION = "unexplained_decision"
    MISSING_INFORMATION = "missing_information"
    OTHER = "other"


class CreatedBy(str, Enum):
    AI = "ai"
    HUMAN = "human"


class AnalysisRunStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
