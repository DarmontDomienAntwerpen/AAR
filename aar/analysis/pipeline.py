"""Orchestrates the full AI pipeline (Stages 1-6) for one incident and does
`AnalysisRun` bookkeeping. This is the single entry point the UI calls both
for the first analysis and for re-analysis after a facilitator correction
(spec §49 — full pipeline re-run is an accepted v1 simplification; Stage 1
extraction is skipped for reports that were already successfully extracted,
since raw report text hasn't changed)."""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from aar.analysis.extraction import run_extraction
from aar.analysis.findings import run_findings
from aar.analysis.lessons import run_lessons
from aar.analysis.narrative import run_narrative
from aar.analysis.reconstruction import run_reconstruction
from aar.analysis.timeline import enrich_with_dispatch_times
from aar.config.logging_setup import get_logger
from aar.llm.base import LLMProvider
from aar.models import (
    AnalysisRun,
    AnalysisRunStatus,
    CommanderReport,
    HumanCorrection,
    Incident,
    IncidentStatus,
)

logger = get_logger("analysis.pipeline")


def run_analysis(session: Session, incident: Incident, provider: LLMProvider) -> AnalysisRun:
    correction_ids = [
        c.id for c in session.query(HumanCorrection).filter_by(incident_id=incident.id).all()
    ]
    run = AnalysisRun(incident_id=incident.id, status=AnalysisRunStatus.RUNNING, correction_ids=correction_ids)
    session.add(run)
    session.commit()
    session.refresh(run)

    try:
        run.stage_reached = "extraction"
        session.commit()
        reports = session.query(CommanderReport).filter_by(incident_id=incident.id).all()
        if not reports:
            raise ValueError("Geen bevelvoerdersverslagen beschikbaar om te analyseren.")
        # Always re-extract: skipping already-parsed reports meant a re-analysis
        # kept extractions from an earlier run, possibly made by another
        # provider (e.g. the mock). run_extraction replaces only AI-created
        # observations; facilitator-added ones are kept.
        for report in reports:
            run_extraction(session, report, provider)

        run.stage_reached = "reconstruction"
        session.commit()
        run_reconstruction(session, incident, provider)

        run.stage_reached = "dispatch_enrichment"
        session.commit()
        enrich_with_dispatch_times(session, incident)

        run.stage_reached = "findings"
        session.commit()
        run_findings(session, incident, provider)

        run.stage_reached = "lessons"
        session.commit()
        run_lessons(session, incident, provider)

        run.stage_reached = "narrative"
        session.commit()
        run_narrative(session, incident, provider)

        run.stage_reached = "done"
        run.status = AnalysisRunStatus.SUCCESS
        run.finished_at = dt.datetime.now(dt.timezone.utc)
        incident.status = IncidentStatus.ANALYZED
        session.commit()
        logger.info("Analysis run %s for incident %s succeeded.", run.id, incident.id)
    except Exception as exc:  # noqa: BLE001 — recorded on the run, not swallowed
        run.status = AnalysisRunStatus.ERROR
        run.error_message = str(exc)
        run.finished_at = dt.datetime.now(dt.timezone.utc)
        session.commit()
        logger.error("Analysis run %s for incident %s failed at stage %s: %s", run.id, incident.id, run.stage_reached, exc)

    session.refresh(run)
    return run
