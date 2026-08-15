"""Streamlit entrypoint / page router for the Fire Service AAR Tool."""
from __future__ import annotations

import streamlit as st

from aar.config.logging_setup import configure_logging, get_logger
from aar.db.session import get_engine, get_session, init_db
from aar.services.incident_service import get_incident
from aar.ui import aar_page, analysis_page, archive_page, final_aar_page, new_incident_page, sources_page

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

_INCIDENT_ROUTES = {
    "sources": sources_page,
    "analysis": analysis_page,
    "aar": aar_page,
    "final_aar": final_aar_page,
}

session = get_session()
try:
    route = st.session_state["route"]
    if route == "archive":
        archive_page.render(session)
    elif route == "new_incident":
        new_incident_page.render(session)
    elif route in _INCIDENT_ROUTES:
        incident = get_incident(session, st.session_state.get("incident_id"))
        if incident is None:
            st.session_state["route"] = "archive"
            st.rerun()
        else:
            _INCIDENT_ROUTES[route].render(session, incident)
    else:
        st.session_state["route"] = "archive"
        st.rerun()
finally:
    session.close()
