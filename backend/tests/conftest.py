import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import ASGITransport, AsyncClient
from pydantic import SecretStr
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Environment, Settings
from app.integrations.ai_judge import FakeAIJudge
from app.main import create_app
from app.models.clock import FixedClock
from app.models.daily_game import DailyGameConfig
from app.models.game import MAX_QUESTIONS
from app.models.word import WordEntry
from app.repositories.database import apply_migrations
from app.repositories.game_store import RedisGameStore
from app.repositories.word_repository import SqliteWordRepository
from app.scripts.seed_words import dev_entries
from app.services.daily_word_service import DailyWordService
from app.services.game_service import GameService

# Fixed, obviously non-production key: tests must be deterministic and never need a real secret.
TEST_KEY_HEX = "00112233445566778899aabbccddeeff" * 2
TEST_KEY = bytes.fromhex(TEST_KEY_HEX)
TEST_SESSION_HEX = "ffeeddccbbaa99887766554433221100" * 2
# A dedicated database on a throwaway Redis (see README). It is flushed before every test.
TEST_REDIS_URL = os.environ.get("TENQ_TEST_REDIS_URL", "redis://127.0.0.1:6390/15")
LEASE_MS = 30_000
JUDGE_TIMEOUT_S = 5.0


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "tenq.sqlite3"
    apply_migrations(path)
    return path


@pytest.fixture
def words() -> list[WordEntry]:
    return dev_entries(DailyGameConfig().word_count)


@pytest.fixture
def repository(db_path: Path, words: list[WordEntry]) -> SqliteWordRepository:
    repo = SqliteWordRepository(db_path)
    repo.replace_words(words)
    return repo


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 10, 17, 12, 0, tzinfo=UTC))


@pytest.fixture
def settings(db_path: Path) -> Settings:
    # _env_file=None keeps a developer's local .env from leaking into tests.
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        env=Environment.TEST,
        database_path=db_path,
        word_selection_key=SecretStr(TEST_KEY_HEX),
        session_secret=SecretStr(TEST_SESSION_HEX),
        redis_url=SecretStr(TEST_REDIS_URL),
    )


@pytest.fixture
def client(
    settings: Settings, repository: SqliteWordRepository, clock: FixedClock
) -> Iterator[TestClient]:
    with TestClient(create_app(settings, clock=clock)) as test_client:
        yield test_client


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client = Redis.from_url(TEST_REDIS_URL, decode_responses=True, socket_connect_timeout=1)
    try:
        await client.ping()
    except RedisError:
        await client.aclose()
        pytest.skip(f"no test Redis at {TEST_REDIS_URL} (see README: Redis for tests)")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture
def judge() -> FakeAIJudge:
    return FakeAIJudge()


@pytest.fixture
def word_service(repository: SqliteWordRepository, clock: FixedClock) -> DailyWordService:
    return DailyWordService(repository=repository, clock=clock, selection_key=TEST_KEY)


@pytest.fixture
def store(redis: Redis) -> RedisGameStore:
    return RedisGameStore(redis, MAX_QUESTIONS)


@pytest.fixture
def game_service(
    store: RedisGameStore,
    word_service: DailyWordService,
    judge: FakeAIJudge,
    clock: FixedClock,
) -> GameService:
    return GameService(
        store=store,
        words=word_service,
        judge=judge,
        clock=clock,
        lease_ms=LEASE_MS,
        judge_timeout_s=JUDGE_TIMEOUT_S,
    )


@pytest.fixture
async def api(
    settings: Settings,
    repository: SqliteWordRepository,
    clock: FixedClock,
    judge: FakeAIJudge,
    redis: Redis,
) -> AsyncIterator[AsyncClient]:
    """Async HTTP client against the real app (lifespan included), Redis, and the fake judge."""
    app: FastAPI = create_app(settings, clock=clock, judge=judge)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client
