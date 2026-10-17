"""Phase 09 QA: gaps found while mapping the test plan to the existing suite."""

import asyncio
import json
import logging
import uuid
from datetime import UTC, date, datetime

import httpx2
import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient
from pydantic import SecretStr
from redis.asyncio import Redis

from app.core.circuit_breaker import CircuitBreaker
from app.core.config import Settings
from app.integrations.ai_judge import FakeAIJudge, JudgeContext
from app.integrations.judge_prompt import PROMPT_VERSION
from app.integrations.ollama_client import OllamaClient, OllamaOptions, make_http_client
from app.integrations.ollama_mock import MockOllamaProvider
from app.main import create_app
from app.models.clock import FixedClock
from app.models.game import Answer
from app.models.question import parse_question
from app.repositories.judge_cache import JudgeCache, cache_key
from app.repositories.word_repository import SqliteWordRepository
from app.services.daily_word_service import DailyWordService
from app.services.game_service import GameService
from app.services.judge_service import HybridJudge
from tests.conftest import start_session
from tests.turnstile_mock import TurnstileMock

pytestmark = pytest.mark.anyio

ASK = "/api/v1/game/today/questions"
CONTEXT = JudgeContext(date(2026, 10, 17), "zzapple", None, "p" * 32)


def idem() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid.uuid4())}


def hybrid(
    redis: Redis, transport: httpx2.AsyncBaseTransport, **kw: object
) -> tuple[HybridJudge, httpx2.AsyncClient]:
    http = make_http_client("https://ollama.test", "k", transport)
    client = OllamaClient(http, OllamaOptions(model="m", max_retries=0))
    judge = HybridJudge(
        client,
        JudgeCache(redis),
        CircuitBreaker(),
        FixedClock(datetime(2026, 10, 17, 12, tzinfo=UTC)),
        deadline_s=3,
        daily_budget=100,
        hourly_budget=100,
        **kw,  # type: ignore[arg-type]
    )
    return judge, http


class GateTransport(httpx2.AsyncBaseTransport):
    """Holds every request until released; counts calls."""

    def __init__(self, provider: MockOllamaProvider) -> None:
        self.inner = provider.transport()
        self.gate = asyncio.Event()
        self.started = 0

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        self.started += 1
        await self.gate.wait()
        return await self.inner.handle_async_request(request)


LOOSE_LIMITS = {
    "session_limit_per_ip_hour": 1000,
    "session_limit_per_device_hour": 1000,
    "question_limit_per_player_minute": 1000,
    "question_limit_per_ip_minute": 1000,
    "question_concurrency_per_ip": 100,
}


@pytest.fixture
async def loose_api(
    settings: Settings,
    repository: SqliteWordRepository,
    clock: FixedClock,
    judge: FakeAIJudge,
    redis: Redis,
) -> object:
    """The real app with abuse limits raised, to test concurrency rather than rate limits."""
    app = create_app(
        settings.model_copy(update=LOOSE_LIMITS),
        clock=clock,
        judge=judge,
        turnstile_transport=TurnstileMock(clock).transport(),
    )
    async with app.router.lifespan_context(app):
        yield ASGITransport(app=app)


# --- concurrency -------------------------------------------------------------------------


async def test_expired_judge_lock_from_a_dead_process_does_not_block(redis: Redis) -> None:
    """A process died while holding the stampede lock: once it expires, others proceed."""
    provider = MockOllamaProvider()
    judge, http = hybrid(redis, provider.transport(), lock_ttl_ms=300)
    question = parse_question("Is it a fruit?")
    key = cache_key(CONTEXT.game_date, CONTEXT.puzzle_id, question.normalized, PROMPT_VERSION, "m")
    assert await JudgeCache(redis).acquire_lock(CONTEXT.game_date, key, "dead-process", 300)

    answer = await judge.judge(CONTEXT, question)

    assert answer in {Answer.YES, Answer.NO}
    assert provider.calls == 1
    await http.aclose()


async def test_interrupted_ollama_request_is_not_charged_and_recovers(
    redis: Redis,
    repository: SqliteWordRepository,
    word_service: DailyWordService,
    clock: FixedClock,
) -> None:
    from app.repositories.game_store import RedisGameStore

    provider = MockOllamaProvider()
    gate = GateTransport(provider)
    judge, http = hybrid(redis, gate)
    service = GameService(
        RedisGameStore(redis, 10), word_service, judge, clock, lease_ms=30_000, judge_timeout_s=5
    )
    player = "i" * 32
    task = asyncio.create_task(service.ask(player, "Is it a fruit?", str(uuid.uuid4())))
    while gate.started == 0:
        await asyncio.sleep(0.01)
    task.cancel()  # client disconnect / worker shutdown in the middle of the model call
    with pytest.raises(asyncio.CancelledError):
        await task

    state = await service.state(player)
    assert state.used == 0 and not state.in_progress  # released, not charged
    gate.gate.set()
    result = await service.ask(player, "Is it a fruit?", str(uuid.uuid4()))
    assert result.number == 1
    await http.aclose()


