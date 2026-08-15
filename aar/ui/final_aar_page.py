"""Screen 6 — the compiled definitieve AAR (spec §51, §68 Screen 6).

Read-oriented presentation of the currently validated content — no AI-vs-
human audit trail (spec §50), just what's true now. "Markeer als afgerond"
locks the incident's status; the underlying content stays editable via
Screen 5 even afterwards, since v1 has no complex permission model.
"""
from __future__ import annotations

import streamlit as st
from sqlalchemy.orm import Session

from aar.models import Incident, IncidentStatus
from aar.services import aar_service


def render(session: Session, incident: Incident) -> None:
    st.title(f"Definitieve AAR — {incident.location}")

    if st.button("← Terug naar interactieve AAR"):
        st.session_state["route"] = "aar"
        st.rerun()

    st.caption(f"{incident.date.strftime('%d-%m-%Y')} · {incident.incident_type.value} · Status: {incident.status.value}")

    st.header("Situatie")
    st.write(incident.situation_summary or aar_service.default_situation_summary(session, incident) or "—")

    events = aar_service.get_events(session, incident)
    timed = [e for e in events if e.exact_time is not None]
    if timed:
        st.header("Belangrijke tijdstippen")
        for e in sorted(timed, key=lambda e: e.exact_time):
            st.markdown(f"**{e.exact_time.strftime('%H:%M')}** — {e.title}")

    st.header("Incidentverloop")
    if not events:
        st.caption("Geen incidentmomenten beschikbaar.")
    for e in events:
        time_label = (
            e.exact_time.strftime("%H:%M")
            if e.exact_time is not None
            else (f"ca. {e.approx_time_text}" if e.approx_time_text else "geen exact tijdstip")
        )
        st.markdown(f"**{time_label} — {e.title}**")
        st.write(e.ai_summary)

    positive = aar_service.get_positive_findings(session, incident)
    st.header("Wat ging goed")
    if not positive:
        st.caption("Geen positieve punten geregistreerd.")
    for pf in positive:
        st.markdown(f"- **{pf.title}** — {pf.description}")

    discussion = aar_service.get_discussion_points(session, incident)
    st.header("Wat ging minder goed / te bespreken")
    if not discussion:
        st.caption("Geen bespreekpunten geregistreerd.")
    for dp in discussion:
        st.markdown(f"- **{dp.title}** — {dp.description}")

    lessons = aar_service.get_lessons(session, incident)
    st.header("Leerpunten")
    if not lessons:
        st.caption("Geen leerpunten geregistreerd.")
    for lesson in lessons:
        st.markdown(f"- **{lesson.title}** — {lesson.description}")

    improvements = aar_service.get_improvements(session, incident)
    st.header("Mogelijke verbeteringen")
    if not improvements:
        st.caption("Geen verbeteringen geregistreerd.")
    for imp in improvements:
        st.markdown(f"- **{imp.title}** — {imp.description}")

    st.divider()
    if incident.status == IncidentStatus.FINALIZED:
        st.success("Deze AAR is gemarkeerd als afgerond.")
    else:
        if st.button("Markeer als afgerond", type="primary"):
            aar_service.finalize_incident(session, incident)
            st.rerun()
