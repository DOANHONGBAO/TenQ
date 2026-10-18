"""Leaderboard names chosen by winners (OQ-07, owner request 2026-10-18)."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx2 import AsyncClient

from app.core.errors import InvalidPlayerNameAppError, NotAWinnerError
from app.models.clock import FixedClock
from app.models.player_name import InvalidPlayerNameError, normalize_player_name
from app.repositories.database import apply_migrations
from app.repositories.game_store import RedisGameStore
from app.repositories.player_name_repository import SqlitePlayerNameRepository
from app.services.daily_word_service import DailyWordService
from app.services.game_service import GameService
from tests.conftest import JUDGE_TIMEOUT_S, LEASE_MS, FakeAIJudge, start_session

WINNER = "a" * 32
OTHER = "b" * 32


def key() -> str:
    return str(uuid.uuid4())


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Trang", "Trang"),
        ("  Nguyễn   Văn A ", "Nguyễn Văn A"),
        ("Nguyễn", "Nguyễn"),  # decomposed input is composed by NFC
        ("o'brien_2", "o'brien_2"),
        ("Zoë-Ann", "Zoë-Ann"),
        ("tab\there", "tab here"),  # any whitespace becomes one space
    ],
)
def test_valid_names_are_normalized(raw: str, expected: str) -> None:
    assert normalize_player_name(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "a",  # too short
        "x" * 21,  # too long
        "1234",  # no letter
        "<script>",
        "Bob!",
        "visit www.spam",
        "spam.com",
        "me@mail",
        "https evil",
        "Za̶̶̶lgo",  # stacked combining marks
        "nul\x00name",
        "emoji 😀",
    ],
)
def test_invalid_names_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidPlayerNameError):
        normalize_player_name(raw)


def test_repository_upserts_and_looks_up(tmp_path: Path) -> None:
    db = tmp_path / "names.sqlite3"
    apply_migrations(db)
    repo = SqlitePlayerNameRepository(db)
    at = datetime(2026, 10, 18, tzinfo=UTC)

    repo.set_name(WINNER, "First", at)
    repo.set_name(WINNER, "Second", at)

    assert repo.names_for([WINNER, OTHER, WINNER]) == {WINNER: "Second"}
    assert repo.names_for([]) == {}


@pytest.fixture
def named_service(
    store: RedisGameStore,
    word_service: DailyWordService,
    judge: FakeAIJudge,
    clock: FixedClock,
    db_path: Path,
) -> GameService:
    return GameService(
        store=store,
        words=word_service,
        judge=judge,
        clock=clock,
        lease_ms=LEASE_MS,
        judge_timeout_s=JUDGE_TIMEOUT_S,
        names=SqlitePlayerNameRepository(db_path),
    )


@pytest.mark.anyio
async def test_only_todays_winner_can_choose_a_name(
    named_service: GameService, word_service: DailyWordService
) -> None:
    with pytest.raises(NotAWinnerError):
        await named_service.set_name(WINNER, "Early Bird")

    await named_service.guess(WINNER, word_service.puzzle_for_today().word, key())

    assert await named_service.set_name(WINNER, " Trang ") == "Trang"
    board = await named_service.leaderboard(10, WINNER)
    assert board.entries[0].display_name == "Trang"
    assert board.me is not None and board.me.display_name == "Trang"


@pytest.mark.anyio
async def test_invalid_name_is_rejected_before_the_game_check(named_service: GameService) -> None:
    with pytest.raises(InvalidPlayerNameAppError):
        await named_service.set_name(WINNER, "<b>")


@pytest.mark.anyio
async def test_name_endpoint(api: AsyncClient, word_service: DailyWordService) -> None:
    await start_session(api)
    early = await api.post("/api/v1/players/me/name", json={"name": "Trang"})
    assert early.status_code == 409 and early.json()["error"]["code"] == "NOT_A_WINNER"

    word = word_service.puzzle_for_today().word
    won = await api.post(
        "/api/v1/game/today/guesses", json={"guess": word}, headers={"Idempotency-Key": key()}
    )
    assert won.json()["answer"] == "WIN"

    bad = await api.post("/api/v1/players/me/name", json={"name": "x"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_NAME"
    extra = await api.post("/api/v1/players/me/name", json={"name": "Trang", "rank": 1})
    assert extra.status_code == 422

    ok = await api.post("/api/v1/players/me/name", json={"name": "Nguyễn Trang"})
    assert ok.status_code == 200 and ok.json() == {"display_name": "Nguyễn Trang"}
    board = (await api.get("/api/v1/leaderboard/today")).json()
    assert board["entries"][0]["display_name"] == "Nguyễn Trang"
    assert board["me"]["display_name"] == "Nguyễn Trang"


@pytest.mark.anyio
async def test_name_endpoint_requires_a_session(api: AsyncClient) -> None:
    response = await api.post("/api/v1/players/me/name", json={"name": "Trang"})
    assert response.status_code == 401
