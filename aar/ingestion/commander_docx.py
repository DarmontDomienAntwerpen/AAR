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
from docx.shared import Pt

from aar.config.logging_setup import get_logger
from aar.models.enums import ObjectiveAchieved
from aar.schemas.constants import CALLSIGN_ALIASES, UNIT_NAME_ALIASES
from aar.schemas.ingestion import COMMANDER_REPORT_SECTION_KEYS, CommanderIdentity, CommanderReportRaw

logger = get_logger("ingestion.commander_docx")


def _normalize_alias_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def canonicalize_unit_name(raw: str) -> str:
    """Maps known spelling/casing/full-name variants of the same real unit
    to one canonical display form (see UNIT_NAME_ALIASES) — unrecognised
    values pass through unchanged, never dropped or guessed at."""
    raw = raw.strip()
    return UNIT_NAME_ALIASES.get(_normalize_alias_key(raw), raw)


def canonicalize_callsign(raw: str) -> str:
    """Same idea as canonicalize_unit_name, for callsigns (see
    CALLSIGN_ALIASES)."""
    raw = raw.strip()
    return CALLSIGN_ALIASES.get(_normalize_alias_key(raw), raw)


class CommanderReportParseError(Exception):
    """Raised when a document cannot be parsed as a commander report at all
    (corrupt file, or not recognisably our template)."""


SECTION_HEADINGS: dict[str, str] = {
    "situation": "B. Feiten, info en waarnemingen bij aankomst",
    "actions": "C. Acties",
    "went_well": "D. Wat ging goed",
    "went_less_well": "E. Wat kon beter, en waarom",
    "other": "F. Overige opmerkingen (vrij in te vullen)",
    "difficulties": "G. Problemen of moeilijkheden die ervaren werden",
}
assert set(SECTION_HEADINGS) == set(COMMANDER_REPORT_SECTION_KEYS)

IDENTITY_LABELS: dict[str, str] = {
    "callsign": "callsign",
    "officiële eenheidsnaam": "unit_name",
    "graad": "rank",
    "achternaam": "surname",
}
# Matched by prefix (see _extract_tables), not exact equality — so a label
# can carry a short example like "Officiële eenheidsnaam (bv. 1H PZ)"
# without also having to update this dict every time the wording changes.

# Kept only for backward compatibility: documents from an earlier template
# revision may still carry an "Is het doel bereikt?" table (spec history —
# now handled live during the AAR discussion instead of in the report). If
# present it's still parsed; if absent (the current template), that's the
# expected, unremarkable case — no warning either way.
OBJECTIVE_ANSWER_LABEL_PREFIX = "antwoord"
OBJECTIVE_EXPLANATION_LABEL_PREFIX = "toelichting bij doelbereik"

# The "C. Acties" section is a repeating set of labelled paragraphs — not a
# table — one block per action: what was done, why (doel), what came of it
# (resultaat, free text — not a constrained choice: forcing a pick from
# Geslaagd/Gedeeltelijk/Niet geslaagd on top of an already-descriptive result
# was redundant, the outcome is already legible from what's written) and,
# optionally, why it went the way it did. Plain paragraphs give unlimited,
# naturally reflowing writing room per field, a Word table cell doesn't.
ACTION_RESULT_LABEL = "Resultaat"
ACTION_FIELD_LABELS = (
    "Doel",
    ACTION_RESULT_LABEL,
    "Toelichting (optioneel, bv. als het niet volledig lukte: waarom)",
)
_ACTION_BLOCK_STARTER_COUNT = 3
_ACTION_START_RE = re.compile(r"^actie\s*\d*\s*$")


def _normalize_heading(text: str) -> str:
    return re.sub(r"^[A-Za-z]\.\s*", "", text).strip().lower()


_HEADING_LOOKUP: dict[str, str] = {
    _normalize_heading(heading): key for key, heading in SECTION_HEADINGS.items()
}


