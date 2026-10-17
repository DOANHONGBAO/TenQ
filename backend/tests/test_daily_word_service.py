import logging
import threading
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.errors import AnswerNotAvailableError, NotFoundError, ServiceUnavailableError
from app.models.clock import FixedClock
from app.models.word import WordEntry
from app.models.word_schedule import word_index_for
from app.repositories.word_repository import SqliteWordRepository
from app.scripts.seed_words import dev_entries
from app.services.daily_word_service import DailyWordService
from tests.conftest import TEST_KEY


def make_service(repo: SqliteWordRepository, clock: FixedClock) -> DailyWordService:
    return DailyWordService(repository=repo, clock=clock, selection_key=TEST_KEY)


def at(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)  # type: ignore[misc]


def test_word_matches_keyed_schedule(repository: SqliteWordRepository) -> None:
    service = make_service(repository, FixedClock(at(2026, 10, 17, 9)))
    words = repository.list_words()

    puzzle = service.puzzle_for_today()

    assert puzzle.game_date == date(2026, 10, 17)
    assert puzzle.word == words[word_index_for(TEST_KEY, date(2026, 10, 17))]


def test_same_word_all_day_and_new_word_at_midnight(repository: SqliteWordRepository) -> None:
    clock = FixedClock(at(2026, 10, 17, 0, 0, 0))
    service = make_service(repository, clock)
    first = service.puzzle_for_today().word

    clock.set(at(2026, 10, 17, 23, 59, 59))
    assert service.puzzle_for_today().word == first

    clock.set(at(2026, 10, 18, 0, 0, 0))
    assert service.puzzle_for_today().game_date == date(2026, 10, 18)
    assert service.puzzle_for_today().word != first


def test_restart_keeps_the_word(repository: SqliteWordRepository, db_path: Path) -> None:
    clock = FixedClock(at(2026, 10, 17, 8))
    before = make_service(repository, clock).puzzle_for_today()

    # A new process: fresh repository object, fresh service, empty in-memory cache.
    after = make_service(SqliteWordRepository(db_path), clock).puzzle_for_today()

    assert after == before


def test_pinned_word_survives_word_list_change(repository: SqliteWordRepository) -> None:
    clock = FixedClock(at(2026, 10, 17, 8))
    pinned = make_service(repository, clock).puzzle_for_today()

    replacement = [
        WordEntry(
            e.word.replace("zzdev", "zznew"),
            e.part_of_speech,
            e.category,
            e.definition,
            e.attributes,
        )
        for e in dev_entries(365)
    ]
    repository.replace_words(replacement)

    assert make_service(repository, clock).puzzle_for_today().word == pinned.word
    # The next, unpinned day uses the new list.
    clock.set(at(2026, 10, 18, 8))
    assert make_service(repository, clock).puzzle_for_today().word.startswith("zznew")


def test_players_in_different_timezones_get_the_same_word(
    repository: SqliteWordRepository,
) -> None:
    instant = at(2026, 10, 17, 23, 30)
    words = set()
    for hours in (-10, -3, 0, 5, 7, 12, 14):
        local_view = instant.astimezone(timezone(timedelta(hours=hours)))
        words.add(make_service(repository, FixedClock(local_view)).puzzle_for_today().word)
    assert len(words) == 1


def test_concurrent_first_requests_pin_one_word(repository: SqliteWordRepository) -> None:
    clock = FixedClock(at(2026, 10, 17, 0, 0, 1))
    results: list[str] = []

    def work() -> None:
        results.append(make_service(repository, clock).puzzle_for_today().word)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(set(results)) == 1


def test_revealed_word_only_for_past_days(repository: SqliteWordRepository) -> None:
    clock = FixedClock(at(2026, 10, 17, 12))
    service = make_service(repository, clock)
    word = service.puzzle_for_today().word

    with pytest.raises(AnswerNotAvailableError):
        service.revealed_word(date(2026, 10, 17))
    with pytest.raises(AnswerNotAvailableError):
        service.revealed_word(date(2026, 10, 18))

    clock.set(at(2026, 10, 18, 0, 0, 0))
    assert service.revealed_word(date(2026, 10, 17)) == word
    with pytest.raises(NotFoundError):
        service.revealed_word(date(2026, 10, 1))


def test_unseeded_database_is_unavailable(db_path: Path) -> None:
    service = make_service(SqliteWordRepository(db_path), FixedClock(at(2026, 10, 17, 12)))
    with pytest.raises(ServiceUnavailableError):
        service.puzzle_for_today()


def test_logs_and_repr_never_contain_the_word(
    repository: SqliteWordRepository, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    service = make_service(repository, FixedClock(at(2026, 10, 17, 12)))

    puzzle = service.puzzle_for_today()

    assert puzzle.word not in caplog.text
    assert puzzle.word not in repr(puzzle)
    assert "puzzle pinned for 2026-10-17" in caplog.text


def test_rejects_short_key(repository: SqliteWordRepository) -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        DailyWordService(repository, FixedClock(at(2026, 1, 1)), selection_key=b"short")
