"""Central application configuration.

Reads from environment variables (optionally loaded from a local .env file).
No secrets are hard-coded. Kept as a plain dataclass rather than pulling in
pydantic-settings, since the app already depends on pydantic and dotenv and
does not need a second settings framework.
"""
from __future__ import annotations

import os
import secrets
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
    access_password: str | None
    session_secret: str
    project_root: Path = PROJECT_ROOT

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def auth_enabled(self) -> bool:
        return bool(self.access_password)


def _get_or_create_session_secret(project_root: Path) -> str:
    """A stable secret is needed to keep login sessions valid across app
    restarts. If not explicitly configured, generate one once and persist it
    locally (gitignored) rather than regenerating on every restart, which
    would silently log everyone out each time the server restarts."""
    env_value = os.environ.get("AAR_SESSION_SECRET")
    if env_value:
        return env_value
    secret_file = project_root / "data" / ".session_secret"
    if secret_file.exists():
        return secret_file.read_text().strip()
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_hex(32)
    secret_file.write_text(secret)
    return secret


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
        access_password=os.environ.get("AAR_ACCESS_PASSWORD") or None,
        session_secret=_get_or_create_session_secret(PROJECT_ROOT),
    )