async def test_same_idempotency_key_in_parallel_charges_once(
    game_service: GameService, judge: FakeAIJudge
) -> None:
    judge.delay_s = 0.05
    key = str(uuid.uuid4())
    results = await asyncio.gather(
        *(game_service.ask("s" * 32, "Is it alive?", key) for _ in range(12)),
        return_exceptions=True,
    )
    successes = [r for r in results if not isinstance(r, BaseException)]
    assert successes and all(r.number == 1 for r in successes)  # type: ignore[union-attr]
    assert (await game_service.state("s" * 32)).used == 1
    assert judge.calls == 1


async def test_twelve_sessions_in_parallel_are_isolated(loose_api: ASGITransport) -> None:
    clients = [AsyncClient(transport=loose_api, base_url="http://testserver") for _ in range(12)]
    try:
        await asyncio.gather(*(start_session(c) for c in clients))
        responses = await asyncio.gather(
            *(c.post(ASK, json={"question": "Is it alive?"}, headers=idem()) for c in clients)
        )
        assert [r.status_code for r in responses] == [200] * 12
        states = await asyncio.gather(*(c.get("/api/v1/game/today") for c in clients))
        assert all(s.json()["used"] == 1 for s in states)
    finally:
        for c in clients:
            await c.aclose()


# --- security ----------------------------------------------------------------------------


async def test_daily_ai_budget_exhaustion_is_polite_and_free(
    settings: Settings,
    repository: SqliteWordRepository,
    clock: FixedClock,
    redis: Redis,
) -> None:
    turnstile = TurnstileMock(clock)
    app: FastAPI = create_app(
        settings.model_copy(update={"ai_daily_budget": 1}),
        clock=clock,
        turnstile_transport=turnstile.transport(),
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client,
    ):
        await start_session(client)
        first = await client.post(ASK, json={"question": "Is it alive?"}, headers=idem())
        second = await client.post(ASK, json={"question": "Is it heavy?"}, headers=idem())
        state = (await client.get("/api/v1/game/today")).json()
    assert first.status_code == 200
    assert second.status_code == 503 and second.json()["error"]["code"] == "AI_UNAVAILABLE"
    assert "not charged" in second.json()["error"]["message"]
    assert state["used"] == 1


async def test_secret_word_never_appears_before_the_day_ends(
    loose_api: ASGITransport,
    word_service: DailyWordService,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Play a full losing game and read every endpoint: the word must not show up anywhere."""
    caplog.set_level(logging.DEBUG)
    api = AsyncClient(transport=loose_api, base_url="http://testserver")
    await start_session(api)
    word = word_service.puzzle_for_today().word
    bodies: list[str] = []
    for n in range(10):
        r = await api.post(ASK, json={"question": f"Is it test number {n}?"}, headers=idem())
        bodies.append(r.text)
    for path in (
        "/api/v1/game/today",
        "/api/v1/leaderboard/today",
        "/api/v1/puzzles/today",
        "/api/v1/puzzles/2026-10-17/answer",
        "/api/openapi.json",
    ):
        bodies.append((await api.get(path)).text)
    await api.aclose()
    blob = "\n".join(bodies)
    assert json.loads(bodies[9])["game"]["status"] == "lost"
    assert word not in blob
    assert word not in caplog.text


async def test_turnstile_cannot_be_bypassed_by_skipping_session(
    settings: Settings, repository: SqliteWordRepository, clock: FixedClock, redis: Redis
) -> None:
    turnstile = TurnstileMock(clock)
    app = create_app(settings, clock=clock, turnstile_transport=turnstile.transport())
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client,
    ):
        for method, path, body in (
            ("GET", "/api/v1/game/today", None),
            ("POST", ASK, {"question": "Is it alive?"}),
            ("POST", "/api/v1/game/today/guesses", {"guess": "zzx"}),
        ):
            r = await client.request(method, path, json=body, headers=idem())
            assert r.status_code == 401, path
        client.cookies.set("tenq_sid", "made.up.cookie", path="/api")
        assert (await client.get("/api/v1/game/today")).status_code == 401
    assert turnstile.calls == 0


async def test_origin_secret_settings_reject_unproxied_requests(
    settings: Settings, repository: SqliteWordRepository, clock: FixedClock, redis: Redis
) -> None:
    app = create_app(
        settings.model_copy(update={"origin_secrets": SecretStr("o" * 40)}), clock=clock
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client,
    ):
        spoof = {"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "1.2.3.4"}
        assert (await client.get("/api/v1/puzzles/today", headers=spoof)).status_code == 403
        ok = await client.get("/api/v1/puzzles/today", headers={"X-Origin-Secret": "o" * 40})
        assert ok.status_code == 200
