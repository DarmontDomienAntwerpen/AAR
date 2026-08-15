"""Screen 5 — the interactive AAR workspace the facilitator runs the actual
group session from (spec §45-49, §68 Screen 5)."""
from __future__ import annotations

import streamlit as st
from sqlalchemy.orm import Session

from aar.models import Incident, IncidentStatus
from aar.services import aar_service
from aar.services.analysis_service import trigger_analysis
from aar.ui.labels import CONFIDENCE_STATE_LABELS_NL, DISCUSSION_ORIGIN_LABELS_NL


def _evidence_expander(session: Session, observation_ids: list[int]) -> None:
    if not observation_ids:
        return
    observations = aar_service.get_observations_by_ids(session, observation_ids)
    if not observations:
        return
    with st.expander(f"Bewijs bekijken ({len(observations)})"):
        for obs in observations:
            who = obs.attributed_to or "AI-analyse"
            st.markdown(f"**{who}**")
            if obs.source_passage:
                st.caption(f"„{obs.source_passage}”")


def _correction_form(session: Session, incident: Incident, target_type: str, target_id: int, key_suffix: str) -> None:
    with st.expander("Correctie toevoegen"):
        with st.form(f"correction_{key_suffix}", clear_on_submit=True):
            text = st.text_area(
                "Geef aan wat aangepast moet worden aan de interpretatie. Dit wordt "
                "meegenomen bij een volgende analyse.",
                key=f"correction_text_{key_suffix}",
            )
            submitted = st.form_submit_button("Correctie opslaan")
        if submitted and text.strip():
            aar_service.add_correction(session, incident, target_type, target_id, text)
            st.success("Correctie opgeslagen. Voer een nieuwe analyse uit om ze te verwerken.")
            st.rerun()


def _render_overview_tab(session: Session, incident: Incident) -> None:
    st.subheader("Incidentgegevens")
    c1, c2 = st.columns(2)
    c1.markdown(f"**Datum:** {incident.date.strftime('%d-%m-%Y')}")
    c1.markdown(f"**Locatie:** {incident.location}")
    c2.markdown(f"**Type:** {incident.incident_type.value}")
    c2.markdown(f"**Status:** {incident.status.value}")
    if incident.description:
        st.caption(incident.description)

    st.subheader("Situatiesamenvatting")
    default_text = incident.situation_summary or aar_service.default_situation_summary(session, incident)
    with st.form("situation_summary_form"):
        text = st.text_area("Samenvatting (bewerkbaar)", value=default_text, height=150)
        if st.form_submit_button("Samenvatting opslaan"):
            aar_service.update_situation_summary(session, incident, text)
            st.success("Opgeslagen.")
            st.rerun()

    events = aar_service.get_events(session, incident)
    timed = [e for e in events if e.exact_time is not None]
    if timed:
        st.subheader("Belangrijke tijdstippen")
        for e in sorted(timed, key=lambda e: e.exact_time):
            st.markdown(f"**{e.exact_time.strftime('%H:%M')}** — {e.title}")

    st.subheader("Heranalyse")
    st.caption(
        "Voer dit uit nadat u correcties heeft toegevoegd, zodat de AI-analyse "
        "hiermee rekening houdt."
    )
    if st.button("Analyse opnieuw uitvoeren"):
        with st.spinner("Analyse wordt uitgevoerd..."):
            trigger_analysis(session, incident)
        st.rerun()


def _render_timeline_tab(session: Session, incident: Incident) -> None:
    events = aar_service.get_events(session, incident)
    if not events:
        st.info("Nog geen incidentmomenten beschikbaar.")

    for event in events:
        if event.exact_time is not None:
            time_label = event.exact_time.strftime("%H:%M")
        elif event.approx_time_text:
            time_label = f"ca. {event.approx_time_text}"
        else:
            time_label = "Geen exact tijdstip beschikbaar"

        with st.container(border=True):
            st.markdown(f"**{event.title}** · {time_label}")
            if event.involved_commanders:
                st.caption("Betrokken: " + ", ".join(event.involved_commanders))

            with st.form(f"event_summary_{event.id}"):
                summary = st.text_area("AI-samenvatting (bewerkbaar)", value=event.ai_summary, key=f"summary_{event.id}")
                if st.form_submit_button("Opslaan"):
                    aar_service.update_event_summary(session, event, summary)
                    st.rerun()

            perspectives = event.perspectives
            if perspectives:
                with st.expander(f"Perspectieven ({len(perspectives)})"):
                    for p in perspectives:
                        st.markdown(f"**{p.commander_display_name}**")
                        st.write(p.perspective_text)

            _evidence_expander(session, event.observation_ids)
            _correction_form(session, incident, "event", event.id, f"event_{event.id}")

            if st.button("Moment verwijderen", key=f"delete_event_{event.id}"):
                aar_service.delete_event(session, event)
                st.rerun()

    with st.expander("+ Moment handmatig toevoegen"):
        with st.form("add_event_form", clear_on_submit=True):
            title = st.text_input("Titel")
            if st.form_submit_button("Toevoegen") and title.strip():
                aar_service.add_manual_event(session, incident, title)
                st.rerun()


