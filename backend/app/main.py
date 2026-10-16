"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import ai, health
from app.api import settings as settings_api
from app.api.errors import register_error_handlers
from app.api.guard import ApiGuard
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title=settings.app_name, version=__version__)
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
    register_error_handlers(app)
    # Added last, so it is the outermost layer: even a CORS preflight goes through the Host check.
    app.add_middleware(ApiGuard, port=settings.port, allowed_origins=settings.cors_origins)
    return app


app = create_app()
