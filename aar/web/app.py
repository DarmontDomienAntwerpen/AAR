"""FastAPI application factory for the Fire Service AAR Tool."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from aar.config.logging_setup import configure_logging, get_logger
from aar.config.settings import get_settings
from aar.db.session import get_engine, init_db
from aar.web.deps import IncidentFinalizedError
from aar.web.flash import redirect_with_flash
from aar.web.routes import analysis, archive, auth, final_aar, incidents, interactive_aar, media, sources

configure_logging()
logger = get_logger("web.app")

# Paths reachable without being logged in — just enough to render/submit the
# login form itself. Everything else is gated when AAR_ACCESS_PASSWORD is set.
_PUBLIC_PATHS = {"/login"}


@asynccontextmanager
async def _lifespan(app: FastAPI):
    init_db(get_engine())
    logger.info("Database geïnitialiseerd.")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AAR Tool — Brandweer", lifespan=_lifespan)

    # Middleware registration order matters here: Starlette runs the
    # *last*-added middleware outermost/first on the way in. require_login
    # reads request.session, so SessionMiddleware — added second — must
    # still end up wrapping *inside* it (i.e. added AFTER require_login) or
    # the session is never attached before require_login reads it.
    @app.middleware("http")
    async def require_login(request: Request, call_next):
        if settings.auth_enabled and request.url.path not in _PUBLIC_PATHS:
            if not request.session.get("authenticated"):
                return RedirectResponse(f"/login?next={request.url.path}", status_code=303)
        return await call_next(request)

    # Required for request.session (auth.py, require_login above) to work
    # at all — signs the session cookie. A stable secret (see
    # _get_or_create_session_secret in settings.py) so logins survive app
    # restarts.
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)

    @app.exception_handler(IncidentFinalizedError)
    async def _handle_incident_finalized(request: Request, exc: IncidentFinalizedError):
        fallback = f"/incidents/{request.path_params.get('incident_id')}/final" if "incident_id" in request.path_params else "/"
        target = request.headers.get("referer") or fallback
        return redirect_with_flash(target, str(exc.detail), "warning")

    app.include_router(auth.router)
    app.include_router(archive.router)
    app.include_router(incidents.router)
    app.include_router(sources.router)
    app.include_router(media.router)
    app.include_router(analysis.router)
    app.include_router(interactive_aar.router)
    app.include_router(final_aar.router)

    return app


app = create_app()
