"""Jinja2 environment: templates dir, Dutch-formatting filters, and the
enum→label dictionaries shared with the (removed) Streamlit UI so the
Dutch-only-in-the-UI rule (spec §57) stays centralised in one place."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from fastapi.templating import Jinja2Templates

from aar.models.enums import IncidentStatus, IncidentType
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
    IncidentStatus.DRAFT: "bg-slate-100 text-slate-600",
    IncidentStatus.SOURCES_UPLOADED: "bg-sky-50 text-sky-700",
    IncidentStatus.ANALYZED: "bg-amber-50 text-amber-700",
    IncidentStatus.IN_REVIEW: "bg-indigo-50 text-indigo-700",
    IncidentStatus.FINALIZED: "bg-emerald-50 text-emerald-700",
}


templates.env.filters["nl_date"] = _fmt_date
templates.env.filters["nl_time"] = _fmt_time
templates.env.filters["nl_datetime"] = _fmt_datetime
templates.env.globals["IncidentType"] = IncidentType
templates.env.globals["status_label"] = lambda s: STATUS_LABELS_NL.get(s, getattr(s, "value", str(s)))
templates.env.globals["status_badge_class"] = lambda s: STATUS_BADGE_CLASSES.get(s, "bg-slate-100 text-slate-600")
templates.env.globals["origin_label"] = lambda o: DISCUSSION_ORIGIN_LABELS_NL.get(o, getattr(o, "value", str(o)))
templates.env.globals["confidence_label"] = lambda c: CONFIDENCE_STATE_LABELS_NL.get(c, getattr(c, "value", str(c)))
templates.env.globals["observation_type_label"] = lambda t: OBSERVATION_TYPE_LABELS_NL.get(t, getattr(t, "value", str(t)))
