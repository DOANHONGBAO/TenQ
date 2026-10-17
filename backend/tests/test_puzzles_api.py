import logging
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.models.clock import FixedClock
from app.repositories.word_repository import SqliteWordRepository


def todays_word(repository: SqliteWordRepository) -> str:
    puzzle = repository.get_pinned(datetime(2026, 10, 17, tzinfo=UTC).date())
    assert puzzle is not None
    return puzzle.word


def test_today_returns_dates_but_never_the_word(
    client: TestClient, repository: SqliteWordRepository, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    response = client.get("/api/v1/puzzles/today")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "game_date": "2026-10-17",
        "server_time": "2026-10-17T12:00:00.000Z",
        "next_reset_at": "2026-10-18T00:00:00.000Z",
    }
    word = todays_word(repository)
    assert word not in response.text
    assert word not in caplog.text


def test_openapi_schema_has_no_word_field_for_today(client: TestClient) -> None:
    schema = client.get("/api/openapi.json").json()
    today = schema["components"]["schemas"]["PuzzleTodayResponse"]["properties"]
    assert set(today) == {"game_date", "server_time", "next_reset_at"}


def test_answer_for_today_is_forbidden(
    client: TestClient, repository: SqliteWordRepository
) -> None:
    client.get("/api/v1/puzzles/today")

    response = client.get("/api/v1/puzzles/2026-10-17/answer")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ANSWER_NOT_AVAILABLE"
    assert todays_word(repository) not in response.text


def test_answer_for_future_is_forbidden(client: TestClient) -> None:
    response = client.get("/api/v1/puzzles/2027-01-01/answer")
    assert response.status_code == 403


def test_answer_for_past_day_after_midnight(
    client: TestClient, repository: SqliteWordRepository, clock: FixedClock
) -> None:
    client.get("/api/v1/puzzles/today")
    word = todays_word(repository)

    clock.set(datetime(2026, 10, 18, 0, 0, 0, tzinfo=UTC))
    response = client.get("/api/v1/puzzles/2026-10-17/answer")

    assert response.status_code == 200
    assert response.json() == {"game_date": "2026-10-17", "word": word}
    assert response.headers["cache-control"] == "public, max-age=86400"


def test_answer_for_unplayed_past_day_is_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/puzzles/2026-01-01/answer")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_invalid_date_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/puzzles/not-a-date/answer")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
