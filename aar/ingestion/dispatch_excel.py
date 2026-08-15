"""Dispatch/control-room spreadsheet ingestion.

Deterministic only — no LLM. Real dispatch exports vary in column naming and
order, so headers are matched via a normalised synonym lookup rather than
fixed positions, and the parser degrades gracefully (skips blank rows,
flags unparsable timestamps per-row) instead of raising whenever possible.
It raises only when the sheet is genuinely unrecognisable as dispatch data.
"""
from __future__ import annotations

import datetime as dt
import unicodedata
from pathlib import Path

import pandas as pd

from aar.config.logging_setup import get_logger
from aar.schemas.ingestion import DispatchRecordRaw, DispatchSheetRaw

logger = get_logger("ingestion.dispatch_excel")


class DispatchExcelParseError(Exception):
    """Raised when the workbook cannot be recognised as dispatch data at all."""


TIMESTAMP_SYNONYMS = {
    "tijdstip", "tijd", "datumtijd", "datum tijd", "datum/tijd", "time",
    "timestamp", "uur", "datum en tijd", "registratietijd",
}
EVENT_SYNONYMS = {
    "gebeurtenis", "melding", "omschrijving", "event", "actie", "bericht",
    "status", "statuscode", "beschrijving", "toelichting",
}
UNIT_SYNONYMS = {
    "eenheid", "voertuig", "unit", "middel", "roepnummer", "callsign", "wagen",
}


def _normalize_header(text: str) -> str:
    text = str(text).strip().lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return text


def _json_safe(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.to_pydatetime().isoformat()
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)


def _detect_columns(columns: list[str]) -> dict[str, str]:
    """Return {'timestamp': original_col_name, 'event': ..., 'unit': ...} for
    whichever roles were recognised."""
    detected: dict[str, str] = {}
    for col in columns:
        normalized = _normalize_header(col)
        if "timestamp" not in detected and normalized in TIMESTAMP_SYNONYMS:
            detected["timestamp"] = col
        elif "event" not in detected and normalized in EVENT_SYNONYMS:
            detected["event"] = col
        elif "unit" not in detected and normalized in UNIT_SYNONYMS:
            detected["unit"] = col
    return detected


def _select_sheet(sheets: dict[str, pd.DataFrame]) -> tuple[str, pd.DataFrame, dict[str, str]]:
    best_name, best_df, best_cols, best_score = None, None, {}, -1
    for name, df in sheets.items():
        cols = _detect_columns(list(df.columns))
        score = len(cols)
        if score > best_score:
            best_name, best_df, best_cols, best_score = name, df, cols, score
    return best_name, best_df, best_cols


def parse_dispatch_excel(path: str | Path, source_filename: str | None = None) -> DispatchSheetRaw:
    path = Path(path)
    source_filename = source_filename or path.name

    try:
        sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl")
    except Exception as exc:
        raise DispatchExcelParseError(
            f"Het bestand '{source_filename}' kon niet worden gelezen als Excel-werkblad: {exc}"
        ) from exc

    if not sheets:
        raise DispatchExcelParseError(f"Het bestand '{source_filename}' bevat geen werkbladen.")

    sheet_name, df, columns = _select_sheet(sheets)

    if df is None or df.dropna(how="all").empty:
        return DispatchSheetRaw(
            records=[],
            source_filename=source_filename,
            sheet_name=sheet_name or "",
            warnings=["Het werkblad bevat geen gegevens."],
        )

    if "event" not in columns:
        raise DispatchExcelParseError(
            f"Kon geen kolom herkennen met gebeurtenis/omschrijving in werkblad "
            f"'{sheet_name}' van '{source_filename}'. Herkende kolommen: "
            f"{list(df.columns)}."
        )

    warnings: list[str] = []
    if "timestamp" not in columns:
        warnings.append(
            "Geen tijdstip-kolom herkend — gebeurtenissen worden zonder exact tijdstip verwerkt."
        )
    if "unit" not in columns:
        warnings.append("Geen eenheid-kolom herkend.")

    records: list[DispatchRecordRaw] = []
    for idx, row in df.iterrows():
        excel_row_number = idx + 2  # +1 for 0-index, +1 for header row
        raw_row = {str(col): _json_safe(row[col]) for col in df.columns}

        event_value = row.get(columns["event"]) if "event" in columns else None
        event_description = "" if pd.isna(event_value) else str(event_value).strip()

        unit_value = row.get(columns.get("unit")) if "unit" in columns else None
        unit = None if unit_value is None or pd.isna(unit_value) else str(unit_value).strip()

        if not event_description and not unit and all(pd.isna(v) for v in row.values):
            continue  # fully blank row — irrelevant, skip silently

        timestamp: dt.datetime | None = None
        is_valid = True
        validation_error: str | None = None
        if "timestamp" in columns:
            raw_ts = row.get(columns["timestamp"])
            if raw_ts is None or (isinstance(raw_ts, float) and pd.isna(raw_ts)):
                timestamp = None
            else:
                parsed = pd.to_datetime(raw_ts, errors="coerce", dayfirst=True)
                if pd.isna(parsed):
                    is_valid = False
                    validation_error = f"Ongeldig tijdstip: {raw_ts!r}"
                else:
                    timestamp = parsed.to_pydatetime()

        if not event_description:
            is_valid = False
            validation_error = (validation_error + "; " if validation_error else "") + (
                "Geen gebeurtenis/omschrijving ingevuld."
            )

        records.append(
            DispatchRecordRaw(
                row_index=excel_row_number,
                timestamp=timestamp,
                event_description=event_description,
                unit=unit,
                raw_row=raw_row,
                is_valid=is_valid,
                validation_error=validation_error,
            )
        )

    logger.info(
        "Parsed dispatch sheet '%s' from %s: %d record(s), %d warning(s).",
        sheet_name,
        source_filename,
        len(records),
        len(warnings),
    )
    return DispatchSheetRaw(
        records=records, source_filename=source_filename, sheet_name=sheet_name, warnings=warnings
    )
