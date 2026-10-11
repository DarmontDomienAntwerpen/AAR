"""Jinja2 environment: templates dir, Dutch-formatting filters, and the
enum→label dictionaries shared with the (removed) Streamlit UI so the
Dutch-only-in-the-UI rule (spec §57) stays centralised in one place."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from urllib.parse import quote

from fastapi.templating import Jinja2Templates

from aar.models.enums import DiscussionOrigin, IncidentStatus, IncidentType
from aar.schemas.constants import CATEGORY_LABELS_NL, CATEGORY_ORDER
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

# One colour per incident type, used consistently wherever the type is
# shown (sidebar, Overzicht, archive) so a facilitator recognises the kind
# of incident at a glance rather than reading the label every time.
INCIDENT_TYPE_BADGE_CLASSES = {
    IncidentType.BRAND: "bg-rose-50 text-rose-700",
    IncidentType.WATERONGEVAL: "bg-sky-50 text-sky-700",
    IncidentType.GEVAARLIJKE_STOFFEN: "bg-amber-50 text-amber-700",
    IncidentType.TECHNISCHE_HULPVERLENING: "bg-teal-50 text-teal-700",
}
INCIDENT_TYPE_DOT_CLASSES = {
    IncidentType.BRAND: "bg-rose-500",
    IncidentType.WATERONGEVAL: "bg-sky-500",
    IncidentType.GEVAARLIJKE_STOFFEN: "bg-amber-500",
    IncidentType.TECHNISCHE_HULPVERLENING: "bg-teal-500",
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

templates.env.globals["category_label"] = lambda c: CATEGORY_LABELS_NL.get(c, getattr(c, "value", str(c)))
templates.env.globals["category_order"] = lambda c: CATEGORY_ORDER.get(c, 99)

# "Waarnemingen & acties": groups matching the form's own literal sections
# (situation/actions/went_well/went_less_well/other/difficulties), each its
# own colour, rendered as one column so the chronological arc reads
# top-to-bottom.
SECTION_BOX_CLASSES = {
    "situation": "border-slate-300 bg-slate-100/80",
    "actions": "border-sky-300 bg-sky-100/70",
    "went_well": "border-emerald-300 bg-emerald-100/70",
    "went_less_well": "border-rose-300 bg-rose-100/70",
    "other": "border-slate-300 bg-slate-100/60",
    "difficulties": "border-amber-300 bg-amber-100/60",
}
templates.env.globals["section_box_class"] = lambda k: SECTION_BOX_CLASSES.get(k, "border-slate-300 bg-slate-100/70")

SECTION_DOT_CLASSES = {
    "situation": "bg-slate-400",
    "actions": "bg-sky-500",
    "went_well": "bg-emerald-500",
    "went_less_well": "bg-rose-500",
    "other": "bg-slate-400",
    "difficulties": "bg-amber-500",
}
templates.env.globals["section_dot_class"] = lambda k: SECTION_DOT_CLASSES.get(k, "bg-slate-400")

COMMANDER_SECTION_FIELDS = [
    ("observations", "Waarnemingen"),
    ("assessment", "Inschatting"),
    ("decision", "Beslissing"),
    ("result", "Resultaat"),
    ("went_well", "Wat ging goed"),
    ("went_less_well", "Wat ging minder goed"),
]
templates.env.globals["commander_section_fields"] = COMMANDER_SECTION_FIELDS

_PLACEHOLDER_RE = re.compile(r"^[\s\-–—.]*$")
templates.env.tests["placeholder_text"] = lambda text: bool(_PLACEHOLDER_RE.match(text or ""))
templates.env.filters["nl_date"] = _fmt_date
templates.env.filters["nl_time"] = _fmt_time
templates.env.filters["nl_datetime"] = _fmt_datetime
templates.env.globals["IncidentType"] = IncidentType


def _maps_url(location: str) -> str:
    """Google Maps search deep link for an address — plain browser
    navigation link (no API key/billing needed, unlike an embedded map).
    Deliberately the plain search action, not `map_action=pano`: pano's
    `viewpoint` is documented as accepting an address, but in practice
    free-text addresses don't reliably geocode to a panorama and the
    address never visibly appears anywhere on the resulting page. Search
    always shows the address in the search box and drops a pin on it —
    from there the user can click the Street View pegman themselves."""
    return f"https://www.google.com/maps/search/?api=1&query={quote(location or '')}"


def _incident_home_url(incident) -> str:
    """Where clicking an incident (e.g. from the archive) should land —
    depends on how far along it is, so a finalized report opens the report
    and not the raw upload screen it started from."""
    if incident.status == IncidentStatus.FINALIZED:
        return f"/incidents/{incident.id}/final"
    if incident.status in (IncidentStatus.ANALYZED, IncidentStatus.IN_REVIEW):
        return f"/incidents/{incident.id}/aar"
    return f"/incidents/{incident.id}/sources"


templates.env.globals["maps_url"] = _maps_url
templates.env.globals["incident_home_url"] = _incident_home_url
templates.env.globals["status_label"] = lambda s: STATUS_LABELS_NL.get(s, getattr(s, "value", str(s)))
templates.env.globals["status_badge_class"] = lambda s: STATUS_BADGE_CLASSES.get(s, "bg-ink-100 text-ink-600")
templates.env.globals["incident_type_badge_class"] = lambda t: INCIDENT_TYPE_BADGE_CLASSES.get(t, "bg-ink-100 text-ink-600")
templates.env.globals["incident_type_dot_class"] = lambda t: INCIDENT_TYPE_DOT_CLASSES.get(t, "bg-ink-400")
templates.env.globals["origin_label"] = lambda o: DISCUSSION_ORIGIN_LABELS_NL.get(o, getattr(o, "value", str(o)))
templates.env.globals["confidence_label"] = lambda c: CONFIDENCE_STATE_LABELS_NL.get(c, getattr(c, "value", str(c)))
templates.env.globals["observation_type_label"] = lambda t: OBSERVATION_TYPE_LABELS_NL.get(t, getattr(t, "value", str(t)))
