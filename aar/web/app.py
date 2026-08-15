"""FastAPI application factory for the Fire Service AAR Tool."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from aar.config.logging_setup import configure_logging, get_logger
from aar.db.session import get_engine, init_db
from aar.web.routes import analysis, archive, final_aar, incidents, interactive_aar, media, sources

configure_logging()
logger = get_logger("web.app")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    init_db(get_engine())
    logger.info("Database geïnitialiseerd.")
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="AAR Tool — Brandweer", lifespan=_lifespan)

    app.include_router(archive.router)
    app.include_router(incidents.router)
    app.include_router(sources.router)
    app.include_router(media.router)
    app.include_router(analysis.router)
    app.include_router(interactive_aar.router)
    app.include_router(final_aar.router)

    return app


app = create_app()
