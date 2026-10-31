"""FastAPI application factory."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import (
    ai,
    backup,
    consolidation,
    curriculum,
    discovery,
    drills,
    enrichment,
    error_log,
    export,
    health,
    library,
    productions,
    reviews,
    session,
    speech,
    stats,
    transcripts,
    writing,
)
from app.api import settings as settings_api
from app.api.errors import register_error_handlers
from app.api.frontend import mount_frontend
from app.api.guard import ApiGuard
from app.api.headers import LocalhostRedirect, SecurityHeaders
from app.config import Settings, get_settings
from app.services import backup_auto


def startup_backup(settings: Settings) -> None:
    """The startup copy of the automatic backup (D-307). A function of its own, so the test suite
    can switch it off: tests must never read, let alone copy, the owner's real database."""
    backup_auto.at_startup(settings)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # An automatic backup copy when the last one is over 24 h old (D-307). In the loop's own
        # executor, so the start is not delayed; it never raises.
        asyncio.get_running_loop().run_in_executor(None, startup_backup, settings)
        yield

    app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
    # Middleware order, innermost first (the last one added is the outermost):
    # CORS, security headers, the localhost redirect (use mode), then the Host guard (D-061).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # One router per module, all under /api (see docs/SPEC.md, section 5).
    app.include_router(health.router, prefix="/api")
    app.include_router(ai.router, prefix="/api")
    app.include_router(settings_api.router, prefix="/api")
    app.include_router(library.router, prefix="/api")
    app.include_router(enrichment.router, prefix="/api")
    app.include_router(session.router, prefix="/api")
    app.include_router(reviews.router, prefix="/api")
    app.include_router(discovery.router, prefix="/api")
    app.include_router(error_log.router, prefix="/api")
    app.include_router(productions.router, prefix="/api")
    app.include_router(writing.router, prefix="/api")
    app.include_router(transcripts.router, prefix="/api")
    app.include_router(drills.router, prefix="/api")
    app.include_router(speech.router, prefix="/api")
    app.include_router(consolidation.router, prefix="/api")
    app.include_router(curriculum.router, prefix="/api")
    app.include_router(stats.router, prefix="/api")
    app.include_router(export.router, prefix="/api")
    app.include_router(backup.router, prefix="/api")
    register_error_handlers(app)
    if settings.use_mode:
        # Last route of all, so every API route and /docs win over the page fallback (D-310).
        mount_frontend(app, settings.frontend_dist)
    app.add_middleware(SecurityHeaders)
    if settings.use_mode:
        app.add_middleware(LocalhostRedirect, port=settings.port)
    # Added last, so it is the outermost layer: even a CORS preflight goes through the Host check,
    # and a foreign Host is refused (403) before the localhost redirect can answer.
    app.add_middleware(ApiGuard, port=settings.port, allowed_origins=settings.cors_origins)
    return app


app = create_app()
