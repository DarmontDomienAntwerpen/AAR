"""Screen 4 — trigger the AI pipeline and show processing/error state
(spec §68 Screen 4)."""
from __future__ import annotations

import streamlit as st
from sqlalchemy.orm import Session

from aar.models import AnalysisRunStatus, CommanderReport, Incident
from aar.services.analysis_service import get_latest_analysis_run, trigger_analysis

_STAGE_LABELS_NL = {
    "extraction": "Verslagen worden geanalyseerd",
    "reconstruction": "Incidentverloop wordt gereconstrueerd",
    "dispatch_enrichment": "Dispatchtijden worden gekoppeld",
    "findings": "Bevindingen worden gezocht",
    "lessons": "Leerpunten worden voorgesteld",
    "done": "Analyse voltooid",
}


def render(session: Session, incident: Incident) -> None:
    st.title(f"Analyse — {incident.location}")
    if st.button("← Terug naar bronnen"):
        st.session_state["route"] = "sources"
        st.rerun()

    n_reports = session.query(CommanderReport).filter_by(incident_id=incident.id).count()
    if n_reports == 0:
        st.warning("Er zijn nog geen commandantenverslagen geüpload.")
        return

    run = get_latest_analysis_run(session, incident)

    if run is not None:
        if run.status == AnalysisRunStatus.SUCCESS:
            st.success(f"Laatste analyse voltooid op {run.finished_at.strftime('%d-%m-%Y %H:%M')}.")
            if st.button("Ga naar interactieve AAR", type="primary"):
                st.session_state["route"] = "aar"
                st.rerun()
        elif run.status == AnalysisRunStatus.ERROR:
            stage_label = _STAGE_LABELS_NL.get(run.stage_reached, run.stage_reached or "onbekend")
            st.error(f"Analyse mislukt tijdens stap '{stage_label}': {run.error_message}")

    if st.button("Analyse (opnieuw) uitvoeren", type="primary" if run is None else "secondary"):
        with st.spinner("Analyse wordt uitgevoerd — dit kan even duren..."):
            new_run = trigger_analysis(session, incident)
        if new_run.status == AnalysisRunStatus.SUCCESS:
            st.success("Analyse voltooid.")
        else:
            st.error(f"Analyse mislukt: {new_run.error_message}")
        st.rerun()
