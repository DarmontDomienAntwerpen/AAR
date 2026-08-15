"""Regenerate templates/commander_report_template.docx.

Run with: python scripts/generate_template.py
"""
from pathlib import Path

from aar.ingestion.commander_docx import generate_commander_report_template

if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "templates" / "commander_report_template.docx"
    generate_commander_report_template(out)
    print(f"Written: {out}")
