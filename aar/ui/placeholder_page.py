"""Temporary placeholder for screens not yet built in the current phase.
Replaced incrementally as Phases 2/3/8 land — never left in the final build."""
from __future__ import annotations

import streamlit as st


def render(title: str, phase_note: str) -> None:
    st.title(title)
    st.warning(f"Dit scherm wordt gebouwd in een latere fase: {phase_note}")
    if st.button("← Terug naar archief"):
        st.session_state["route"] = "archive"
        st.rerun()