def generate_commander_report_template(path: str | Path) -> Path:
    """(Re)generate the standard commander report DOCX template."""
    path = Path(path)
    doc = Document()
    # Topic headings (A./B./C. ...) a touch smaller, "Actie N" labels a touch
    # bigger — the default Heading 1 size read as too dominant next to the
    # per-action labels, which needed more visual weight to stand out from
    # plain body text.
    doc.styles["Heading 1"].font.size = Pt(13)
    doc.styles["Heading 1"].paragraph_format.space_before = Pt(20)
    doc.styles["Heading 1"].paragraph_format.space_after = Pt(6)

    doc.add_heading("AAR — Persoonlijk verslag", level=0)
    doc.add_paragraph(
        "Kort, duidelijk en specifiek — geen volledig verhaal nodig. Wat u zelf "
        "zag, wist en besloot op dat moment, niet wat achteraf bleek. Details "
        "bespreken we samen tijdens de AAR."
    )

    doc.add_heading("A. Identificatie", level=1)
    identity_display_labels = ["Callsign", "Officiële eenheidsnaam (bv. 1H PZ)", "Graad", "Achternaam"]
    id_table = doc.add_table(rows=4, cols=2)
    id_table.style = "Light Grid Accent 1"
    for row, label in zip(id_table.rows, identity_display_labels):
        row.cells[0].text = label
        row.cells[1].text = ""

    for key, heading in SECTION_HEADINGS.items():
        doc.add_heading(heading, level=1)
        if key == "actions":
            doc.add_paragraph(
                "Eén blok per actie: wat deed u (Actie), met welk doel (Doel), en wat "
                "was het resultaat (Resultaat)? Voeg een Toelichting toe als het niet "
                "volledig lukte. Meer acties dan de onderstaande blokken? Kopieer een "
                "blok en plak het eronder."
            )
            for n in range(1, _ACTION_BLOCK_STARTER_COUNT + 1):
                actie_label = doc.add_paragraph()
                actie_label.paragraph_format.space_before = Pt(18)
                actie_label.paragraph_format.space_after = Pt(4)
                actie_run = actie_label.add_run(f"Actie {n}:")
                actie_run.bold = True
                actie_run.font.size = Pt(13)
                answer = doc.add_paragraph("")
                answer.paragraph_format.space_after = Pt(10)
                for field_label in ACTION_FIELD_LABELS:
                    label_paragraph = doc.add_paragraph()
                    label_paragraph.paragraph_format.left_indent = Pt(14)
                    label_paragraph.paragraph_format.space_before = Pt(6)
                    label_paragraph.paragraph_format.space_after = Pt(2)
                    label_paragraph.add_run(f"{field_label}:").bold = True
                    field_answer = doc.add_paragraph("")
                    field_answer.paragraph_format.left_indent = Pt(14)
                    field_answer.paragraph_format.space_after = Pt(8)
        else:
            doc.add_paragraph("")

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
            matched_identity_field = next(
                (field for prefix, field in IDENTITY_LABELS.items() if normalized.startswith(prefix)), None
            )
            if matched_identity_field is not None:
                identity_fields[matched_identity_field] = value
            elif normalized.startswith(OBJECTIVE_ANSWER_LABEL_PREFIX):
                objective_answer_text = value
            elif normalized.startswith(OBJECTIVE_EXPLANATION_LABEL_PREFIX):
                objective_explanation = value

    identity = CommanderIdentity(
        callsign=canonicalize_callsign(identity_fields.get("callsign", "")),
        unit_name=canonicalize_unit_name(identity_fields.get("unit_name", "")),
        rank=identity_fields.get("rank", ""),
        surname=identity_fields.get("surname", ""),
    )
    if not identity_fields:
        warnings.append("Identificatiegegevens (tabel) niet gevonden in het document.")
    elif not identity.is_complete:
        warnings.append("Niet alle identificatievelden (callsign, achternaam) zijn ingevuld.")

    # No warning for a missing answer here: the current template no longer
    # asks this in the report at all (spec: doelbereik wordt live besproken
    # tijdens de AAR) — only act on it if an older-template document happens
    # to carry the table.
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

    return identity, objective_achieved, objective_explanation, warnings


def _is_bold_label(paragraph) -> bool:
    runs_with_text = [r for r in paragraph.runs if r.text.strip()]
    return bool(runs_with_text) and all(r.bold for r in runs_with_text)


