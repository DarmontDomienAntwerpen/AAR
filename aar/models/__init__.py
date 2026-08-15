"""Import every ORM model so Base.metadata is fully populated before
`Base.metadata.create_all()` or `configure_mappers()` runs."""
from aar.models.correction import AnalysisRun, HumanCorrection
from aar.models.enums import (
    AnalysisRunStatus,
    ConfidenceState,
    CreatedBy,
    DiscussionOrigin,
    IncidentStatus,
    IncidentType,
    ObjectiveAchieved,
    ObservationCategory,
    ObservationType,
    ParseStatus,
    SourceDocumentType,
)
from aar.models.event import EventPerspective, IncidentEvent
from aar.models.findings import DiscussionPoint, Improvement, Lesson, PositiveFinding
from aar.models.incident import Incident
from aar.models.observation import Observation
from aar.models.source import CommanderReport, DispatchRecord, SourceDocument

__all__ = [
    "AnalysisRun",
    "AnalysisRunStatus",
    "CommanderReport",
    "ConfidenceState",
    "CreatedBy",
    "DiscussionOrigin",
    "DiscussionPoint",
    "DispatchRecord",
    "EventPerspective",
    "HumanCorrection",
    "Improvement",
    "Incident",
    "IncidentEvent",
    "IncidentStatus",
    "IncidentType",
    "Lesson",
    "ObjectiveAchieved",
    "Observation",
    "ObservationCategory",
    "ObservationType",
    "ParseStatus",
    "PositiveFinding",
    "SourceDocument",
    "SourceDocumentType",
]
