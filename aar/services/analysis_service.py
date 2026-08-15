"""Thin wrapper the UI calls to trigger the AI pipeline with the configured
provider (spec §12 — the UI never talks to an LLM provider directly)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from aar.analysis.pipeline import run_analysis
from aar.llm.factory import get_llm_provider
from aar.models import AnalysisRun, Incident


def trigger_analysis(session: Session, incident: Incident) -> AnalysisRun:
    provider = get_llm_provider()
    return run_analysis(session, incident, provider)


def get_latest_analysis_run(session: Session, incident: Incident) -> AnalysisRun | None:
    return (
        session.query(AnalysisRun)
        .filter_by(incident_id=incident.id)
        .order_by(AnalysisRun.started_at.desc())
        .first()
    )
