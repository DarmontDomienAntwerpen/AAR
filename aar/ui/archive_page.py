"""Screen 1 — archive/overview of AARs, search, and entry point to create a
new incident (spec §68 Screen 1)."""
from __future__ import annotations

import streamlit as st
from sqlalchemy.orm import Session

from aar.models import IncidentStatus, IncidentType
from aar.services.incident_service import list_incidents

_STATUS_LABELS = {
    IncidentStatus.DRAFT: "Concept",
    IncidentStatus.SOURCES_UPLOADED: "Bronnen geüpload",
    IncidentStatus.ANALYZED: "Geanalyseerd",
    IncidentStatus.IN_REVIEW: "In beoordeling",
    IncidentStatus.FINALIZED: "Afgerond",
}


def render(session: Session) -> None:
    st.title("Archief — After Action Reviews")

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        search_text = st.text_input("Zoeken (locatie, omschrijving)", value="")
    with col2:
        type_filter = st.selectbox(
            "Type incident", options=["Alle"] + [t.value for t in IncidentType]
        )
    with col3:
        if st.button("+ Nieuw incident", type="primary", use_container_width=True):
            st.session_state["route"] = "new_incident"
            st.rerun()

    incident_type = None if type_filter == "Alle" else IncidentType(type_filter)
    incidents = list_incidents(session, search_text=search_text or None, incident_type=incident_type)

    if not incidents:
        st.info("Geen incidenten gevonden.")
        return

    for incident in incidents:
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 1, 1])
            c1.markdown(f"**{incident.location}** — {incident.incident_type.value}")
            c1.caption(incident.description or "Geen omschrijving.")
            c2.write(incident.date.strftime("%d-%m-%Y"))
            c3.write(_STATUS_LABELS.get(incident.status, incident.status.value))
            if st.button("Openen", key=f"open_{incident.id}"):
                st.session_state["route"] = "sources"
                st.session_state["incident_id"] = incident.id
                st.rerun()
