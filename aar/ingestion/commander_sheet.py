"""Commander-report ingestion from a Google Forms responses sheet.

An alternative front end to the DOCX template (aar.ingestion.commander_docx):
colleagues fill in a Google Form instead of typing into Word, one form
submission per commander, all landing as rows in one linked Google Sheet.
The facilitator downloads that sheet as .xlsx and uploads it here — one file,
many commanders, instead of one .docx per commander.

Deliberately produces the exact same `CommanderReportRaw.sections` shape and
"Actie: ... | Doel: ... | Resultaat: ... | Toelichting: ..." line format as
the DOCX parser (see commander_docx._extract_action_blocks), so nothing
downstream (Stage 1 extraction, the mock provider) needs to know or care
which front end a given report came from.

Column matching is by normalised header prefix, not exact position — mirrors
dispatch_excel.py's synonym-based approach, adapted to columns instead of
rows. The exact question titles a facilitator should use when building the
Google Form are the same text as these prefixes (defined below)."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

from aar.config.logging_setup import get_logger
from aar.ingestion.commander_docx import canonicalize_callsign, canonicalize_unit_name
from aar.schemas.ingestion import CommanderIdentity, CommanderReportRaw, CommanderReportSheetRaw

logger = get_logger("ingestion.commander_sheet")


class CommanderSheetParseError(Exception):
    """Raised when the workbook cannot be recognised as commander-report
    responses at all (no identity/action columns found)."""


IDENTITY_COLUMN_PREFIXES: dict[str, str] = {
    "callsign": "callsign",
    "officiele eenheidsnaam": "unit_name",  # accent stripped by _normalize_header
    "eenheid": "unit_name",  # a facilitator may title the question just "Eenheid"
    "graad": "rank",
    "achternaam": "surname",
}

SECTION_COLUMN_PREFIXES: dict[str, str] = {
    "feiten": "situation",
    "wat ging goed": "went_well",
    "wat kon beter": "went_less_well",
    "overige opmerkingen": "other",
    "extra opmerkingen": "other",  # the real Kerkstraat form titled this question "Extra opmerkingen"
    "problemen": "difficulties",
}

# Matches "Actie 1", but also whatever more natural phrasing a facilitator
# actually types — "Doel van actie 1", "Resultaat actie 1", even a long
# explanatory title like "Toelichting indien actie 1 niet of gedeeltelijk
# geslaagd" (the real Kerkstraat form's actual wording — the slot number
# sits in the MIDDLE of the title here, not at the end). The only two things
# that must hold: the title starts with one of the four field words, and the
# slot number is the first number that appears anywhere after that —
# everything else is free text, not something to rely on matching.
_ACTION_COLUMN_RE = re.compile(r"^(actie|doel|resultaat|toelichting)\b.*?(\d+)")


def _normalize_header(text: str) -> str:
    text = str(text).strip().lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return text


def _cell(row: pd.Series, col: str) -> str:
    value = row.get(col)
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, float) and value.is_integer():
        # A callsign like "110" typed into a Google Form numeric-looking
        # question comes back from pandas as 110.0 — show it the way a
        # human typed it, not with a spurious ".0".
        return str(int(value))
    return str(value).strip()


def _classify_columns(columns: list[str]) -> tuple[dict[str, str], dict[str, str], dict[int, dict[str, str]]]:
    """Returns (identity_cols, section_cols, action_cols) mapping our field
    keys to the original column names — action_cols keyed by slot number."""
    identity_cols: dict[str, str] = {}
    section_cols: dict[str, str] = {}
    action_cols: dict[int, dict[str, str]] = {}

    for col in columns:
        normalized = _normalize_header(col)

        identity_key = next(
            (field for prefix, field in IDENTITY_COLUMN_PREFIXES.items() if normalized.startswith(prefix)), None
        )
        if identity_key and identity_key not in identity_cols:
            identity_cols[identity_key] = col
            continue

        section_key = next(
            (field for prefix, field in SECTION_COLUMN_PREFIXES.items() if normalized.startswith(prefix)), None
        )
        if section_key and section_key not in section_cols:
            section_cols[section_key] = col
            continue

        match = _ACTION_COLUMN_RE.match(normalized)
        if match:
            field, slot = match.group(1), int(match.group(2))
            action_cols.setdefault(slot, {})[field] = col

    return identity_cols, section_cols, action_cols


def _build_actions_text(row: pd.Series, action_cols: dict[int, dict[str, str]]) -> tuple[str, list[str]]:
    warnings: list[str] = []
    lines: list[str] = []
    for slot in sorted(action_cols):
        cols = action_cols[slot]
        actie = _cell(row, cols["actie"]) if "actie" in cols else ""
        doel = _cell(row, cols["doel"]) if "doel" in cols else ""
        resultaat = _cell(row, cols["resultaat"]) if "resultaat" in cols else ""
        toelichting = _cell(row, cols["toelichting"]) if "toelichting" in cols else ""
        if not any((actie, doel, resultaat, toelichting)):
            continue  # this respondent didn't fill in this action slot

        if not resultaat:
            warnings.append(f"Actie {slot} ('{actie}') heeft geen resultaat gekregen.")

        parts = [f"Actie: {actie}"]
        if doel:
            parts.append(f"Doel: {doel}")
        if resultaat:
            parts.append(f"Resultaat: {resultaat}")
        if toelichting:
            parts.append(f"Toelichting: {toelichting}")
        lines.append(" | ".join(parts))

    return "\n".join(lines), warnings


def parse_commander_report_sheet(
    path: str | Path, source_filename: str | None = None
) -> CommanderReportSheetRaw:
    path = Path(path)
    source_filename = source_filename or path.name

    try:
        sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl")
    except Exception as exc:
        raise CommanderSheetParseError(
            f"Het bestand '{source_filename}' kon niet worden gelezen als Excel-werkblad: {exc}"
        ) from exc
    if not sheets:
        raise CommanderSheetParseError(f"Het bestand '{source_filename}' bevat geen werkbladen.")

    sheet_name, df = None, None
    identity_cols, section_cols, action_cols = {}, {}, {}
    best_score = -1
    for name, candidate in sheets.items():
        i_cols, s_cols, a_cols = _classify_columns(list(candidate.columns))
        score = len(i_cols) + len(s_cols) + len(a_cols)
        if score > best_score:
            sheet_name, df = name, candidate
            identity_cols, section_cols, action_cols = i_cols, s_cols, a_cols
            best_score = score

    if df is None or df.dropna(how="all").empty:
        return CommanderReportSheetRaw(
            reports=[], source_filename=source_filename, sheet_name=sheet_name or "",
            warnings=["Het werkblad bevat geen gegevens."],
        )
    if not identity_cols and not action_cols:
        raise CommanderSheetParseError(
            f"Kon geen identificatie- of actiekolommen herkennen in werkblad '{sheet_name}' van "
            f"'{source_filename}'. Herkende kolommen: {list(df.columns)}."
        )

    reports: list[CommanderReportRaw] = []
    sheet_warnings: list[str] = []
    for idx, row in df.iterrows():
        excel_row_number = idx + 2  # +1 for 0-index, +1 for header row
        if row.isna().all():
            continue

        identity = CommanderIdentity(
            callsign=canonicalize_callsign(_cell(row, identity_cols["callsign"]) if "callsign" in identity_cols else ""),
            unit_name=canonicalize_unit_name(_cell(row, identity_cols["unit_name"]) if "unit_name" in identity_cols else ""),
            rank=_cell(row, identity_cols["rank"]) if "rank" in identity_cols else "",
            surname=_cell(row, identity_cols["surname"]) if "surname" in identity_cols else "",
        )
        if not identity.callsign and not identity.surname:
            continue  # a respondent-less blank row (e.g. a stray trailing row)

        sections: dict[str, str] = {key: "" for key in SECTION_COLUMN_PREFIXES.values()}
        for key, col in section_cols.items():
            sections[key] = _cell(row, col)
        actions_text, action_warnings = _build_actions_text(row, action_cols)
        sections["actions"] = actions_text

        row_warnings = list(action_warnings)
        if not identity.is_complete:
            row_warnings.append("niet alle identificatievelden zijn ingevuld.")
        if not actions_text:
            row_warnings.append("geen acties ingevuld.")
        for key in section_cols:
            # Only flag a section as "leeg" when the form actually has a
            # question for it and the respondent left it blank — not for
            # sections the form never asked in the first place (no matching
            # column found at all), which would otherwise warn on every
            # single row forever.
            if not sections[key]:
                row_warnings.append(f"'{key}' is leeg.")

        reports.append(
            CommanderReportRaw(
                identity=identity,
                sections=sections,
                objective_achieved=None,
                objective_achieved_explanation="",
                source_filename=f"{source_filename} (rij {excel_row_number} — {identity.display_name or 'onbekend'})",
            )
        )
        sheet_warnings.extend(f"Rij {excel_row_number}: {w}" for w in row_warnings)

    if not reports:
        sheet_warnings.append("Geen enkele rij met een ingevulde callsign of achternaam gevonden.")

    logger.info(
        "Parsed commander-report sheet '%s' from %s: %d report(s), %d warning(s).",
        sheet_name, source_filename, len(reports), len(sheet_warnings),
    )
    return CommanderReportSheetRaw(
        reports=reports, source_filename=source_filename, sheet_name=sheet_name or "", warnings=sheet_warnings
    )
