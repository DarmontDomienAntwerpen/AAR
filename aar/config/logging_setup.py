"""Application-wide logging configuration.

Deliberately does not log full report/narrative contents (which contain
personal names and operational details) — only identifiers, counts, and
outcomes. Call `configure_logging()` once, early, from `app.py` and from the
pytest session fixture.
"""
from __future__ import annotations

import logging
import sys

from aar.config.settings import get_settings

_CONFIGURED = False


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    settings = get_settings()
    root = logging.getLogger("aar")
    root.setLevel(settings.log_level)
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
        )
        root.addHandler(handler)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(f"aar.{name}")
