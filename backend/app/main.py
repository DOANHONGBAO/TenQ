"""FastAPI application factory.

Run locally with: uv run uvicorn app.main:create_app --factory --reload
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from starlette.concurrency import run_in_threadpool

from app.api.router import api_router
from app.core.circuit_breaker import CircuitBreaker
from app.core.config import Environment, Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import BodySizeLimitMiddleware, OriginGuardMiddleware
from app.core.session import Identifiers, SessionCodec
from app.integrations.ai_judge import AIJudge
from app.integrations.ollama_client import OllamaClient, OllamaOptions, make_http_client
from app.integrations.ollama_mock import MockOllamaProvider
from app.integrations.turnstile import TurnstileVerifier
from app.models.clock import Clock, SystemUTCClock
from app.models.game import MAX_QUESTIONS
from app.repositories.abuse_store import AbuseStore
from app.repositories.database import apply_migrations
from app.repositories.game_store import RedisGameStore
from app.repositories.judge_cache import JudgeCache
from app.repositories.player_name_repository import SqlitePlayerNameRepository
from app.repositories.word_repository import SqliteWordRepository
from app.services.daily_word_service import DailyWordService
from app.services.game_service import GameService
from app.services.judge_service import HybridJudge
from app.services.session_service import SessionLimits, SessionService

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    clock: Clock | None = None,
    judge: AIJudge | None = None,
    turnstile_transport: httpx2.AsyncBaseTransport | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    clock = clock or SystemUTCClock()

    def turnstile_transport_client() -> httpx2.AsyncClient:
        return (
            httpx2.AsyncClient(transport=turnstile_transport)
            if turnstile_transport
            else (httpx2.AsyncClient())
        )

    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        applied = await run_in_threadpool(apply_migrations, settings.database_path)
        if applied:
            logger.info("applied database migrations %s", applied)
        words = DailyWordService(
            repository=SqliteWordRepository(settings.database_path),
            clock=clock,
            selection_key=settings.selection_key_bytes,
        )
        redis = Redis.from_url(
            settings.redis_url.get_secret_value(),
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )
        if settings.ai_judge == "ollama":
            api_key = (
                settings.ollama_api_key.get_secret_value() if settings.ollama_api_key else None
            )
            http = make_http_client(settings.ollama_base_url, api_key)
            model = settings.ollama_model or ""
        else:
            http = make_http_client("http://mock-ollama", None, MockOllamaProvider().transport())
            model = "mock"
        hybrid_holder: list[HybridJudge] = []

        async def budget_guard() -> None:
            await hybrid_holder[0].take_budget()

        client = OllamaClient(
            http,
            OllamaOptions(
                model=model,
                num_predict=settings.ollama_num_predict,
                think=settings.ollama_think_value,
            ),
            before_attempt=budget_guard,
        )
        hybrid = HybridJudge(
            client,
            JudgeCache(redis),
            CircuitBreaker(),
            clock,
            deadline_s=settings.judge_timeout_s - 1,
            daily_budget=settings.ai_daily_budget,
            hourly_budget=settings.ai_hourly_budget,
            max_concurrency=settings.ai_max_concurrency,
        )
        hybrid_holder.append(hybrid)
        app.state.daily_word_service = words
        codec = SessionCodec(settings.session_secret_bytes, settings.previous_session_secret_bytes)
        identifiers = Identifiers(settings.player_hash_key_bytes)
        abuse = AbuseStore(redis)
        turnstile_http = turnstile_transport_client()
        app.state.clock = clock
        app.state.session_codec = codec
        app.state.identifiers = identifiers
        app.state.abuse_store = abuse
        app.state.session_service = SessionService(
            codec,
            identifiers,
            TurnstileVerifier(
                turnstile_http,
                settings.turnstile_secret_key.get_secret_value(),
                allowed_hostnames=settings.turnstile_allowed_hostnames,
                expected_action=settings.turnstile_expected_action,
                allow_test_keys=settings.env is not Environment.PRODUCTION,
            ),
            abuse,
            clock,
            SessionLimits(
                per_ip_hour=settings.session_limit_per_ip_hour,
                per_device_hour=settings.session_limit_per_device_hour,
            ),
            # Test keys return the same dummy token every time; production rejects test keys.
            replay_guard=not settings.turnstile_uses_test_key,
        )
        app.state.game_service = GameService(
            store=RedisGameStore(redis, MAX_QUESTIONS),
            words=words,
            judge=judge or hybrid,
            clock=clock,
            lease_ms=settings.question_lease_ms,
            judge_timeout_s=settings.judge_timeout_s,
            names=SqlitePlayerNameRepository(settings.database_path),
        )
        logger.info(
            "app started env=%s judge=%s model=%s", settings.env.value, settings.ai_judge, model
        )
        try:
            yield
        finally:
            await http.aclose()
            await turnstile_http.aclose()
            await redis.aclose()

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

    # Outermost first: refuse non-proxy traffic, then cap body size, before any route runs.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_body_bytes)
    app.add_middleware(OriginGuardMiddleware, secrets=settings.origin_secret_list)
    install_error_handlers(app)
    app.include_router(api_router)
    return app