def _render_discussion_tab(session: Session, incident: Incident) -> None:
    points = aar_service.get_discussion_points(session, incident)
    if not points:
        st.info("Nog geen bespreekpunten.")
    for dp in points:
        with st.container(border=True):
            origin_label = DISCUSSION_ORIGIN_LABELS_NL.get(dp.origin_category, dp.origin_category.value)
            confidence_label = CONFIDENCE_STATE_LABELS_NL.get(dp.confidence_state, dp.confidence_state.value)
            st.markdown(f"**{dp.title}**")
            st.caption(f"{origin_label} · {confidence_label}")
            with st.form(f"dp_edit_{dp.id}"):
                title = st.text_input("Titel", value=dp.title, key=f"dp_title_{dp.id}")
                description = st.text_area("Beschrijving", value=dp.description, key=f"dp_desc_{dp.id}")
                col1, col2 = st.columns(2)
                save = col1.form_submit_button("Opslaan")
                delete = col2.form_submit_button("Verwijderen")
            if save:
                aar_service.update_discussion_point(session, dp, title, description)
                st.rerun()
            if delete:
                aar_service.delete_discussion_point(session, dp)
                st.rerun()
            _evidence_expander(session, dp.observation_ids)

    with st.expander("+ Bespreekpunt handmatig toevoegen"):
        with st.form("add_dp_form", clear_on_submit=True):
            title = st.text_input("Titel", key="new_dp_title")
            description = st.text_area("Beschrijving", key="new_dp_desc")
            if st.form_submit_button("Toevoegen") and title.strip():
                aar_service.add_manual_discussion_point(session, incident, title, description)
                st.rerun()


def _render_positive_tab(session: Session, incident: Incident) -> None:
    findings = aar_service.get_positive_findings(session, incident)
    if not findings:
        st.info("Nog geen positieve punten.")
    for pf in findings:
        with st.container(border=True):
            st.markdown(f"**{pf.title}**")
            with st.form(f"pf_edit_{pf.id}"):
                title = st.text_input("Titel", value=pf.title, key=f"pf_title_{pf.id}")
                description = st.text_area("Beschrijving", value=pf.description, key=f"pf_desc_{pf.id}")
                col1, col2 = st.columns(2)
                save = col1.form_submit_button("Opslaan")
                delete = col2.form_submit_button("Verwijderen")
            if save:
                aar_service.update_positive_finding(session, pf, title, description)
                st.rerun()
            if delete:
                aar_service.delete_positive_finding(session, pf)
                st.rerun()
            _evidence_expander(session, pf.observation_ids)

    with st.expander("+ Positief punt handmatig toevoegen"):
        with st.form("add_pf_form", clear_on_submit=True):
            title = st.text_input("Titel", key="new_pf_title")
            description = st.text_area("Beschrijving", key="new_pf_desc")
            if st.form_submit_button("Toevoegen") and title.strip():
                aar_service.add_manual_positive_finding(session, incident, title, description)
                st.rerun()


def _render_lessons_tab(session: Session, incident: Incident) -> None:
    lessons = aar_service.get_lessons(session, incident)
    improvements = aar_service.get_improvements(session, incident)
    improvements_by_lesson: dict[int | None, list] = {}
    for imp in improvements:
        improvements_by_lesson.setdefault(imp.related_lesson_id, []).append(imp)

    if not lessons:
        st.info("Nog geen leerpunten.")
    for lesson in lessons:
        with st.container(border=True):
            st.markdown(f"**{lesson.title}**")
            with st.form(f"lesson_edit_{lesson.id}"):
                title = st.text_input("Titel", value=lesson.title, key=f"lesson_title_{lesson.id}")
                description = st.text_area("Beschrijving", value=lesson.description, key=f"lesson_desc_{lesson.id}")
                col1, col2 = st.columns(2)
                save = col1.form_submit_button("Opslaan")
                delete = col2.form_submit_button("Verwijderen")
            if save:
                aar_service.update_lesson(session, lesson, title, description)
                st.rerun()
            if delete:
                aar_service.delete_lesson(session, lesson)
                st.rerun()

            for imp in improvements_by_lesson.get(lesson.id, []):
                st.markdown(f"↳ *Mogelijke verbetering:* {imp.title}")
                st.caption(imp.description)

    unlinked = improvements_by_lesson.get(None, [])
    if unlinked:
        st.subheader("Overige mogelijke verbeteringen")
        for imp in unlinked:
            st.markdown(f"**{imp.title}**")
            st.caption(imp.description)

    with st.expander("+ Leerpunt handmatig toevoegen"):
        with st.form("add_lesson_form", clear_on_submit=True):
            title = st.text_input("Titel", key="new_lesson_title")
            description = st.text_area("Beschrijving", key="new_lesson_desc")
            if st.form_submit_button("Toevoegen") and title.strip():
                aar_service.add_manual_lesson(session, incident, title, description)
                st.rerun()

    with st.expander("+ Verbetering handmatig toevoegen"):
        with st.form("add_improvement_form", clear_on_submit=True):
            title = st.text_input("Titel", key="new_imp_title")
            description = st.text_area("Beschrijving", key="new_imp_desc")
            if st.form_submit_button("Toevoegen") and title.strip():
                aar_service.add_manual_improvement(session, incident, title, description)
                st.rerun()


def render(session: Session, incident: Incident) -> None:
    st.title(f"Interactieve AAR — {incident.location}")
    st.caption(f"{incident.date.strftime('%d-%m-%Y')} · {incident.incident_type.value}")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("← Terug naar archief"):
            st.session_state["route"] = "archive"
            st.rerun()
    with col2:
        if st.button("Definitieve AAR →", type="primary"):
            st.session_state["route"] = "final_aar"
            st.rerun()

    if incident.status == IncidentStatus.ANALYZED:
        incident.status = IncidentStatus.IN_REVIEW
        session.commit()

    tabs = st.tabs(["Overzicht", "Incidentverloop", "Te bespreken", "Positieve punten", "Leerpunten"])
    with tabs[0]:
        _render_overview_tab(session, incident)
    with tabs[1]:
        _render_timeline_tab(session, incident)
    with tabs[2]:
        _render_discussion_tab(session, incident)
    with tabs[3]:
        _render_positive_tab(session, incident)
    with tabs[4]:
        _render_lessons_tab(session, incident)
