"""Single shared-password login gate (spec has no multi-user auth in v1 —
this is a minimal addition so the app isn't wide open when reachable beyond
the facilitator's own machine). See aar/web/app.py for the middleware that
enforces this on every other route."""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from aar.config.settings import get_settings
from aar.web.templating import templates

router = APIRouter()


@router.get("/login")
def login_form(request: Request, next: str = "/"):
    if request.session.get("authenticated"):
        return RedirectResponse(next or "/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"next": next, "error": None})


@router.post("/login")
def login_submit(request: Request, password: str = Form(""), next: str = Form("/")):
    settings = get_settings()
    if settings.auth_enabled and secrets_match(password, settings.access_password):
        request.session["authenticated"] = True
        return RedirectResponse(next or "/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"next": next, "error": "Onjuist wachtwoord."},
        status_code=401,
    )


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


def secrets_match(a: str, b: str | None) -> bool:
    if b is None:
        return False
    return hmac.compare_digest(a, b)
