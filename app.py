"""Streamlit entrypoint / page router for the Fire Service AAR Tool."""
from __future__ import annotations

import streamlit as st

from aar.config.logging_setup import configure_logging, get_logger
from aar.db.session import get_engine, get_session, init_db
from aar.services.incident_service import get_incident
from aar.ui import archive_page, new_incident_page, placeholder_page, sources_page

configure_logging()
logger = get_logger("app")

st.set_page_config(page_title="AAR Tool — Brandweer", page_icon="🚒", layout="wide")


@st.cache_resource
def _bootstrap() -> None:
    engine = get_engine()
    init_db(engine)
    logger.info("Database geïnitialiseerd.")


_bootstrap()

if "route" not in st.session_state:
    st.session_state["route"] = "archive"

session = get_session()
try:
    route = st.session_state["route"]
    if route == "archive":
        archive_page.render(session)
    elif route == "new_incident":
        new_incident_page.render(session)
    elif route == "sources":
        incident = get_incident(session, st.session_state.get("incident_id"))
        if incident is None:
            st.session_state["route"] = "archive"
            st.rerun()
        else:
            sources_page.render(session, incident)
    elif route == "analysis":
        placeholder_page.render("Analyse", "Fase 4-7 — AI-pijplijn")
    elif route == "aar":
        placeholder_page.render("Interactieve AAR", "Fase 8 — interactieve werksessie")
    elif route == "final_aar":
        placeholder_page.render("Definitieve AAR", "Fase 8 — definitieve AAR")
    else:
        st.session_state["route"] = "archive"
        st.rerun()
finally:
    session.close()
