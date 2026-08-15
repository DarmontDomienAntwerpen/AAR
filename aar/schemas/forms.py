"""Schemas for human-entered data (Streamlit forms)."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from aar.models.enums import IncidentType


class IncidentCreateForm(BaseModel):
    date: dt.date
    location: str = Field(min_length=1)
    incident_type: IncidentType
    description: str = ""
