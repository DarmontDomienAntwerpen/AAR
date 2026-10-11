from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from aar.models import AnalysisRunStatus, CommanderReport
from aar.services.analysis_service import get_latest_analysis_run, trigger_analysis
from aar.web.deps import get_db, incident_or_404, writable_incident_or_404
from aar.web.flash import redirect_with_flash
from aar.web.templating import templates

router = APIRouter()

STAGE_LABELS_NL = {
    "extraction": "Verslagen worden geanalyseerd",
    "reconstruction": "Incidentverloop wordt gereconstrueerd",
    "dispatch_enrichment": "Dispatchtijden worden gekoppeld",
    "findings": "Bevindingen worden gezocht",
    "lessons": "Leerpunten worden voorgesteld",
    "done": "Analyse voltooid",
}


@router.get("/incidents/{incident_id}/analysis")
def analysis_page(incident_id: int, request: Request, session: Session = Depends(get_db)):
    incident = incident_or_404(session, incident_id)
    n_reports = session.query(CommanderReport).filter_by(incident_id=incident_id).count()
    run = get_latest_analysis_run(session, incident)

    return templates.TemplateResponse(
        request,
        "analysis.html",
        {
            "active_nav": "analysis",
            "incident": incident,
            "n_reports": n_reports,
            "run": run,
            "stage_labels": STAGE_LABELS_NL,
        },
    )


@router.post("/incidents/{incident_id}/analysis/run")
def run_analysis_now(incident_id: int, session: Session = Depends(get_db)):
    incident = writable_incident_or_404(session, incident_id)
    run = trigger_analysis(session, incident)
    if run.status == AnalysisRunStatus.SUCCESS:
        return redirect_with_flash(f"/incidents/{incident_id}/analysis", "Analyse voltooid.")
    return redirect_with_flash(
        f"/incidents/{incident_id}/analysis", f"Analyse mislukt: {run.error_message}", "error"
    )
