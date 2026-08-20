from pathlib import Path

import pandas as pd
import pytest

from aar.ingestion.commander_sheet import CommanderSheetParseError, parse_commander_report_sheet

_BASE_ROW = {
    "Timestamp": "2026-03-04 21:15:00",
    "Callsign": "P12",
    "Officiële eenheidsnaam": "1H PZ",
    "Graad": "Adjudant",
    "Achternaam": "Janssens",
    "Feiten bij aankomst": "Matige rook zichtbaar aan de voorzijde.",
    "Actie 1": "Interne aanval ingezet via voordeur.",
    "Doel 1": "Brand snel blussen.",
    "Resultaat 1": "Geslaagde actie",
    "Toelichting 1": "",
    "Actie 2": "",
    "Doel 2": "",
    "Resultaat 2": "",
    "Toelichting 2": "",
    "Actie 3": "",
    "Doel 3": "",
    "Resultaat 3": "",
    "Toelichting 3": "",
    "Wat ging goed": "Snelle interne aanval.",
    "Wat kon beter, en waarom": "",
    "Overige opmerkingen": "",
    "Problemen of moeilijkheden": "",
}


def _write_sheet(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "responses.xlsx"
    pd.DataFrame(rows).to_excel(path, index=False)
    return path


def test_parse_single_row_report(tmp_path):
    path = _write_sheet(tmp_path, [_BASE_ROW])
    result = parse_commander_report_sheet(path)

    assert len(result.reports) == 1
    report = result.reports[0]
    assert report.identity.callsign == "P12"
    assert report.identity.unit_name == "1H PZ"
    assert report.identity.surname == "Janssens"
    assert report.sections["situation"] == "Matige rook zichtbaar aan de voorzijde."
    assert report.sections["actions"] == (
        "Actie: Interne aanval ingezet via voordeur. | Doel: Brand snel blussen. | Resultaat: Geslaagde actie"
    )
    assert report.sections["went_well"] == "Snelle interne aanval."


def test_parse_multiple_rows_become_multiple_reports(tmp_path):
    row2 = dict(_BASE_ROW, Callsign="P21", Achternaam="Willems", **{"Actie 1": "Materiaal klaargezet.", "Resultaat 1": "geslaagde actie"})
    path = _write_sheet(tmp_path, [_BASE_ROW, row2])
    result = parse_commander_report_sheet(path)

    assert len(result.reports) == 2
    assert {r.identity.callsign for r in result.reports} == {"P12", "P21"}
    # Resultaat is free text, carried through verbatim — no canonicalisation.
    p21 = next(r for r in result.reports if r.identity.callsign == "P21")
    assert "Resultaat: geslaagde actie" in p21.sections["actions"]


def test_parse_multiple_action_slots_joined_in_order(tmp_path):
    row = dict(
        _BASE_ROW,
        **{
            "Actie 2": "Achterzijde laten controleren.",
            "Doel 2": "Zekerheid over veiligheid achterzijde.",
            "Resultaat 2": "Gedeeltelijk geslaagde actie",
            "Toelichting 2": "Controle gebeurde later dan bedoeld.",
        },
    )
    path = _write_sheet(tmp_path, [row])
    result = parse_commander_report_sheet(path)

    actions = result.reports[0].sections["actions"]
    lines = actions.split("\n")
    assert len(lines) == 2
    assert "Interne aanval" in lines[0]
    assert "Achterzijde laten controleren" in lines[1]
    assert "Toelichting: Controle gebeurde later dan bedoeld." in lines[1]


def test_parse_flags_missing_resultaat(tmp_path):
    row = dict(
        _BASE_ROW,
        **{
            "Actie 2": "Ventilatie gestart.",
            "Doel 2": "",
            "Resultaat 2": "",
            "Toelichting 2": "",
        },
    )
    path = _write_sheet(tmp_path, [row])
    result = parse_commander_report_sheet(path)

    assert any("geen resultaat" in w for w in result.warnings)


def test_parse_skips_blank_rows_without_callsign_or_surname(tmp_path):
    blank_row = {k: "" for k in _BASE_ROW}
    blank_row["Timestamp"] = "2026-03-04 21:30:00"
    path = _write_sheet(tmp_path, [_BASE_ROW, blank_row])
    result = parse_commander_report_sheet(path)

    assert len(result.reports) == 1


def test_parse_empty_sheet_returns_no_reports_with_warning(tmp_path):
    path = tmp_path / "empty.xlsx"
    pd.DataFrame().to_excel(path, index=False)
    result = parse_commander_report_sheet(path)

    assert result.reports == []
    assert result.warnings


def test_parse_unrecognisable_sheet_raises_clear_error(tmp_path):
    path = tmp_path / "unrelated.xlsx"
    pd.DataFrame([{"Foo": "bar", "Baz": "qux"}]).to_excel(path, index=False)

    with pytest.raises(CommanderSheetParseError):
        parse_commander_report_sheet(path)


def test_source_filename_identifies_row_and_commander(tmp_path):
    path = _write_sheet(tmp_path, [_BASE_ROW])
    result = parse_commander_report_sheet(path)

    assert "rij 2" in result.reports[0].source_filename
    assert "Janssens" in result.reports[0].source_filename
