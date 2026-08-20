from pathlib import Path

import pytest
from docx import Document

from aar.ingestion.commander_docx import (
    CommanderReportParseError,
    generate_commander_report_template,
    parse_commander_report,
)
from fixtures.synthetic_incident.build_fixture import _fill_action_blocks


def _fill_template(
    tmp_path: Path, *, fill_identity=True, narrative_text="Testverhaal.", action_rows=None
) -> Path:
    template_path = tmp_path / "template.docx"
    generate_commander_report_template(template_path)
    doc = Document(str(template_path))

    if fill_identity:
        table = doc.tables[0]
        table.rows[0].cells[1].text = "P12"
        table.rows[1].cells[1].text = "1ste Hulpcentrum"
        table.rows[2].cells[1].text = "Adjudant"
        table.rows[3].cells[1].text = "Janssens"

    if action_rows:
        _fill_action_blocks(doc, action_rows)

    # Fill the first empty paragraph after each Heading 1 with narrative_text.
    for i, paragraph in enumerate(doc.paragraphs):
        style_name = paragraph.style.name if paragraph.style else ""
        if style_name == "Heading 1" and "B. Feiten" in paragraph.text:
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
    assert raw.sections["situation"] == "Testverhaal."
    assert raw.sections["actions"] == ""  # left empty in this fixture
    assert any("leeg" in w for w in warnings)  # other empty sections flagged


def test_parse_missing_optional_field_still_parses(tmp_path):
    path = _fill_template(tmp_path, narrative_text="")
    raw, warnings = parse_commander_report(path)
    assert raw.sections["situation"] == ""
    assert any("Feiten, info en waarnemingen bij aankomst" in w for w in warnings)


def test_parse_missing_identification_flags_warning(tmp_path):
    path = _fill_template(tmp_path, fill_identity=False)
    raw, warnings = parse_commander_report(path)
    assert not raw.identity.is_complete
    assert any("identificatievelden" in w.lower() for w in warnings)


def test_parse_has_no_objective_field_and_no_warning_about_it(tmp_path):
    """The current template deliberately no longer asks for the overall
    doelbereik answer in the report — parsing must not treat that as a
    gap to flag; the facilitator sets it later, live during the AAR."""
    path = _fill_template(tmp_path)
    raw, warnings = parse_commander_report(path)
    assert raw.objective_achieved is None
    assert not any("doel bereikt" in w.lower() for w in warnings)


def test_parse_long_narrative(tmp_path):
    long_text = "Dit is een lang verhaal. " * 200
    path = _fill_template(tmp_path, narrative_text=long_text)
    raw, _ = parse_commander_report(path)
    assert len(raw.sections["situation"]) > 1000


def test_parse_empty_narrative_not_an_error(tmp_path):
    path = _fill_template(tmp_path, narrative_text="")
    raw, warnings = parse_commander_report(path)
    assert raw.sections["situation"] == ""


def test_parse_unusual_punctuation(tmp_path):
    weird = 'Waarneming: "rook" — zwaar!! (±3m) café-terras… 50%??'
    path = _fill_template(tmp_path, narrative_text=weird)
    raw, _ = parse_commander_report(path)
    assert raw.sections["situation"] == weird


def test_parse_dutch_uncertainty_wording_preserved_verbatim(tmp_path):
    text = "Ik ging ervan uit dat de achterzijde al gecontroleerd was. Volgens mij was er niemand meer binnen."
    path = _fill_template(tmp_path, narrative_text=text)
    raw, _ = parse_commander_report(path)
    assert "Ik ging ervan uit" in raw.sections["situation"]
    assert "Volgens mij" in raw.sections["situation"]


def test_parse_corrupt_docx_raises_clear_error(tmp_path):
    bad_path = tmp_path / "corrupt.docx"
    bad_path.write_bytes(b"not a real docx file")
    with pytest.raises(CommanderReportParseError):
        parse_commander_report(bad_path)


def test_parse_empty_document_raises_clear_error(tmp_path):
    doc = Document()
    path = tmp_path / "empty.docx"
    doc.save(str(path))
    with pytest.raises(CommanderReportParseError):
        parse_commander_report(path)


def test_parse_free_form_document_falls_back_to_narrative_section(tmp_path):
    """Real reports don't always follow the template (spec discussion: a
    writer's own free-form headers like "Acties uitgevoerd:" instead of our
    section headings). Rather than rejecting the whole upload, the full text
    is captured as one narrative passage with an explicit warning."""
    doc = Document()
    doc.add_paragraph("AAR (PD Sgt Pannekoeke Maarten)")
    doc.add_paragraph("Bij aankomst gemeld bij de officier, callsign 210 gekregen.")
    doc.add_paragraph("Eerste opdracht SAR van verdiep 9 en zo naar beneden werken.")
    path = tmp_path / "freeform.docx"
    doc.save(str(path))

    raw, warnings = parse_commander_report(path)

    assert "callsign 210" in raw.sections["narrative"]
    assert "SAR van verdiep 9" in raw.sections["narrative"]
    assert any("volgt niet het standaard" in w for w in warnings)


def test_parse_actions_table_formats_action_and_result(tmp_path):
    path = _fill_template(
        tmp_path,
        action_rows=[
            ("Interne aanval ingezet via voordeur.", "Brand snel blussen.", "Brand snel geblust.", ""),
            (
                "Achterzijde gecontroleerd op slachtoffers.",
                "Zekerheid over veiligheid achterzijde.",
                "Gedeeltelijk gelukt",
                "Controle gebeurde later dan bedoeld.",
            ),
        ],
    )
    raw, warnings = parse_commander_report(path)

    assert raw.sections["actions"] == (
        "Actie: Interne aanval ingezet via voordeur. | Doel: Brand snel blussen. | "
        "Resultaat: Brand snel geblust.\n"
        "Actie: Achterzijde gecontroleerd op slachtoffers. | Doel: Zekerheid over "
        "veiligheid achterzijde. | Resultaat: Gedeeltelijk gelukt | Toelichting: "
        "Controle gebeurde later dan bedoeld."
    )
    assert not any("Acties" in w and "leeg" in w for w in warnings)


def test_parse_actions_table_empty_is_flagged(tmp_path):
    path = _fill_template(tmp_path, action_rows=None)
    raw, warnings = parse_commander_report(path)

    assert raw.sections["actions"] == ""
    assert any("C. Acties" in w and "leeg" in w for w in warnings)


def test_parse_actions_table_flags_missing_resultaat(tmp_path):
    path = _fill_template(
        tmp_path,
        action_rows=[("Ventilatie gestart.", "", "", "")],
    )
    raw, warnings = parse_commander_report(path)

    assert "Actie: Ventilatie gestart." in raw.sections["actions"]
    assert any("geen resultaat" in w for w in warnings)


def test_parse_actions_table_skips_fully_blank_rows(tmp_path):
    path = _fill_template(tmp_path, action_rows=[("Enige actie.", "", "Gelukt.", "")])
    raw, _ = parse_commander_report(path)

    # The template ships with 5 starter rows; only one was filled in, the
    # rest must not show up as empty "" entries.
    assert raw.sections["actions"] == "Actie: Enige actie. | Resultaat: Gelukt."
