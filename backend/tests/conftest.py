from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Environment, Settings
from app.main import create_app
from app.models.clock import FixedClock
from app.models.daily_game import DailyGameConfig
from app.models.word import WordEntry
from app.repositories.database import apply_migrations
from app.repositories.word_repository import SqliteWordRepository
from app.scripts.seed_words import dev_entries

# Fixed, obviously non-production key: tests must be deterministic and never need a real secret.
TEST_KEY_HEX = "00112233445566778899aabbccddeeff" * 2
TEST_KEY = bytes.fromhex(TEST_KEY_HEX)


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
    )


@pytest.fixture
def client(
    settings: Settings, repository: SqliteWordRepository, clock: FixedClock
) -> Iterator[TestClient]:
    with TestClient(create_app(settings, clock=clock)) as test_client:
        yield test_client
