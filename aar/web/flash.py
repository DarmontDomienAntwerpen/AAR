"""Stateless flash messages via URL query params (no session/cookie
middleware needed for a single-operator local tool)."""
from __future__ import annotations

from urllib.parse import urlencode

from fastapi.responses import RedirectResponse


def redirect_with_flash(url: str, message: str, flash_type: str = "success") -> RedirectResponse:
    query = urlencode({"flash": message, "flash_type": flash_type})
    separator = "&" if "?" in url else "?"
    return RedirectResponse(f"{url}{separator}{query}", status_code=303)
