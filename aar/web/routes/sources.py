from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from aar.config.settings import get_settings
from aar.models import CommanderReport, ParseStatus, SourceDocument, SourceDocumentType
from aar.services import media_service
from aar.services.dispatch_service import ingest_dispatch_excel
from aar.services.errors import DuplicateSourceError
from aar.services.report_service import ingest_commander_report, ingest_commander_report_sheet
from aar.web.deps import get_db, incident_or_404
from aar.web.flash import redirect_with_flash
from aar.web.templating import templates

router = APIRouter()


@router.get("/incidents/{incident_id}/sources")
def sources_page(incident_id: int, request: Request, session: Session = Depends(get_db)):
    incident = incident_or_404(session, incident_id)

    reports = session.query(CommanderReport).filter_by(incident_id=incident_id).all()
    report_docs = {
        d.id: d
        for d in session.query(SourceDocument)
        .filter_by(incident_id=incident_id, doc_type=SourceDocumentType.COMMANDER_REPORT)
        .all()
    }
    failed_report_docs = [
        d for d in report_docs.values() if d.id not in {r.source_document_id for r in reports}
    ]
    dispatch_docs = (
        session.query(SourceDocument)
        .filter_by(incident_id=incident_id, doc_type=SourceDocumentType.DISPATCH_EXCEL)
        .all()
    )
    from aar.models import DispatchRecord

    dispatch_info = []
    for d in dispatch_docs:
        n = session.query(DispatchRecord).filter_by(source_document_id=d.id).count()
        n_invalid = session.query(DispatchRecord).filter_by(source_document_id=d.id, is_valid=False).count()
        dispatch_info.append({"doc": d, "n_records": n, "n_invalid": n_invalid})

    photos = media_service.list_photos(session, incident)

    return templates.TemplateResponse(
        request,
        "sources.html",
        {
            "active_nav": "sources",
            "incident": incident,
            "reports": reports,
            "report_docs": report_docs,
            "failed_report_docs": failed_report_docs,
            "dispatch_info": dispatch_info,
            "photos": photos,
        },
    )


@router.post("/incidents/{incident_id}/sources/reports")
async def upload_reports(
    incident_id: int, files: list[UploadFile] = File(...), session: Session = Depends(get_db)
):
    incident = incident_or_404(session, incident_id)
    messages = []
    for f in files:
        content = await f.read()
        try:
            doc = ingest_commander_report(session, incident, content, f.filename)
            if doc.parse_status != ParseStatus.PARSED:
                messages.append(f"{f.filename}: {doc.parse_error}")
        except DuplicateSourceError as exc:
            messages.append(str(exc))

    flash = "; ".join(messages) if messages else "Verslagen toegevoegd."
    flash_type = "warning" if messages else "success"
    return redirect_with_flash(f"/incidents/{incident_id}/sources", flash, flash_type)


@router.post("/incidents/{incident_id}/sources/reports-sheet")
async def upload_reports_sheet(
    incident_id: int, file: UploadFile = File(...), session: Session = Depends(get_db)
):
    """Alternative to individual .docx uploads: a Google-Forms responses
    sheet (downloaded as .xlsx) carrying one row per commander."""
    incident = incident_or_404(session, incident_id)
    content = await file.read()
    try:
        docs = ingest_commander_report_sheet(session, incident, content, file.filename)
        errored = [d for d in docs if d.parse_status != ParseStatus.PARSED]
        if errored:
            flash, flash_type = f"{file.filename}: {errored[0].parse_error}", "warning"
        else:
            flash, flash_type = f"{len(docs)} verslag(en) toegevoegd uit {file.filename}.", "success"
    except DuplicateSourceError as exc:
        flash, flash_type = str(exc), "warning"

    return redirect_with_flash(f"/incidents/{incident_id}/sources", flash, flash_type)


@router.post("/incidents/{incident_id}/sources/dispatch")
async def upload_dispatch(
    incident_id: int, file: UploadFile = File(...), session: Session = Depends(get_db)
):
    incident = incident_or_404(session, incident_id)
    content = await file.read()
    try:
        doc = ingest_dispatch_excel(session, incident, content, file.filename)
        if doc.parse_status != ParseStatus.PARSED:
            flash, flash_type = f"{file.filename}: {doc.parse_error}", "warning"
        else:
            flash, flash_type = "Dispatchbestand toegevoegd.", "success"
    except DuplicateSourceError as exc:
        flash, flash_type = str(exc), "warning"

    return redirect_with_flash(f"/incidents/{incident_id}/sources", flash, flash_type)


@router.get("/commander-report-template.docx")
def download_template():
    settings = get_settings()
    path = settings.project_root / "templates" / "commander_report_template.docx"
    return FileResponse(
        path,
        filename="commandantenverslag_sjabloon.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
