"""Screen 3 — upload commander DOCX reports + dispatch Excel, review parse
status, and (once available) start the analysis pipeline (spec §68 Screen 3).
"""
from __future__ import annotations

import streamlit as st
from sqlalchemy.orm import Session

from aar.models import (
    CommanderReport,
    DispatchRecord,
    Incident,
    ParseStatus,
    SourceDocument,
    SourceDocumentType,
)
from aar.services.dispatch_service import ingest_dispatch_excel
from aar.services.errors import DuplicateSourceError
from aar.services.report_service import ingest_commander_report


def _render_commander_reports(session: Session, incident: Incident) -> None:
    st.subheader("Commandantenverslagen (.docx)")

    with st.form("upload_commander_reports", clear_on_submit=True):
        files = st.file_uploader(
            "Upload één of meerdere verslagen", type=["docx"], accept_multiple_files=True
        )
        submitted = st.form_submit_button("Verslagen toevoegen")

    if submitted and files:
        for f in files:
            try:
                doc = ingest_commander_report(session, incident, f.getvalue(), f.name)
                if doc.parse_status == ParseStatus.PARSED:
                    st.success(f"{f.name}: verwerkt.")
                else:
                    st.error(f"{f.name}: kon niet worden verwerkt — {doc.parse_error}")
            except DuplicateSourceError as exc:
                st.warning(str(exc))
        st.rerun()

    reports = (
        session.query(CommanderReport).filter_by(incident_id=incident.id).all()
    )
    docs = {
        d.id: d
        for d in session.query(SourceDocument)
        .filter_by(incident_id=incident.id, doc_type=SourceDocumentType.COMMANDER_REPORT)
        .all()
    }
    if not reports and not docs:
        st.caption("Nog geen verslagen geüpload.")
    for report in reports:
        doc = docs.get(report.source_document_id)
        with st.container(border=True):
            st.markdown(f"**{report.display_name}**")
            st.caption(f"Bestand: {doc.original_filename if doc else '?'}")
            if doc and doc.parse_error:
                st.caption(f"Opmerkingen: {doc.parse_error}")
    # Documents that failed to parse entirely (no CommanderReport row created)
    parsed_source_ids = {r.source_document_id for r in reports}
    for doc in docs.values():
        if doc.id not in parsed_source_ids:
            st.error(f"{doc.original_filename}: {doc.parse_error}")


def _render_dispatch(session: Session, incident: Incident) -> None:
    st.subheader("Dispatchgegevens (.xlsx)")

    with st.form("upload_dispatch", clear_on_submit=True):
        file = st.file_uploader("Upload dispatch-spreadsheet", type=["xlsx"])
        submitted = st.form_submit_button("Dispatchbestand toevoegen")

    if submitted and file:
        try:
            doc = ingest_dispatch_excel(session, incident, file.getvalue(), file.name)
            if doc.parse_status == ParseStatus.PARSED:
                st.success(f"{file.name}: verwerkt.")
            else:
                st.error(f"{file.name}: kon niet worden verwerkt — {doc.parse_error}")
        except DuplicateSourceError as exc:
            st.warning(str(exc))
        st.rerun()

    dispatch_docs = (
        session.query(SourceDocument)
        .filter_by(incident_id=incident.id, doc_type=SourceDocumentType.DISPATCH_EXCEL)
        .all()
    )
    if not dispatch_docs:
        st.caption("Nog geen dispatchbestand geüpload.")
    for doc in dispatch_docs:
        with st.container(border=True):
            st.markdown(f"**{doc.original_filename}**")
            n_records = session.query(DispatchRecord).filter_by(source_document_id=doc.id).count()
            n_invalid = (
                session.query(DispatchRecord)
                .filter_by(source_document_id=doc.id, is_valid=False)
                .count()
            )
            st.caption(f"{n_records} rijen herkend, waarvan {n_invalid} met een waarschuwing.")
            if doc.parse_error:
                st.caption(f"Opmerkingen: {doc.parse_error}")


def render(session: Session, incident: Incident) -> None:
    st.title(f"Bronnen — {incident.location}")
    st.caption(f"{incident.date.strftime('%d-%m-%Y')} · {incident.incident_type.value}")

    if st.button("← Terug naar archief"):
        st.session_state["route"] = "archive"
        st.rerun()

    col1, col2 = st.columns(2)
    with col1:
        _render_commander_reports(session, incident)
    with col2:
        _render_dispatch(session, incident)

    st.divider()
    n_reports = session.query(CommanderReport).filter_by(incident_id=incident.id).count()
    if n_reports == 0:
        st.info("Voeg minstens één commandantenverslag toe om de analyse te starten.")
    else:
        if st.button("Analyse starten", type="primary"):
            st.session_state["route"] = "analysis"
            st.rerun()
