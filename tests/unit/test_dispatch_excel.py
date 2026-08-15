import datetime as dt

import pandas as pd
import pytest

from aar.ingestion.dispatch_excel import DispatchExcelParseError, parse_dispatch_excel


def _write_xlsx(tmp_path, df: pd.DataFrame, name="dispatch.xlsx", sheet_name="Blad1") -> str:
    path = tmp_path / name
    df.to_excel(path, index=False, sheet_name=sheet_name)
    return path


def test_parse_valid_workbook(tmp_path):
    df = pd.DataFrame(
        {
            "Tijdstip": ["2026-03-04 14:07:00", "2026-03-04 14:11:00"],
            "Gebeurtenis": ["Eerste voertuig ter plaatse", "Opschaling"],
            "Eenheid": ["P12", "P21"],
        }
    )
    path = _write_xlsx(tmp_path, df)
    result = parse_dispatch_excel(path)

    assert len(result.records) == 2
    assert result.records[0].event_description == "Eerste voertuig ter plaatse"
    assert result.records[0].unit == "P12"
    assert result.records[0].timestamp is not None
    assert result.records[0].timestamp.hour == 14
    assert result.records[0].is_valid


def test_parse_iso_timestamp_not_day_month_swapped(tmp_path):
    """Regression test: pandas.to_datetime(dayfirst=True) silently swaps day
    and month even for unambiguous ISO 'YYYY-MM-DD' strings — e.g. it turned
    '2026-03-04' (4 March) into 4 April. Caught during Phase 11 synthetic
    fixture testing; must never regress."""
    df = pd.DataFrame(
        {
            "Tijdstip": ["2026-03-04 14:07:00"],
            "Gebeurtenis": ["Eerste voertuig ter plaatse"],
            "Eenheid": ["P12"],
        }
    )
    path = _write_xlsx(tmp_path, df)
    result = parse_dispatch_excel(path)
    assert result.records[0].timestamp == dt.datetime(2026, 3, 4, 14, 7, 0)


def test_parse_ambiguous_european_date_still_uses_dayfirst(tmp_path):
    df = pd.DataFrame(
        {
            "Tijdstip": ["04/03/2026 14:07:00"],
            "Gebeurtenis": ["Eerste voertuig ter plaatse"],
            "Eenheid": ["P12"],
        }
    )
    path = _write_xlsx(tmp_path, df)
    result = parse_dispatch_excel(path)
    assert result.records[0].timestamp == dt.datetime(2026, 3, 4, 14, 7, 0)


def test_parse_reordered_columns(tmp_path):
    df = pd.DataFrame(
        {
            "Eenheid": ["P12"],
            "Gebeurtenis": ["Aankomst"],
            "Tijdstip": ["2026-03-04 14:07:00"],
        }
    )
    path = _write_xlsx(tmp_path, df)
    result = parse_dispatch_excel(path)
    assert len(result.records) == 1
    assert result.records[0].event_description == "Aankomst"


def test_parse_irrelevant_rows_skipped(tmp_path):
    df = pd.DataFrame(
        {
            "Tijdstip": ["2026-03-04 14:07:00", None, "2026-03-04 14:20:00"],
            "Gebeurtenis": ["Aankomst", None, "Bericht"],
            "Eenheid": ["P12", None, "P21"],
        }
    )
    path = _write_xlsx(tmp_path, df)
    result = parse_dispatch_excel(path)
    assert len(result.records) == 2


def test_parse_missing_timestamp_column(tmp_path):
    df = pd.DataFrame({"Gebeurtenis": ["Aankomst"], "Eenheid": ["P12"]})
    path = _write_xlsx(tmp_path, df)
    result = parse_dispatch_excel(path)
    assert len(result.records) == 1
    assert result.records[0].timestamp is None
    assert result.records[0].is_valid  # missing timestamp column is not an error
    assert any("tijdstip" in w.lower() for w in result.warnings)


def test_parse_invalid_timestamp_value_flags_row(tmp_path):
    df = pd.DataFrame(
        {
            "Tijdstip": ["niet-een-datum"],
            "Gebeurtenis": ["Rare rij"],
            "Eenheid": ["P12"],
        }
    )
    path = _write_xlsx(tmp_path, df)
    result = parse_dispatch_excel(path)
    assert len(result.records) == 1
    rec = result.records[0]
    assert rec.timestamp is None
    assert not rec.is_valid
    assert "ongeldig tijdstip" in rec.validation_error.lower()


def test_parse_empty_workbook_does_not_crash(tmp_path):
    df = pd.DataFrame({"Tijdstip": [], "Gebeurtenis": [], "Eenheid": []})
    path = _write_xlsx(tmp_path, df)
    result = parse_dispatch_excel(path)
    assert result.records == []
    assert result.warnings


def test_parse_unsupported_layout_raises_clear_error(tmp_path):
    df = pd.DataFrame({"Kolom A": [1, 2], "Kolom B": ["x", "y"]})
    path = _write_xlsx(tmp_path, df)
    with pytest.raises(DispatchExcelParseError):
        parse_dispatch_excel(path)
