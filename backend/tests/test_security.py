"""Phase 06 security tests: identity, proxy trust, Turnstile, and anti-abuse limits."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx2
import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient
from pydantic import SecretStr
from redis.asyncio import Redis

from app.core.client_ip import resolve_client_ip
from app.core.config import Settings
from app.core.session import COOKIE_MAX_AGE_S, COOKIE_NAME, SessionCodec
from app.integrations.ai_judge import FakeAIJudge
from app.integrations.turnstile import TurnstileOutcome, TurnstileVerifier
from app.main import create_app
from app.models.clock import FixedClock
from app.repositories.word_repository import SqliteWordRepository
from tests.conftest import TEST_SESSION_HEX, start_session
from tests.turnstile_mock import TurnstileMock

pytestmark = pytest.mark.anyio

ASK = "/api/v1/game/today/questions"
ORIGIN = "o" * 40
NOW_S = int(datetime(2026, 10, 17, 12, tzinfo=UTC).timestamp())


def idem() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid.uuid4())}


async def used(client: AsyncClient) -> int:
    return int((await client.get("/api/v1/game/today")).json()["used"])


@pytest.fixture
async def make_client(
    settings: Settings,
    repository: SqliteWordRepository,
    clock: FixedClock,
    judge: FakeAIJudge,
    redis: Redis,
    turnstile: TurnstileMock,
) -> AsyncIterator[object]:
    """Factory: clients with their own cookie jar, peer IP, and optional settings overrides."""
    apps: dict[str, FastAPI] = {}
    contexts: list[object] = []
    clients: list[AsyncClient] = []

    async def factory(ip: str = "203.0.113.10", **overrides: object) -> AsyncClient:
        key = repr(sorted(overrides.items()))
        if key not in apps:
            app = create_app(
                settings.model_copy(update=overrides),
                clock=clock,
                judge=judge,
                turnstile_transport=turnstile.transport(),
            )
            ctx = app.router.lifespan_context(app)
            await ctx.__aenter__()
            contexts.append(ctx)
            apps[key] = app
        transport = ASGITransport(app=apps[key], client=(ip, 40000))
        client = AsyncClient(transport=transport, base_url="http://testserver")
        clients.append(client)
        return client

    yield factory
    for client in clients:
        await client.aclose()
    for ctx in reversed(contexts):
        await ctx.__aexit__(None, None, None)  # type: ignore[attr-defined]


# --- cookies --------------------------------------------------------------------------


def codec() -> SessionCodec:
    return SessionCodec(bytes.fromhex(TEST_SESSION_HEX))


def test_cookie_roundtrip() -> None:
    value, player_id = codec().issue(NOW_S)
    session = codec().verify(value, NOW_S)
    assert session is not None and session.player_id == player_id and not session.needs_reissue


@pytest.mark.parametrize(
    "mutate",
    [
        lambda v: v[:-2] + ("AA" if not v.endswith("AA") else "BB"),  # forged signature
        lambda v: "A" + v[1:] if v[0] != "A" else "B" + v[1:],  # edited player id
        lambda v: v.replace(".", ".9", 1),  # edited issued_at
        lambda v: v.rsplit(".", 1)[0],  # signature removed
        lambda v: v + ".extra",
        lambda v: "x" * 300,
        lambda v: "",
    ],
)
def test_tampered_cookies_are_rejected(mutate: object) -> None:
    value, _ = codec().issue(NOW_S)
    assert codec().verify(mutate(value), NOW_S) is None  # type: ignore[operator]


def test_cookie_signed_with_another_secret_is_rejected() -> None:
    value, _ = SessionCodec(bytes(range(32))).issue(NOW_S)
    assert codec().verify(value, NOW_S) is None


def test_expired_and_future_cookies_are_rejected() -> None:
    old, _ = codec().issue(NOW_S - COOKIE_MAX_AGE_S - 1)
    future, _ = codec().issue(NOW_S + 3600)
    assert codec().verify(old, NOW_S) is None
    assert codec().verify(future, NOW_S) is None


def test_rotation_accepts_previous_secret_and_requests_reissue() -> None:
    old_secret, new_secret = bytes(range(32)), bytes(range(1, 33))
    value, player_id = SessionCodec(old_secret).issue(NOW_S)
    rotated = SessionCodec(new_secret, previous_secrets=(old_secret,))

    session = rotated.verify(value, NOW_S)
    assert session is not None and session.needs_reissue and session.player_id == player_id
    reissued, same_id = rotated.issue(session.issued_at_s, player_id=session.player_id)
    assert same_id == player_id
    assert SessionCodec(new_secret).verify(reissued, NOW_S) is not None


async def test_forged_cookie_cannot_play(make_client: object) -> None:
    client = await make_client()  # type: ignore[operator]
    client.cookies.set(COOKIE_NAME, "A" * 22 + f".{NOW_S}.forgedsignature", path="/api")
    response = await client.post(ASK, json={"question": "Is it alive?"}, headers=idem())
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SESSION_REQUIRED"


async def test_rotated_cookie_keeps_the_same_player(
    make_client: object, settings: Settings
) -> None:
    client = await make_client()  # type: ignore[operator]
    await start_session(client)
    await client.post(ASK, json={"question": "Is it alive?"}, headers=idem())
    old_cookie = client.cookies.get(COOKIE_NAME)

    new_secret = "ab" * 32
    rotated = await make_client(  # type: ignore[operator]
        session_secret=SecretStr(new_secret),
        session_secret_previous=SecretStr(TEST_SESSION_HEX),
    )
    rotated.cookies.set(COOKIE_NAME, old_cookie, path="/api")
    response = await rotated.get("/api/v1/game/today")

    assert response.json()["used"] == 1  # same player hash: state survives rotation
    assert COOKIE_NAME in response.headers["set-cookie"]  # re-signed with the new secret


async def test_deleting_the_cookie_starts_a_new_anonymous_player(make_client: object) -> None:
    client = await make_client()  # type: ignore[operator]
    await start_session(client)
    await client.post(ASK, json={"question": "Is it alive?"}, headers=idem())
    assert await used(client) == 1

    client.cookies.clear()
    assert (await client.get("/api/v1/game/today")).status_code == 401
    await start_session(client)  # needs a new Turnstile pass, counted by the IP limits
    assert await used(client) == 0  # documented limitation: no account, no device binding


# --- proxy trust ----------------------------------------------------------------------


def test_spoofed_forwarded_headers_are_ignored_without_origin_secret() -> None:
    headers = {"x-forwarded-for": "1.2.3.4", "x-real-ip": "1.2.3.4"}
    assert resolve_client_ip("198.51.100.7", headers, ()).ip == "198.51.100.7"
    wrong = {**headers, "x-origin-secret": "guess"}
    resolved = resolve_client_ip("198.51.100.7", wrong, (ORIGIN,))
    assert resolved.ip == "198.51.100.7" and not resolved.trusted_proxy


def test_forwarded_ip_used_only_behind_verified_proxy() -> None:
    headers = {"x-origin-secret": ORIGIN, "x-real-ip": "1.2.3.4", "x-forwarded-for": "5.6.7.8"}
    resolved = resolve_client_ip("10.0.0.2", headers, (ORIGIN, "p" * 40))
    assert resolved.ip == "1.2.3.4" and resolved.trusted_proxy
    garbage = {"x-origin-secret": ORIGIN, "x-real-ip": "not-an-ip"}
    assert resolve_client_ip("10.0.0.2", garbage, (ORIGIN,)).ip == "10.0.0.2"


async def test_direct_origin_access_is_refused(make_client: object) -> None:
    client = await make_client(origin_secrets=SecretStr(ORIGIN))  # type: ignore[operator]
    direct = await client.post("/api/v1/session", json={"turnstile_token": "t"})
    assert direct.status_code == 403
    assert direct.json()["error"]["code"] == "FORBIDDEN_ORIGIN"
    spoofed = await client.get(
        "/api/v1/leaderboard/today", headers={"x-origin-secret": "x" * 40, "x-real-ip": "1.1.1.1"}
    )
    assert spoofed.status_code == 403
    proxied = await client.get("/api/v1/leaderboard/today", headers={"x-origin-secret": ORIGIN})
    assert proxied.status_code == 200
    assert (await client.get("/api/v1/health")).status_code == 200  # VM health check


async def test_rotating_spoofed_ips_does_not_escape_limits(
    make_client: object, turnstile: TurnstileMock
) -> None:
    client = await make_client(session_limit_per_ip_hour=3)  # type: ignore[operator]
    statuses = []
    for n in range(5):
        client.cookies.clear()
        response = await client.post(
            "/api/v1/session",
            json={"turnstile_token": f"t{n}"},
            headers={"x-forwarded-for": f"9.9.9.{n}", "user-agent": f"bot-{n}"},
        )
        statuses.append(response.status_code)
    assert statuses == [201, 201, 201, 429, 429]
    assert turnstile.calls == 3  # limited requests never reach Cloudflare


async def test_two_players_behind_one_ip_play_independently(make_client: object) -> None:
    alice = await make_client(ip="198.51.100.20")  # type: ignore[operator]
    bob = await make_client(ip="198.51.100.20")  # type: ignore[operator]
    await start_session(alice)
    await start_session(bob)

    await alice.post(ASK, json={"question": "Is it alive?"}, headers=idem())
    await alice.post(ASK, json={"question": "Is it big?"}, headers=idem())
    await bob.post(ASK, json={"question": "Is it alive?"}, headers=idem())

    assert (await used(alice), await used(bob)) == (2, 1)


# --- Turnstile ------------------------------------------------------------------------


async def session_status(client: AsyncClient, token: str = "") -> httpx2.Response:
    return await client.post("/api/v1/session", json={"turnstile_token": token or uuid.uuid4().hex})


@pytest.mark.parametrize(
    "reply",
    [
        TurnstileMock.failure("invalid-input-response"),
        TurnstileMock.failure("timeout-or-duplicate"),
        {
            "success": True,
            "hostname": "evil.example",
            "action": "session",
            "challenge_ts": "2026-10-17T12:00:00Z",
        },
        {
            "success": True,
            "hostname": "localhost",
            "action": "other",
            "challenge_ts": "2026-10-17T12:00:00Z",
        },
        {"success": "true", "hostname": "localhost"},
    ],
)
async def test_rejected_tokens_create_no_session(
    make_client: object, turnstile: TurnstileMock, reply: dict[str, object]
) -> None:
    client = await make_client()  # type: ignore[operator]
    turnstile.queue(reply)
    response = await session_status(client)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "TURNSTILE_FAILED"
    assert "set-cookie" not in response.headers
    assert "hostname" not in response.text and "action" not in response.text  # no internals


async def test_expired_token_is_rejected(
    make_client: object, turnstile: TurnstileMock, clock: FixedClock
) -> None:
    client = await make_client()  # type: ignore[operator]
    turnstile.queue(turnstile.challenge_at(clock.now() - timedelta(seconds=301)))
    assert (await session_status(client)).status_code == 403


async def test_missing_token_is_rejected_without_calling_cloudflare(
    make_client: object, turnstile: TurnstileMock
) -> None:
    client = await make_client()  # type: ignore[operator]
    for body in ({}, {"turnstile_token": ""}):
        response = await client.post("/api/v1/session", json=body)
        assert response.status_code == 403
    assert turnstile.calls == 0


async def test_token_replay_is_rejected(make_client: object, turnstile: TurnstileMock) -> None:
    first = await make_client()  # type: ignore[operator]
    second = await make_client()  # type: ignore[operator]
    assert (await session_status(first, "same-token")).status_code == 201
    replay = await session_status(second, "same-token")
    assert replay.status_code == 403 and "set-cookie" not in replay.headers
    assert turnstile.calls == 1  # the replay never reached Cloudflare


@pytest.mark.parametrize(
    "failure",
    [
        httpx2.ConnectError("down"),
        httpx2.ReadTimeout("slow"),
        httpx2.Response(500, text="oops"),
        httpx2.Response(200, text="not json"),
        TurnstileMock.failure("internal-error"),
    ],
)
async def test_turnstile_outage_fails_closed(
    make_client: object, turnstile: TurnstileMock, failure: object
) -> None:
    client = await make_client()  # type: ignore[operator]
    turnstile.queue(failure)  # type: ignore[arg-type]
    response = await session_status(client)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert "set-cookie" not in response.headers


async def test_test_keys_rejected_when_not_allowed(clock: FixedClock) -> None:
    async def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json={
                "success": True,
                "hostname": "example.com",
                "challenge_ts": clock.now().isoformat(),
                "metadata": {"result_with_testing_key": True},
            },
        )

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http:
        strict = TurnstileVerifier(
            http,
            "real",
            allowed_hostnames=["example.com"],
            expected_action="session",
            allow_test_keys=False,
        )
        relaxed = TurnstileVerifier(
            http,
            "test",
            allowed_hostnames=["example.com"],
            expected_action="session",
            allow_test_keys=True,
        )
        assert (await strict.verify("tok", None, clock.now())).outcome is TurnstileOutcome.REJECTED
        assert (await relaxed.verify("tok", None, clock.now())).outcome is TurnstileOutcome.OK


# --- anti-abuse -----------------------------------------------------------------------


async def test_direct_backend_calls_without_session_are_refused(make_client: object) -> None:
    client = await make_client()  # type: ignore[operator]
    response = await client.post(ASK, json={"question": "Is it alive?"}, headers=idem())
    assert response.status_code == 401


async def test_question_flood_is_rate_limited_and_not_charged(make_client: object) -> None:
    client = await make_client(question_limit_per_player_minute=3)  # type: ignore[operator]
    await start_session(client)
    statuses = [
        (
            await client.post(ASK, json={"question": f"Is it number {n}?"}, headers=idem())
        ).status_code
        for n in range(6)
    ]
    assert statuses == [200, 200, 200, 429, 429, 429]
    limited = await client.post(ASK, json={"question": "Is it red?"}, headers=idem())
    assert limited.headers["retry-after"].isdigit()
    assert await used(client) == 3  # blocked requests cost nothing


async def test_read_flood_is_rate_limited(make_client: object) -> None:
    client = await make_client(read_limit_per_ip_minute=5)  # type: ignore[operator]
    statuses = [(await client.get("/api/v1/leaderboard/today")).status_code for _ in range(7)]
    assert statuses[:5] == [200] * 5 and statuses[5:] == [429, 429]


async def test_concurrency_slot_limit_returns_409(make_client: object, judge: FakeAIJudge) -> None:
    clients = [
        await make_client(ip="198.51.100.40", question_concurrency_per_ip=2)  # type: ignore[operator]
        for _ in range(3)
    ]
    for client in clients:
        await start_session(client)
    judge.gate = asyncio.Event()
    tasks = [
        asyncio.create_task(c.post(ASK, json={"question": f"Is it {n}?"}, headers=idem()))
        for n, c in enumerate(clients[:2])
    ]
    await asyncio.sleep(0.1)
    blocked = await clients[2].post(ASK, json={"question": "Is it z?"}, headers=idem())
    judge.gate.set()
    results = [await t for t in tasks]

    assert [r.status_code for r in results] == [200, 200]
    assert blocked.status_code == 409
    assert await used(clients[2]) == 0  # refused before reserve: not charged


async def test_oversized_bodies_are_rejected_and_not_charged(make_client: object) -> None:
    client = await make_client()  # type: ignore[operator]
    await start_session(client)
    big = '{"question": "' + "x" * 10_000 + '?"}'
    declared = await client.post(
        ASK, content=big, headers={**idem(), "content-type": "application/json"}
    )
    assert declared.status_code == 413
    assert declared.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"

    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(10):
            yield b"x" * 1000

    streamed = await client.post(
        ASK, content=chunks(), headers={**idem(), "content-type": "application/json"}
    )
    assert streamed.status_code == 413
    assert await used(client) == 0


async def test_unexpected_errors_reveal_no_internals(make_client: object) -> None:
    client = await make_client()  # type: ignore[operator]
    app = client._transport.app  # type: ignore[attr-defined]

    async def boom() -> None:
        raise RuntimeError("redis://:password@internal-host/0 exploded")

    app.add_api_route("/api/v1/boom", boom)
    # Like a real server: the app's 500 response is returned instead of re-raised.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as raw:
        response = await raw.get("/api/v1/boom")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "password" not in response.text and "Traceback" not in response.text
