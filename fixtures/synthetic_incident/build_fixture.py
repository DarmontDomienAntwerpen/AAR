"""Builds the synthetic golden-fixture incident (spec §62-64): a realistic
but entirely fictional woningbrand with four commander reports and one
dispatch spreadsheet, engineered to contain the specific test conditions
from spec §63 (A-J). Personnel, address, and callsigns are all fictional.

Files are generated on demand into a caller-supplied directory rather than
checked into git as binary blobs — regenerating from the (versioned, human-
readable) narrative text below is more maintainable than diffing .docx/.xlsx
binaries, and keeps the fixture in sync with the template automatically.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
from docx import Document

from aar.ingestion.commander_docx import ACTION_FIELD_LABELS, SECTION_HEADINGS, generate_commander_report_template

# Each entry: (actie, doel, resultaat, toelichting) — resultaat is free text
# describing what happened, filled into the C. Acties blocks (see
# aar.ingestion.commander_docx.ACTION_FIELD_LABELS). Toelichting is extra
# context, mainly useful when the result wasn't a clean success.
ActionRow = tuple[str, str, str, str]

_ACTION_START_RE = re.compile(r"^actie\s*\d+\s*$", re.IGNORECASE)

INCIDENT = {
    "date": "2026-03-04",
    "location": "Kerkstraat 45, Antwerpen",
    "incident_type": "Brand",
    "description": "Woningbrand met mogelijk aanwezige bewoner, fictieve testcasus.",
}

# Each entry: identity fields + the 5 narrative sections (situation, actions,
# went_well, went_less_well, other) + objective_achieved. "actions" is a
# list[ActionRow] (table rows), every other section is plain text.
REPORTS = [
    {
        "callsign": "P12",
        "unit_name": "1ste Hulpcentrum",
        "rank": "Adjudant",
        "surname": "Janssens",
        "objective_achieved": "Gedeeltelijk",
        "objective_achieved_explanation": (
            "Doel gedeeltelijk bereikt: de brand werd onder controle gebracht, maar de "
            "uitbreiding naar de eerste verdieping werd pas laat ontdekt."
        ),
        "sections": {
            "situation": (
                "Bij aankomst was er matige rookontwikkeling zichtbaar aan de voorzijde van "
                "de woning op het gelijkvloers. Er waren geen zichtbare vlammen vanaf de "
                "straatzijde.\n\n"
                "Ik wist dat het om een alleenstaande woning ging met vermoedelijk twee "
                "bewoners. Het was niet duidelijk of de bewoners op het moment van de brand "
                "thuis waren."
            ),
            "actions": [
                (
                    "Besliste om onmiddellijk een interne aanval in te zetten via de "
                    "voordeur, met P21 als aanvulling aan de achterzijde.",
                    "De brand snel onder controle krijgen vooraleer uitbreiding naar de "
                    "bovenverdieping, na inschatting dat de brand zich beperkte tot het "
                    "gelijkvloers.",
                    "Geslaagde actie",
                    "",
                ),
                (
                    "Gaf via de portofoon de opdracht aan P21 om de achterzijde van het "
                    "pand te controleren op aanwezigheid van slachtoffers en doorslag van "
                    "de brand.",
                    "Zekerheid krijgen over de veiligheid van de achterzijde.",
                    "Gedeeltelijk geslaagde actie",
                    "De controle gebeurde later dan bedoeld; er bleek meer rookschade op "
                    "de eerste verdieping dan initieel ingeschat.",
                ),
            ],
            "went_well": (
                "De eerste interne aanval verliep vlot en de communicatie met O01 bij "
                "aankomst was duidelijk."
            ),
            "went_less_well": (
                "De controle van de eerste verdieping gebeurde later dan gewenst. Waarom: "
                "er was aanvankelijk onvoldoende zicht op de toestand van de eerste "
                "verdieping vanaf de buitenzijde."
            ),
            "other": (
                "Ik ging ervan uit dat P21 de achterzijde van het pand had gecontroleerd op "
                "basis van mijn eerdere opdracht."
            ),
        },
    },
    {
        "callsign": "P21",
        "unit_name": "2de Hulpcentrum",
        "rank": "Sergeant",
        "surname": "Willems",
        "objective_achieved": "Ja",
        "objective_achieved_explanation": "Ondersteuning werd geboden zoals gepland.",
        "sections": {
            "situation": (
                "Bij aankomst zag ik lichte rookontwikkeling aan de achterzijde van de "
                "woning, via een raam op het gelijkvloers.\n\n"
                "Ik had op dat moment geen rechtstreeks zicht op de situatie aan de voorzijde."
            ),
            "actions": [
                (
                    "Besliste om eerst het materiaal voor de tweede straal klaar te "
                    "zetten vooraleer naar de achterzijde te gaan.",
                    "Ondersteuning bieden aan de eerste ploeg zodra nodig, na inschatting "
                    "dat de achterzijde geen onmiddellijk gevaar vormde.",
                    "Geslaagde actie",
                    "",
                ),
                (
                    "Achterzijde gecontroleerd op aanwezigheid van slachtoffers.",
                    "Zekerheid krijgen dat er niemand meer aanwezig was aan de "
                    "achterzijde.",
                    "Niet geslaagde actie",
                    "Geen expliciete opdracht hiertoe ontvangen — controle gebeurde "
                    "later dan nodig. Later bleek dat er toch nog een slachtoffer op de "
                    "eerste verdieping aanwezig was, aangetroffen door de zoekploeg van "
                    "P34.",
                ),
            ],
            "went_well": "De voorbereiding van het materiaal verliep snel.",
            "went_less_well": (
                "De controle van de achterzijde gebeurde later dan verwacht. Waarom: er "
                "was onduidelijkheid over wie welke controle zou uitvoeren."
            ),
            "other": "Volgens mij was er op dat moment niemand meer aanwezig op de eerste verdieping.",
        },
    },
    {
        "callsign": "O01",
        "unit_name": "Officier van Wacht",
        "rank": "Luitenant",
        "surname": "Peeters",
        "objective_achieved": "Ja",
        "objective_achieved_explanation": "Het slachtoffer werd gevonden en het incident werd onder controle gebracht.",
        "sections": {
            "situation": (
                "Bij aankomst zag ik dat P12 reeds een interne aanval was gestart via de "
                "voordeur.\n\n"
                "Ik werd op de hoogte gebracht van een mogelijke bewoner die nog binnen kon "
                "zijn, maar dit kon niemand bevestigen."
            ),
            "actions": [
                (
                    "Besliste om P34 met de ladderwagen in te zetten voor een gerichte "
                    "zoekactie op de eerste verdieping en vroeg opschaling naar de tweede "
                    "alarmfase aan.",
                    "Zekerheid krijgen over de aanwezigheid van slachtoffers en "
                    "voldoende capaciteit voorzien, gezien de onduidelijkheid over de "
                    "bewoners.",
                    "Geslaagde actie",
                    "",
                ),
                (
                    "Coördineerde de opschaling en de inzet van de zoekploeg.",
                    "Slachtoffer zo snel mogelijk lokaliseren en overdragen aan medische "
                    "hulp.",
                    "Geslaagde actie",
                    "Zoekploeg van P34 trof nadien een slachtoffer aan op de eerste "
                    "verdieping; het slachtoffer werd op tijd aangetroffen en overgedragen "
                    "aan de MUG. De brand werd nadien volledig onder controle gebracht.",
                ),
            ],
            "went_well": "-",
            "went_less_well": "-",
            "other": "Ik veronderstelde dat de opschaling tijdig zou aankomen gezien de aard van de melding.",
        },
    },
    {
        "callsign": "P34",
        "unit_name": "3de Hulpcentrum",
        "rank": "Onderluitenant",
        "surname": "De Smet",
        "objective_achieved": "Ja",
        "objective_achieved_explanation": "Slachtoffer tijdig gevonden en geëvacueerd.",
        "sections": {
            "situation": (
                "Bij aankomst kregen we de opdracht om de eerste verdieping systematisch te "
                "doorzoeken.\n\n"
                "We wisten niet zeker of er nog iemand aanwezig was, maar gingen uit van een "
                "mogelijke aanwezigheid gezien de onbevestigde melding."
            ),
            "actions": [
                (
                    "Besloten de zoekactie systematisch kamer per kamer uit te voeren.",
                    "Zo snel mogelijk zekerheid krijgen over eventuele slachtoffers, na "
                    "inschatting dat de rookontwikkeling op de eerste verdieping de "
                    "zoekactie bemoeilijkte maar niet onmogelijk maakte.",
                    "Geslaagde actie",
                    "",
                ),
                (
                    "Slachtoffer aangetroffen in de tweede kamer en onmiddellijk "
                    "geëvacueerd.",
                    "Slachtoffer veilig overdragen aan medische hulp.",
                    "Geslaagde actie",
                    "Overgedragen aan de MUG-ploeg die klaarstond; het slachtoffer werd "
                    "op tijd aangetroffen en overgedragen.",
                ),
            ],
            "went_well": "-",
            "went_less_well": "-",
            "other": (
                "We gingen ervan uit dat het slachtoffer zich op de eerste verdieping "
                "bevond op basis van de eerste inschatting van O01."
            ),
        },
    },
]

# Deliberately shares "waarnemingen"/"aankomst" vocabulary with the mock
# provider's category-label-based event text so dispatch enrichment has a
# real, unambiguous match to demonstrate spec §63-G end to end. Other rows
# use disjoint vocabulary so they don't create a false/ambiguous match.
DISPATCH_ROWS = [
    {"Tijdstip": "2026-03-04 14:07:00", "Gebeurtenis": "Eerste voertuig P12 ter plaatse - waarnemingen bij aankomst bevestigd", "Eenheid": "P12"},
    {"Tijdstip": "2026-03-04 14:09:00", "Gebeurtenis": "Opschaling naar tweede alarmfase aangevraagd", "Eenheid": "O01"},
    {"Tijdstip": None, "Gebeurtenis": None, "Eenheid": None},  # blank row: must be skipped, not crash
    {"Tijdstip": "2026-03-04 14:19:00", "Gebeurtenis": "Slachtoffer aangetroffen eerste verdieping", "Eenheid": "P34"},
    {"Tijdstip": "2026-03-04 14:24:00", "Gebeurtenis": "Slachtoffer geëvacueerd, overgedragen aan MUG-ploeg", "Eenheid": "P34"},
    {"Tijdstip": "2026-03-04 14:31:00", "Gebeurtenis": "Brand onder controle", "Eenheid": "O01"},
]


def _fill_action_blocks(doc: Document, action_rows: list[ActionRow]) -> None:
    """Fills the 'Actie N' / Doel / Resultaat / Toelichting paragraph blocks
    (see aar.ingestion.commander_docx.generate_commander_report_template) —
    these aren't table cells, so filling means writing into whichever blank
    paragraph immediately follows each bold field label."""
    paragraphs = doc.paragraphs
    block_index = -1
    field = None  # "actie", or an index into ACTION_FIELD_LABELS
    for paragraph in paragraphs:
        text = paragraph.text.strip().rstrip(":").strip()
        if _ACTION_START_RE.match(text):
            block_index += 1
            field = "actie"
            continue
        if text in ACTION_FIELD_LABELS:
            field = ACTION_FIELD_LABELS.index(text)
            continue
        if field is not None and paragraph.text == "" and 0 <= block_index < len(action_rows):
            actie, doel, resultaat, toelichting = action_rows[block_index]
            paragraph.text = actie if field == "actie" else (doel, resultaat, toelichting)[field]
            field = None


def _fill_report(out_dir: Path, spec: dict) -> Path:
    template_path = out_dir / f"_template_{spec['callsign']}.docx"
    generate_commander_report_template(template_path)
    doc = Document(str(template_path))

    id_table = doc.tables[0]
    id_table.rows[0].cells[1].text = spec["callsign"]
    id_table.rows[1].cells[1].text = spec["unit_name"]
    id_table.rows[2].cells[1].text = spec["rank"]
    id_table.rows[3].cells[1].text = spec["surname"]

    _fill_action_blocks(doc, spec["sections"]["actions"])

    # "actions" is filled via the blocks above, not a single blank
    # paragraph — skip it here so the generic paragraph-fill loop below
    # doesn't try to write a list into paragraph.text.
    heading_to_key = {v: k for k, v in SECTION_HEADINGS.items() if k != "actions"}
    current_key = None
    for i, paragraph in enumerate(doc.paragraphs):
        style_name = paragraph.style.name if paragraph.style else ""
        if style_name == "Heading 1" and paragraph.text.strip() in heading_to_key:
            current_key = heading_to_key[paragraph.text.strip()]
        elif current_key is not None and paragraph.text == "":
            paragraph.text = spec["sections"].get(current_key, "")
            current_key = None  # only the first blank paragraph after a heading is the fill target

    out_path = out_dir / f"{spec['callsign']}_{spec['surname']}.docx"
    doc.save(str(out_path))
    template_path.unlink()
    return out_path


def build_commander_reports(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    return [_fill_report(out_dir, spec) for spec in REPORTS]


def build_dispatch_excel(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(DISPATCH_ROWS)
    path = out_dir / "dispatch.xlsx"
    df.to_excel(path, index=False)
    return path
