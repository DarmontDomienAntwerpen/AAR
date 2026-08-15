"""Central application configuration.

Reads from environment variables (optionally loaded from a local .env file).
No secrets are hard-coded. Kept as a plain dataclass rather than pulling in
pydantic-settings, since the app already depends on pydantic and dotenv and
does not need a second settings framework.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    anthropic_api_key: str | None
    anthropic_model: str
    db_path: Path
    log_level: str
    project_root: Path = PROJECT_ROOT

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env", override=False)

    db_path_raw = os.environ.get("AAR_DB_PATH", "data/aar.db")
    db_path = Path(db_path_raw)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path

    return Settings(
        llm_provider=os.environ.get("AAR_LLM_PROVIDER", "mock").strip().lower(),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        anthropic_model=os.environ.get("AAR_ANTHROPIC_MODEL", "claude-sonnet-5"),
        db_path=db_path,
        log_level=os.environ.get("AAR_LOG_LEVEL", "INFO").strip().upper(),
    )
