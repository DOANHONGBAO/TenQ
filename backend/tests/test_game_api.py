"""HTTP contract for the game endpoints, with real Redis and the fake judge."""

import asyncio
import uuid

import pytest
from httpx2 import AsyncClient

from app.core.session import COOKIE_NAME
from app.integrations.ai_judge import FakeAIJudge
from app.services.daily_word_service import DailyWordService
from tests.conftest import start_session

pytestmark = pytest.mark.anyio

ASK = "/api/v1/game/today/questions"


def idem() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid.uuid4())}


async def start(api: AsyncClient) -> None:
    await start_session(api)


async def test_session_then_game_state(api: AsyncClient) -> None:
    response = await api.post("/api/v1/session", json={"turnstile_token": "t-1"})

    assert response.status_code == 201
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE_NAME}=")
    assert "HttpOnly" in cookie and "Path=/api" in cookie and "samesite=lax" in cookie.lower()
    assert "Secure" not in cookie  # local/test only; production adds Secure
    assert response.json()["display_name"].startswith("Player-")
    body = (await api.get("/api/v1/game/today")).json()
    assert body["status"] == "not_started"
    assert (body["used"], body["remaining"], body["max_questions"]) == (0, 10, 10)
    assert body["next_reset_at"] == "2026-10-18T00:00:00.000Z"

    again = await api.post("/api/v1/session", json={"turnstile_token": "t-2"})
    assert again.status_code == 200 and "set-cookie" not in again.headers


async def test_game_state_requires_session(api: AsyncClient) -> None:
    response = await api.get("/api/v1/game/today")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SESSION_REQUIRED"


async def test_ask_requires_session(api: AsyncClient) -> None:
    response = await api.post(ASK, json={"question": "Is it alive?"}, headers=idem())
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SESSION_REQUIRED"


async def test_forged_cookie_is_not_a_session(api: AsyncClient) -> None:
    api.cookies.set(COOKIE_NAME, "abc.123.forged", path="/api")
    response = await api.post(ASK, json={"question": "Is it alive?"}, headers=idem())
    assert response.status_code == 401


async def test_ask_and_replay(api: AsyncClient, judge: FakeAIJudge) -> None:
    await start(api)
    headers = idem()

    first = await api.post(ASK, json={"question": "Is it alive?"}, headers=headers)
    replay = await api.post(ASK, json={"question": "Is it alive?"}, headers=headers)

    assert first.status_code == 200 and replay.status_code == 200
    assert first.json()["number"] == 1 and first.json()["answer"] == "NO"
    assert first.json()["game"]["used"] == 1
    assert replay.headers["idempotent-replayed"] == "true"
    assert replay.json()["number"] == 1 and replay.json()["game"]["used"] == 1
    assert judge.calls == 1


@pytest.mark.parametrize(
    "tampered",
    [
        {"question": "Is it alive?", "remaining": 99},
        {"question": "Is it alive?", "used": 0},
        {"question": "Is it alive?", "status": "won"},
        {"question": "Is it alive?", "game_date": "2026-10-16"},
        {"question": "Is it alive?", "started_at": "2026-10-17T00:00:00Z"},
    ],
)
async def test_client_cannot_change_attempts_or_state(
    api: AsyncClient, tampered: dict[str, object]
) -> None:
    await start(api)
    response = await api.post(ASK, json=tampered, headers=idem())

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert (await api.get("/api/v1/game/today")).json()["used"] == 0


@pytest.mark.parametrize("header", [None, "not-a-uuid", "6ba7b810-9dad-11d1-80b4-00c04fd430c8"])
async def test_idempotency_key_must_be_uuid4(api: AsyncClient, header: str | None) -> None:
    await start(api)
    headers = {} if header is None else {"Idempotency-Key": header}
    response = await api.post(ASK, json={"question": "Is it alive?"}, headers=headers)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BAD_REQUEST"


async def test_invalid_question_has_reason(api: AsyncClient) -> None:
    await start(api)
    response = await api.post(ASK, json={"question": "Is it alive"}, headers=idem())
    assert response.status_code == 422
    assert response.json()["error"]["details"] == {"reason": "not_a_question"}


async def test_concurrent_http_requests_charge_once(api: AsyncClient, judge: FakeAIJudge) -> None:
    await start(api)
    judge.gate = asyncio.Event()

    async def ask(text: str) -> int:
        response = await api.post(ASK, json={"question": text}, headers=idem())
        return response.status_code

    first = asyncio.create_task(ask("Is it alive?"))
    await asyncio.sleep(0.05)
    second = await ask("Is it big?")
    judge.gate.set()

    assert (await first, second) == (200, 409)
    assert (await api.get("/api/v1/game/today")).json()["used"] == 1


async def test_ai_unavailable_sets_retry_after(api: AsyncClient, judge: FakeAIJudge) -> None:
    from app.integrations.ai_judge import AIJudgeError

    await start(api)
    judge.queue(AIJudgeError("down"))
    response = await api.post(ASK, json={"question": "Is it alive?"}, headers=idem())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AI_UNAVAILABLE"
    assert response.headers["retry-after"] == "5"


async def test_win_flow_and_leaderboard(api: AsyncClient, word_service: DailyWordService) -> None:
    await start(api)
    word = word_service.puzzle_for_today().word
    await api.post(ASK, json={"question": "Is it alive?"}, headers=idem())

    win = await api.post(ASK, json={"question": f"Is it a {word}?"}, headers=idem())
    assert win.json()["answer"] == "WIN"
    assert win.json()["game"]["status"] == "won"
    assert word not in (await api.get("/api/v1/game/today")).text.replace(f"Is it a {word}?", "")

    board = (await api.get("/api/v1/leaderboard/today")).json()
    assert board["total_winners"] == 1
    entry = board["entries"][0]
    assert set(entry) == {"rank", "display_name", "questions", "duration_ms"}
    assert entry["display_name"].startswith("Player-") and entry["questions"] == 2
    assert board["me"]["rank"] == 1

    finished = await api.post(ASK, json={"question": "Is it red?"}, headers=idem())
    assert finished.status_code == 409
    assert finished.json()["error"]["code"] == "GAME_FINISHED"


async def test_leaderboard_without_session(api: AsyncClient) -> None:
    response = await api.get("/api/v1/leaderboard/today?limit=5")
    assert response.status_code == 200
    assert response.json() == {
        "game_date": "2026-10-17",
        "entries": [],
        "me": None,
        "total_winners": 0,
    }
    assert (await api.get("/api/v1/leaderboard/today?limit=0")).status_code == 422
