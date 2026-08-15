"""Standard commander report: DOCX template generator + deterministic parser.

The template and the parser are two views of the same fixed contract
(`SECTION_HEADINGS`, `IDENTITY_LABELS`, `OBJECTIVE_LABELS`) — change them
together. Parsing is intentionally deterministic (no LLM involved): headings
and table labels are matched by normalised text, never inferred semantically.
That semantic work happens later, in the Stage 1 extraction LLM call, on top
of this already-structured, already-validated raw text.
"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.opc.exceptions import PackageNotFoundError

from aar.config.logging_setup import get_logger
from aar.models.enums import ObjectiveAchieved
from aar.schemas.ingestion import COMMANDER_REPORT_SECTION_KEYS, CommanderIdentity, CommanderReportRaw

logger = get_logger("ingestion.commander_docx")


class CommanderReportParseError(Exception):
    """Raised when a document cannot be parsed as a commander report at all
    (corrupt file, or not recognisably our template)."""


SECTION_HEADINGS: dict[str, str] = {
    "observations": "B. Eerste en relevante waarnemingen",
    "information_position": "C. Informatiepositie",
    "assessment": "D. Inschatting",
    "decision": "E. Beslissing",
    "objective": "F. Doel / intentie",
    "narrative": "G. Verloop / verhaal",
    "result": "H. Resultaat",
    "went_well": "J. Wat ging goed?",
    "went_less_well": "K. Wat ging minder goed?",
    "why": "L. Waarom?",
    "doubts_assumptions": "M. Twijfels / veronderstellingen / onzekerheden",
    "other": "N. Overige relevante waarnemingen",
}
assert set(SECTION_HEADINGS) == set(COMMANDER_REPORT_SECTION_KEYS)

IDENTITY_LABELS: dict[str, str] = {
    "roepnummer": "callsign",
    "officiële eenheidsnaam": "unit_name",
    "graad": "rank",
    "achternaam": "surname",
}

OBJECTIVE_ANSWER_LABEL_PREFIX = "antwoord"
OBJECTIVE_EXPLANATION_LABEL_PREFIX = "toelichting"


def _normalize_heading(text: str) -> str:
    return re.sub(r"^[A-Za-z]\.\s*", "", text).strip().lower()


_HEADING_LOOKUP: dict[str, str] = {
    _normalize_heading(heading): key for key, heading in SECTION_HEADINGS.items()
}


def generate_commander_report_template(path: str | Path) -> Path:
    """(Re)generate the standard commander report DOCX template."""
    path = Path(path)
    doc = Document()

    doc.add_heading("AAR — Commandantenverslag", level=0)
    doc.add_paragraph(
        "Vul dit verslag zo volledig mogelijk in. Beschrijf wat u zelf hebt "
        "waargenomen, geweten en besloten op het moment zelf — niet wat achteraf "
        "bleek. Gebruik voor de verhalende delen gerust uw eigen woorden."
    )

    doc.add_heading("A. Identificatie", level=1)
    identity_display_labels = ["Roepnummer", "Officiële eenheidsnaam", "Graad", "Achternaam"]
    id_table = doc.add_table(rows=4, cols=2)
    id_table.style = "Light Grid Accent 1"
    for row, label in zip(id_table.rows, identity_display_labels):
        row.cells[0].text = label
        row.cells[1].text = ""

    for key, heading in SECTION_HEADINGS.items():
        doc.add_heading(heading, level=1)
        doc.add_paragraph("")
        if key == "result":
            doc.add_heading("I. Is het doel bereikt?", level=1)
            obj_table = doc.add_table(rows=2, cols=2)
            obj_table.style = "Light Grid Accent 1"
            obj_table.rows[0].cells[0].text = (
                "Antwoord (Ja / Gedeeltelijk / Nee / Niet te beoordelen)"
            )
            obj_table.rows[0].cells[1].text = ""
            obj_table.rows[1].cells[0].text = "Toelichting bij doelbereik"
            obj_table.rows[1].cells[1].text = ""

    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    logger.info("Commander report template written to %s", path)
    return path


def _extract_tables(doc: Document) -> tuple[CommanderIdentity, ObjectiveAchieved | None, str, list[str]]:
    warnings: list[str] = []
    identity_fields: dict[str, str] = {}
    objective_answer_text = ""
    objective_explanation = ""

    for table in doc.tables:
        for row in table.rows:
            if len(row.cells) < 2:
                continue
            label = row.cells[0].text.strip()
            value = row.cells[1].text.strip()
            normalized = label.strip().lower()
            if normalized in IDENTITY_LABELS:
                identity_fields[IDENTITY_LABELS[normalized]] = value
            elif normalized.startswith(OBJECTIVE_ANSWER_LABEL_PREFIX):
                objective_answer_text = value
            elif normalized.startswith(OBJECTIVE_EXPLANATION_LABEL_PREFIX):
                objective_explanation = value

    identity = CommanderIdentity(
        callsign=identity_fields.get("callsign", ""),
        unit_name=identity_fields.get("unit_name", ""),
        rank=identity_fields.get("rank", ""),
        surname=identity_fields.get("surname", ""),
    )
    if not identity_fields:
        warnings.append("Identificatiegegevens (tabel) niet gevonden in het document.")
    elif not identity.is_complete:
        warnings.append("Niet alle identificatievelden (roepnummer, achternaam) zijn ingevuld.")

    objective_achieved: ObjectiveAchieved | None = None
    answer_norm = objective_answer_text.strip().lower()
    if answer_norm:
        for option in ObjectiveAchieved:
            if option.value.lower() == answer_norm:
                objective_achieved = option
                break
        if objective_achieved is None:
            warnings.append(
                f"Antwoord bij 'Is het doel bereikt?' ({objective_answer_text!r}) is geen "
                "herkende optie (Ja / Gedeeltelijk / Nee / Niet te beoordelen)."
            )
    else:
        warnings.append("Vraag 'Is het doel bereikt?' is niet beantwoord.")

    return identity, objective_achieved, objective_explanation, warnings


def _extract_sections(doc: Document) -> tuple[dict[str, str], list[str]]:
    sections: dict[str, str] = {key: "" for key in SECTION_HEADINGS}
    buffers: dict[str, list[str]] = {key: [] for key in SECTION_HEADINGS}
    current_key: str | None = None
    found_any_heading = False

    for paragraph in doc.paragraphs:
        style_name = (paragraph.style.name or "") if paragraph.style else ""
        text = paragraph.text.strip()
        if style_name.startswith("Heading"):
            normalized = _normalize_heading(text)
            if normalized in _HEADING_LOOKUP:
                current_key = _HEADING_LOOKUP[normalized]
                found_any_heading = True
            else:
                current_key = None
            continue
        if current_key is not None and text:
            buffers[current_key].append(text)

    for key, lines in buffers.items():
        sections[key] = "\n".join(lines).strip()

    warnings: list[str] = []
    if not found_any_heading:
        raise CommanderReportParseError(
            "Geen van de verwachte secties werd herkend. Is dit het correcte "
            "commandantenverslag-sjabloon?"
        )
    for key, heading in SECTION_HEADINGS.items():
        if not sections[key]:
            warnings.append(f"Sectie '{heading}' is leeg.")

    return sections, warnings


def parse_commander_report(
    path: str | Path, source_filename: str | None = None
) -> tuple[CommanderReportRaw, list[str]]:
    """Deterministically parse a commander DOCX report. Raises
    `CommanderReportParseError` for corrupt files or files that don't look
    like our template at all. Missing/incomplete optional content is
    reported via warnings on the returned model rather than raised."""
    path = Path(path)
    source_filename = source_filename or path.name

    try:
        doc = Document(str(path))
    except PackageNotFoundError as exc:
        raise CommanderReportParseError(
            f"Het bestand '{source_filename}' is geen geldig Word-document (.docx)."
        ) from exc
    except Exception as exc:  # defensive: python-docx can raise various zip/xml errors
        raise CommanderReportParseError(
            f"Het bestand '{source_filename}' kon niet worden geopend: {exc}"
        ) from exc

    identity, objective_achieved, objective_explanation, table_warnings = _extract_tables(doc)
    sections, section_warnings = _extract_sections(doc)

    raw = CommanderReportRaw(
        identity=identity,
        sections=sections,
        objective_achieved=objective_achieved,
        objective_achieved_explanation=objective_explanation,
        source_filename=source_filename,
    )
    all_warnings = table_warnings + section_warnings
    if all_warnings:
        logger.info("Parsed %s with %d warning(s).", source_filename, len(all_warnings))
    return raw, all_warnings
