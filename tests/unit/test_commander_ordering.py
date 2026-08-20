"""Command-structure-aware ordering of commander reports on the "Middelen &
bevelvoerders" overview (user-specified convention: LVO/command vehicle 100
leads 110/120/130..., a second LVO 200 leads 210/220..., standalone units
like an aerial ladder "AL1"/"AL2" have no place in the hierarchy)."""
from types import SimpleNamespace

from aar.web.routes.interactive_aar import _callsign_sort_key, _group_by_command_structure


def _reports(callsigns):
    return [SimpleNamespace(callsign=c) for c in callsigns]


def test_numeric_callsigns_sort_by_hundred_then_value():
    reports = _reports(["210", "110", "100", "130", "200", "120"])
    reports.sort(key=lambda r: _callsign_sort_key(r.callsign))
    assert [r.callsign for r in reports] == ["100", "110", "120", "130", "200", "210"]


def test_non_numeric_callsigns_sort_after_numeric_ones():
    reports = _reports(["AL2", "110", "AL1", "100"])
    reports.sort(key=lambda r: _callsign_sort_key(r.callsign))
    assert [r.callsign for r in reports] == ["100", "110", "AL1", "AL2"]


def test_group_by_command_structure_groups_by_leading_hundred():
    reports = _reports(["100", "110", "120", "130", "200", "210", "AL1", "AL2"])
    reports.sort(key=lambda r: _callsign_sort_key(r.callsign))

    groups = _group_by_command_structure(reports)

    assert [key for key, _ in groups] == ["100", "200", None]
    assert [r.callsign for r in groups[0][1]] == ["100", "110", "120", "130"]
    assert [r.callsign for r in groups[1][1]] == ["200", "210"]
    assert [r.callsign for r in groups[2][1]] == ["AL1", "AL2"]


def test_group_by_command_structure_handles_blank_or_missing_callsign():
    reports = _reports(["100", "", None])
    reports.sort(key=lambda r: _callsign_sort_key(r.callsign))
    groups = _group_by_command_structure(reports)
    assert groups[-1][0] is None
