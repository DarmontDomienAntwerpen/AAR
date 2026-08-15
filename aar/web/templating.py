"""Jinja2 environment: templates dir, Dutch-formatting filters, and the
enum→label dictionaries shared with the (removed) Streamlit UI so the
Dutch-only-in-the-UI rule (spec §57) stays centralised in one place."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from fastapi.templating import Jinja2Templates

from aar.models.enums import DiscussionOrigin, IncidentStatus, IncidentType, ObjectiveAchieved
from aar.ui.labels import CONFIDENCE_STATE_LABELS_NL, DISCUSSION_ORIGIN_LABELS_NL, OBSERVATION_TYPE_LABELS_NL

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _fmt_date(value: dt.date | dt.datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime("%d-%m-%Y")


def _fmt_time(value: dt.datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime("%H:%M")


def _fmt_datetime(value: dt.datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime("%d-%m-%Y %H:%M")


STATUS_LABELS_NL = {
    IncidentStatus.DRAFT: "Concept",
    IncidentStatus.SOURCES_UPLOADED: "Bronnen geüpload",
    IncidentStatus.ANALYZED: "Geanalyseerd",
    IncidentStatus.IN_REVIEW: "In beoordeling",
    IncidentStatus.FINALIZED: "Afgerond",
}

STATUS_BADGE_CLASSES = {
    IncidentStatus.DRAFT: "bg-ink-100 text-ink-600",
    IncidentStatus.SOURCES_UPLOADED: "bg-sky-50 text-sky-700",
    IncidentStatus.ANALYZED: "bg-amber-50 text-amber-700",
    IncidentStatus.IN_REVIEW: "bg-accent-100 text-accent-700",
    IncidentStatus.FINALIZED: "bg-emerald-50 text-emerald-700",
}


ORIGIN_BORDER_CLASSES = {
    DiscussionOrigin.UNCERTAINTY: "border-l-amber-400",
    DiscussionOrigin.ASSUMPTION: "border-l-amber-400",
    DiscussionOrigin.CONFLICT: "border-l-rose-400",
    DiscussionOrigin.GOAL_NOT_ACHIEVED: "border-l-rose-400",
    DiscussionOrigin.UNEXPECTED_RESULT: "border-l-rose-300",
    DiscussionOrigin.COORDINATION_ISSUE: "border-l-amber-400",
    DiscussionOrigin.COMMUNICATION_ISSUE: "border-l-amber-400",
    DiscussionOrigin.SUCCESSFUL_PRACTICE: "border-l-emerald-400",
    DiscussionOrigin.PATTERN: "border-l-accent-400",
    DiscussionOrigin.UNEXPLAINED_DECISION: "border-l-rose-300",
    DiscussionOrigin.MISSING_INFORMATION: "border-l-amber-300",
    DiscussionOrigin.OTHER: "border-l-slate-300",
}

templates.env.globals["origin_border_class"] = lambda o: ORIGIN_BORDER_CLASSES.get(o, "border-l-slate-300")

OBJECTIVE_BADGE_CLASSES = {
    ObjectiveAchieved.JA: "bg-emerald-50 text-emerald-700",
    ObjectiveAchieved.GEDEELTELIJK: "bg-amber-50 text-amber-700",
    ObjectiveAchieved.NEE: "bg-rose-50 text-rose-700",
    ObjectiveAchieved.NIET_TE_BEOORDELEN: "bg-slate-100 text-slate-500",
}
templates.env.globals["objective_badge_class"] = lambda o: OBJECTIVE_BADGE_CLASSES.get(o, "bg-slate-100 text-slate-500")

COMMANDER_SECTION_FIELDS = [
    ("observations", "Waarnemingen"),
    ("assessment", "Inschatting"),
    ("decision", "Beslissing"),
    ("result", "Resultaat"),
    ("went_well", "Wat ging goed"),
    ("went_less_well", "Wat ging minder goed"),
]
templates.env.globals["commander_section_fields"] = COMMANDER_SECTION_FIELDS
templates.env.filters["nl_date"] = _fmt_date
templates.env.filters["nl_time"] = _fmt_time
templates.env.filters["nl_datetime"] = _fmt_datetime
templates.env.globals["IncidentType"] = IncidentType
templates.env.globals["status_label"] = lambda s: STATUS_LABELS_NL.get(s, getattr(s, "value", str(s)))
templates.env.globals["status_badge_class"] = lambda s: STATUS_BADGE_CLASSES.get(s, "bg-ink-100 text-ink-600")
templates.env.globals["origin_label"] = lambda o: DISCUSSION_ORIGIN_LABELS_NL.get(o, getattr(o, "value", str(o)))
templates.env.globals["confidence_label"] = lambda c: CONFIDENCE_STATE_LABELS_NL.get(c, getattr(c, "value", str(c)))
templates.env.globals["observation_type_label"] = lambda t: OBSERVATION_TYPE_LABELS_NL.get(t, getattr(t, "value", str(t)))