def _extract_action_blocks(doc: Document) -> tuple[str, list[str]]:
    """Walks the paragraphs under 'C. Acties' and groups each "Actie N" /
    Doel / Resultaat / Toelichting set of bold labels + the plain paragraphs
    that follow them into one labelled line of text per action ("Actie: ... |
    Doel: ... | Resultaat: ... | Toelichting: ..."), so downstream code
    (Stage 1 extraction, the mock provider) can keep treating every section
    as plain text — and so a real LLM can trivially re-parse each field by
    its label. Returns ("", []) if the section has no recognisable action
    blocks — e.g. a free-form document that doesn't follow the template."""
    warnings: list[str] = []
    blocks: list[dict[str, list[str]]] = []
    current_block: dict[str, list[str]] | None = None
    current_field: str | None = None
    in_actions_section = False

    field_short_keys = ("doel", "resultaat", "toelichting")
    short_key_by_label = {
        label.lower(): key for label, key in zip(ACTION_FIELD_LABELS, field_short_keys)
    }

    for paragraph in doc.paragraphs:
        style_name = (paragraph.style.name or "") if paragraph.style else ""
        text = paragraph.text.strip()

        if style_name.startswith("Heading"):
            normalized_heading = _normalize_heading(text)
            in_actions_section = _HEADING_LOOKUP.get(normalized_heading) == "actions"
            current_block, current_field = None, None
            continue
        if not in_actions_section:
            continue

        if _is_bold_label(paragraph):
            normalized_label = text.strip().lower().rstrip(":").strip()
            if _ACTION_START_RE.match(normalized_label):
                if current_block is not None:
                    blocks.append(current_block)
                current_block = {"actie": [], "doel": [], "resultaat": [], "toelichting": []}
                current_field = "actie"
                continue
            matched_key = short_key_by_label.get(normalized_label)
            if matched_key is not None and current_block is not None:
                current_field = matched_key
                continue

        if current_block is not None and current_field is not None and text:
            current_block[current_field].append(text)

    if current_block is not None:
        blocks.append(current_block)

    lines: list[str] = []
    for block in blocks:
        actie = "\n".join(block["actie"]).strip()
        doel = "\n".join(block["doel"]).strip()
        resultaat = "\n".join(block["resultaat"]).strip()
        toelichting = "\n".join(block["toelichting"]).strip()
        if not any((actie, doel, resultaat, toelichting)):
            continue  # an untouched starter block
        if not actie:
            warnings.append("Een actieblok heeft gegevens maar geen omschrijving van de actie.")
            continue

        if not resultaat:
            warnings.append(f"Actie '{actie}' heeft geen resultaat gekregen.")

        parts = [f"Actie: {actie}"]
        if doel:
            parts.append(f"Doel: {doel}")
        if resultaat:
            parts.append(f"Resultaat: {resultaat}")
        if toelichting:
            parts.append(f"Toelichting: {toelichting}")
        lines.append(" | ".join(parts))
    return "\n".join(lines), warnings


def _extract_sections(doc: Document) -> tuple[dict[str, str], list[str], bool]:
    sections: dict[str, str] = {key: "" for key in SECTION_HEADINGS}
    buffers: dict[str, list[str]] = {key: [] for key in SECTION_HEADINGS}
    current_key: str | None = None
    found_any_heading = False
    all_paragraphs: list[str] = []

    for paragraph in doc.paragraphs:
        style_name = (paragraph.style.name or "") if paragraph.style else ""
        text = paragraph.text.strip()
        if text:
            all_paragraphs.append(text)
        if style_name.startswith("Heading"):
            normalized = _normalize_heading(text)
            if normalized in _HEADING_LOOKUP:
                current_key = _HEADING_LOOKUP[normalized]
                found_any_heading = True
            else:
                current_key = None
            continue
        # "actions" content comes from its own labelled blocks (see
        # _extract_action_blocks), not this generic paragraph buffer — the
        # instructional paragraph and the bold field labels under that
        # heading must not be captured as if they were commander-written
        # narrative content.
        if current_key is not None and current_key != "actions" and text:
            buffers[current_key].append(text)

    for key, lines in buffers.items():
        sections[key] = "\n".join(lines).strip()

    warnings: list[str] = []
    if not found_any_heading:
        if not all_paragraphs:
            raise CommanderReportParseError(
                "Het document bevat geen leesbare tekst. Is dit het juiste bestand?"
            )
        # Real reports don't always follow the template (free-form prose
        # with the writer's own headers, e.g. "Acties uitgevoerd:" /
        # "Vaststellingen:"). Rejecting those outright would lose real
        # source material. Fall back to treating the whole document as one
        # narrative passage rather than failing the upload — the Stage 1
        # extraction LLM assigns each item's category from its content, not
        # from which section it arrived in, so it can still do useful work
        # here. (The deterministic mock provider's cruder section->category
        # mapping loses granularity in this fallback — an accepted
        # trade-off, same as its other documented mock-only limitations.)
        sections["narrative"] = "\n".join(all_paragraphs).strip()
        warnings.append(
            "Dit document volgt niet het standaard commandantenverslag-sjabloon "
            "(geen herkende sectiekoppen) — de volledige tekst is als één geheel "
            "meegenomen voor analyse in plaats van per sectie."
        )
        return sections, warnings, found_any_heading

    for key, heading in SECTION_HEADINGS.items():
        if key == "actions":
            continue  # emptiness reported separately, once the table is merged in
        if not sections[key]:
            warnings.append(f"Sectie '{heading}' is leeg.")

    return sections, warnings, found_any_heading


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
    sections, section_warnings, found_any_heading = _extract_sections(doc)

    if found_any_heading:
        actions_text, action_warnings = _extract_action_blocks(doc)
        sections["actions"] = actions_text
        if not actions_text:
            action_warnings.append(f"Sectie '{SECTION_HEADINGS['actions']}' is leeg.")
        section_warnings += action_warnings

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
