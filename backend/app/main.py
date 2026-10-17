"""FastAPI application factory.

Run locally with: uv run uvicorn app.main:create_app --factory --reload
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.models.clock import Clock, SystemUTCClock
from app.repositories.database import apply_migrations
from app.repositories.word_repository import SqliteWordRepository
from app.services.daily_word_service import DailyWordService

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, clock: Clock | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        applied = await run_in_threadpool(apply_migrations, settings.database_path)
        if applied:
            logger.info("applied database migrations %s", applied)
        app.state.daily_word_service = DailyWordService(
            repository=SqliteWordRepository(settings.database_path),
            clock=clock or SystemUTCClock(),
            selection_key=settings.selection_key_bytes,
        )
        logger.info("app started env=%s", settings.env.value)
        yield

    app = FastAPI(
        title=settings.app_name,
        docs_url="/api/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = settings

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

    install_error_handlers(app)
    app.include_router(api_router)
    return app
