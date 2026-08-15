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

from pathlib import Path

import pandas as pd
from docx import Document

from aar.ingestion.commander_docx import SECTION_HEADINGS, generate_commander_report_template

INCIDENT = {
    "date": "2026-03-04",
    "location": "Kerkstraat 45, Antwerpen",
    "incident_type": "Brand",
    "description": "Woningbrand met mogelijk aanwezige bewoner, fictieve testcasus.",
}

# Each entry: identity fields + the 12 narrative sections + objective_achieved.
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
            "observations": (
                "Bij aankomst was er matige rookontwikkeling zichtbaar aan de voorzijde van "
                "de woning op het gelijkvloers. Er waren geen zichtbare vlammen vanaf de "
                "straatzijde."
            ),
            "information_position": (
                "Ik wist dat het om een alleenstaande woning ging met vermoedelijk twee "
                "bewoners. Het was niet duidelijk of de bewoners op het moment van de brand "
                "thuis waren."
            ),
            "assessment": (
                "Ik schatte in dat de brand zich beperkte tot het gelijkvloers en dat een "
                "snelle interne aanval haalbaar was."
            ),
            "decision": (
                "Ik besliste om onmiddellijk een interne aanval in te zetten via de "
                "voordeur, met P21 als aanvulling aan de achterzijde."
            ),
            "objective": (
                "Mijn doel was de brand snel onder controle te krijgen vooraleer uitbreiding "
                "naar de bovenverdieping."
            ),
            "narrative": (
                "We gingen naar binnen met de eerste straal. Ik gaf via de portofoon de "
                "opdracht aan P21 om de achterzijde van het pand te controleren op "
                "aanwezigheid van slachtoffers en doorslag van de brand. Kort daarna "
                "bereikte O01 de plaats en nam het commando over het geheel over."
            ),
            "result": (
                "De brand werd bereikt en grotendeels geblust binnen enkele minuten, maar "
                "er bleek meer rookschade op de eerste verdieping dan initieel ingeschat."
            ),
            "went_well": (
                "De eerste interne aanval verliep vlot en de communicatie met O01 bij "
                "aankomst was duidelijk."
            ),
            "went_less_well": "De controle van de eerste verdieping gebeurde later dan gewenst.",
            "why": "Er was aanvankelijk onvoldoende zicht op de toestand van de eerste verdieping vanaf de buitenzijde.",
            "doubts_assumptions": (
                "Ik ging ervan uit dat P21 de achterzijde van het pand had gecontroleerd op "
                "basis van mijn eerdere opdracht."
            ),
            "other": "-",
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
            "observations": (
                "Bij aankomst zag ik lichte rookontwikkeling aan de achterzijde van de "
                "woning, via een raam op het gelijkvloers."
            ),
            "information_position": "Ik had op dat moment geen rechtstreeks zicht op de situatie aan de voorzijde.",
            "assessment": "Ik schatte in dat de achterzijde geen onmiddellijk gevaar vormde.",
            "decision": (
                "Ik besliste om eerst het materiaal voor de tweede straal klaar te zetten "
                "vooraleer naar de achterzijde te gaan."
            ),
            "objective": "Mijn doel was ondersteuning bieden aan de eerste ploeg zodra nodig.",
            "narrative": (
                "Ik heb geen expliciete opdracht ontvangen om de achterzijde onmiddellijk te "
                "controleren op slachtoffers. Volgens mij was er op dat moment niemand meer "
                "aanwezig op de eerste verdieping, maar ik kon dit niet met zekerheid "
                "bevestigen."
            ),
            "result": (
                "Later bleek dat er toch nog een slachtoffer op de eerste verdieping "
                "aanwezig was, aangetroffen door de zoekploeg van P34."
            ),
            "went_well": "De voorbereiding van het materiaal verliep snel.",
            "went_less_well": "De controle van de achterzijde gebeurde later dan verwacht.",
            "why": "Er was onduidelijkheid over wie welke controle zou uitvoeren.",
            "doubts_assumptions": "Volgens mij was er op dat moment niemand meer aanwezig op de eerste verdieping.",
            "other": "-",
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
            "observations": "Bij aankomst zag ik dat P12 reeds een interne aanval was gestart via de voordeur.",
            "information_position": (
                "Ik werd op de hoogte gebracht van een mogelijke bewoner die nog binnen kon "
                "zijn, maar dit kon niemand bevestigen."
            ),
            "assessment": (
                "Gezien de onduidelijkheid over de bewoners schatte ik in dat een "
                "systematische zoekactie noodzakelijk was."
            ),
            "decision": (
                "Ik besliste om P34 met de ladderwagen in te zetten voor een gerichte "
                "zoekactie op de eerste verdieping en vroeg opschaling naar de tweede "
                "alarmfase aan."
            ),
            "objective": "Mijn doel was zekerheid krijgen over de aanwezigheid van slachtoffers en voldoende capaciteit voorzien.",
            "narrative": (
                "Kort na mijn aankomst gaf ik de opdracht tot opschaling. De zoekploeg van "
                "P34 trof nadien een slachtoffer aan op de eerste verdieping, dat vervolgens "
                "geëvacueerd werd naar de MUG-ploeg."
            ),
            "result": (
                "Het slachtoffer werd op tijd aangetroffen en overgedragen aan de MUG. De "
                "brand werd nadien volledig onder controle gebracht."
            ),
            "went_well": "-",
            "went_less_well": "-",
            "why": "-",
            "doubts_assumptions": "Ik veronderstelde dat de opschaling tijdig zou aankomen gezien de aard van de melding.",
            "other": "-",
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
            "observations": "Bij aankomst kregen we de opdracht om de eerste verdieping systematisch te doorzoeken.",
            "information_position": (
                "We wisten niet zeker of er nog iemand aanwezig was, maar gingen uit van een "
                "mogelijke aanwezigheid gezien de onbevestigde melding."
            ),
            "assessment": (
                "We schatten in dat de rookontwikkeling op de eerste verdieping de zoekactie "
                "bemoeilijkte maar niet onmogelijk maakte."
            ),
            "decision": "We besloten de zoekactie systematisch kamer per kamer uit te voeren.",
            "objective": "Ons doel was zo snel mogelijk zekerheid krijgen over eventuele slachtoffers.",
            "narrative": (
                "Tijdens de zoekactie troffen we een slachtoffer aan in de tweede kamer. We "
                "hebben het slachtoffer onmiddellijk geëvacueerd en overgedragen aan de "
                "MUG-ploeg die klaarstond."
            ),
            "result": "Het slachtoffer werd op tijd aangetroffen en overgedragen.",
            "went_well": "-",
            "went_less_well": "-",
            "why": "-",
            "doubts_assumptions": (
                "We gingen ervan uit dat het slachtoffer zich op de eerste verdieping "
                "bevond op basis van de eerste inschatting van O01."
            ),
            "other": "-",
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


def _fill_report(out_dir: Path, spec: dict) -> Path:
    template_path = out_dir / f"_template_{spec['callsign']}.docx"
    generate_commander_report_template(template_path)
    doc = Document(str(template_path))

    id_table = doc.tables[0]
    id_table.rows[0].cells[1].text = spec["callsign"]
    id_table.rows[1].cells[1].text = spec["unit_name"]
    id_table.rows[2].cells[1].text = spec["rank"]
    id_table.rows[3].cells[1].text = spec["surname"]

    obj_table = doc.tables[1]
    obj_table.rows[0].cells[1].text = spec["objective_achieved"]
    obj_table.rows[1].cells[1].text = spec["objective_achieved_explanation"]

    heading_to_key = {v: k for k, v in SECTION_HEADINGS.items()}
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
