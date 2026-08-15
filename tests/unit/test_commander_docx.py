from pathlib import Path

import pytest
from docx import Document

from aar.ingestion.commander_docx import (
    CommanderReportParseError,
    generate_commander_report_template,
    parse_commander_report,
)
from aar.models.enums import ObjectiveAchieved


def _fill_template(tmp_path: Path, *, fill_identity=True, fill_objective=True, narrative_text="Testverhaal.") -> Path:
    template_path = tmp_path / "template.docx"
    generate_commander_report_template(template_path)
    doc = Document(str(template_path))

    if fill_identity:
        table = doc.tables[0]
        table.rows[0].cells[1].text = "P12"
        table.rows[1].cells[1].text = "1ste Hulpcentrum"
        table.rows[2].cells[1].text = "Adjudant"
        table.rows[3].cells[1].text = "Janssens"

    if fill_objective:
        obj_table = doc.tables[1]
        obj_table.rows[0].cells[1].text = "Gedeeltelijk"
        obj_table.rows[1].cells[1].text = "Doel deels bereikt door tijdsdruk."

    # Fill the first empty paragraph after each Heading 1 with narrative_text.
    for i, paragraph in enumerate(doc.paragraphs):
        style_name = paragraph.style.name if paragraph.style else ""
        if style_name == "Heading 1" and "B. Eerste" in paragraph.text:
            doc.paragraphs[i + 1].text = narrative_text

    out_path = tmp_path / "filled.docx"
    doc.save(str(out_path))
    return out_path


def test_generate_template_creates_file(tmp_path):
    path = generate_commander_report_template(tmp_path / "t.docx")
    assert path.exists()
    assert path.stat().st_size > 0


def test_parse_complete_valid_report(tmp_path):
    path = _fill_template(tmp_path)
    raw, warnings = parse_commander_report(path)

    assert raw.identity.callsign == "P12"
    assert raw.identity.unit_name == "1ste Hulpcentrum"
    assert raw.identity.rank == "Adjudant"
    assert raw.identity.surname == "Janssens"
    assert raw.identity.display_name == "P12 (1ste Hulpcentrum) — Adjudant Janssens"
    assert raw.objective_achieved == ObjectiveAchieved.GEDEELTELIJK
    assert "tijdsdruk" in raw.objective_achieved_explanation
    assert raw.sections["observations"] == "Testverhaal."
    assert raw.sections["narrative"] == ""  # left empty in this fixture
    assert any("leeg" in w for w in warnings)  # other empty sections flagged


def test_parse_missing_optional_field_still_parses(tmp_path):
    path = _fill_template(tmp_path, narrative_text="")
    raw, warnings = parse_commander_report(path)
    assert raw.sections["observations"] == ""
    assert any("Eerste en relevante waarnemingen" in w for w in warnings)


def test_parse_missing_identification_flags_warning(tmp_path):
    path = _fill_template(tmp_path, fill_identity=False)
    raw, warnings = parse_commander_report(path)
    assert not raw.identity.is_complete
    assert any("identificatievelden" in w.lower() for w in warnings)


def test_parse_missing_objective_answer_flags_warning(tmp_path):
    path = _fill_template(tmp_path, fill_objective=False)
    raw, warnings = parse_commander_report(path)
    assert raw.objective_achieved is None
    assert any("doel bereikt" in w.lower() for w in warnings)


def test_parse_long_narrative(tmp_path):
    long_text = "Dit is een lang verhaal. " * 200
    path = _fill_template(tmp_path, narrative_text=long_text)
    raw, _ = parse_commander_report(path)
    assert len(raw.sections["observations"]) > 1000


def test_parse_empty_narrative_not_an_error(tmp_path):
    path = _fill_template(tmp_path, narrative_text="")
    raw, warnings = parse_commander_report(path)
    assert raw.sections["observations"] == ""


def test_parse_unusual_punctuation(tmp_path):
    weird = 'Waarneming: "rook" — zwaar!! (±3m) café-terras… 50%??'
    path = _fill_template(tmp_path, narrative_text=weird)
    raw, _ = parse_commander_report(path)
    assert raw.sections["observations"] == weird


def test_parse_dutch_uncertainty_wording_preserved_verbatim(tmp_path):
    text = "Ik ging ervan uit dat de achterzijde al gecontroleerd was. Volgens mij was er niemand meer binnen."
    path = _fill_template(tmp_path, narrative_text=text)
    raw, _ = parse_commander_report(path)
    assert "Ik ging ervan uit" in raw.sections["observations"]
    assert "Volgens mij" in raw.sections["observations"]


def test_parse_corrupt_docx_raises_clear_error(tmp_path):
    bad_path = tmp_path / "corrupt.docx"
    bad_path.write_bytes(b"not a real docx file")
    with pytest.raises(CommanderReportParseError):
        parse_commander_report(bad_path)


def test_parse_wrong_document_raises_clear_error(tmp_path):
    doc = Document()
    doc.add_paragraph("Dit is gewoon een willekeurig Word-document zonder de juiste structuur.")
    path = tmp_path / "wrong.docx"
    doc.save(str(path))
    with pytest.raises(CommanderReportParseError):
        parse_commander_report(path)
