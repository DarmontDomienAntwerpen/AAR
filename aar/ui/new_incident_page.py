"""Screen 2 — create a new AAR incident (spec §13, §68 Screen 2)."""
from __future__ import annotations

import datetime as dt

import streamlit as st
from pydantic import ValidationError
from sqlalchemy.orm import Session

from aar.models import IncidentType
from aar.schemas.forms import IncidentCreateForm
from aar.services.incident_service import create_incident


def render(session: Session) -> None:
    st.title("Nieuw incident aanmaken")

    if st.button("← Terug naar archief"):
        st.session_state["route"] = "archive"
        st.rerun()

    with st.form("new_incident_form"):
        date = st.date_input("Datum", value=dt.date.today())
        location = st.text_input("Locatie")
        incident_type = st.selectbox("Type incident", options=[t.value for t in IncidentType])
        description = st.text_area("Korte omschrijving", height=120)
        submitted = st.form_submit_button("Incident aanmaken", type="primary")

    if submitted:
        try:
            form = IncidentCreateForm(
                date=date,
                location=location,
                incident_type=IncidentType(incident_type),
                description=description,
            )
        except ValidationError as exc:
            st.error(f"Controleer de invoer: {exc.errors()[0]['msg']}")
            return

        incident = create_incident(session, form)
        st.session_state["route"] = "sources"
        st.session_state["incident_id"] = incident.id
        st.success("Incident aangemaakt.")
        st.rerun()
