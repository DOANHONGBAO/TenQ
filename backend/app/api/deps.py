"""FastAPI dependencies: services, client context, session, and rate limits."""

import contextlib
from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request, Response
from redis.exceptions import RedisError

from app.core.client_ip import resolve_client_ip
from app.core.config import Environment, Settings
from app.core.errors import (
    QuestionInProgressError,
    RateLimitedError,
    ServiceUnavailableError,
    SessionRequiredError,
)
from app.core.session import COOKIE_MAX_AGE_S, COOKIE_NAME, Identifiers, SessionCodec
from app.models.clock import Clock
from app.repositories.abuse_store import AbuseStore
from app.services.daily_word_service import DailyWordService
from app.services.game_service import GameService
from app.services.session_service import ClientContext, SessionService


def _state(request: Request, name: str) -> object:
    return getattr(request.app.state, name)


def get_settings_dep(request: Request) -> Settings:
    return cast(Settings, _state(request, "settings"))


def get_daily_word_service(request: Request) -> DailyWordService:
    return cast(DailyWordService, _state(request, "daily_word_service"))


def get_game_service(request: Request) -> GameService:
    return cast(GameService, _state(request, "game_service"))


def get_session_service(request: Request) -> SessionService:
    return cast(SessionService, _state(request, "session_service"))


def client_context(request: Request) -> ClientContext:
    settings = get_settings_dep(request)
    clock = cast(Clock, _state(request, "clock"))
    ids = cast(Identifiers, _state(request, "identifiers"))
    headers = {k.lower(): v for k, v in request.headers.items()}
    client = resolve_client_ip(
        request.client.host if request.client else None, headers, settings.origin_secret_list
    )
    day = clock.now().date()
    ip_hash = ids.ip_hash(client.ip, day)
    return ClientContext(
        ip=client.ip,
        ip_hash=ip_hash,
        device_hash=ip_hash + ids.ua_hash(headers.get("user-agent", ""), day),
        trusted_proxy=client.trusted_proxy,
    )


def set_session_cookie(response: Response, settings: Settings, value: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        value,
        max_age=COOKIE_MAX_AGE_S,
        path="/api",
        httponly=True,
        secure=settings.env is Environment.PRODUCTION,
        samesite="lax",
    )


def optional_player(request: Request, response: Response) -> str | None:
    """Player hash from a valid session cookie, or None. Re-signs cookies after rotation."""
    codec = cast(SessionCodec, _state(request, "session_codec"))
    clock = cast(Clock, _state(request, "clock"))
    session = codec.verify(request.cookies.get(COOKIE_NAME), int(clock.now().timestamp()))
    if session is None:
        return None
    if session.needs_reissue:
        value, _ = codec.issue(session.issued_at_s, player_id=session.player_id)
        set_session_cookie(response, get_settings_dep(request), value)
    ids = cast(Identifiers, _state(request, "identifiers"))
    return ids.player_hash(session.player_id)


def required_player(player: Annotated[str | None, Depends(optional_player)]) -> str:
    if player is None:
        raise SessionRequiredError()
    return player


async def _limit(request: Request, scope: str, subject: str, limit: int, window_s: int) -> None:
    abuse = cast(AbuseStore, _state(request, "abuse_store"))
    clock = cast(Clock, _state(request, "clock"))
    try:
        decision = await abuse.hit(scope, subject, limit, window_s, int(clock.now().timestamp()))
    except RedisError as exc:
        raise ServiceUnavailableError() from exc
    if not decision.allowed:
        raise RateLimitedError(decision.retry_after_s)


async def read_rate_limit(
    request: Request, client: Annotated[ClientContext, Depends(client_context)]
) -> None:
    settings = get_settings_dep(request)
    await _limit(request, "read-ip", client.ip_hash, settings.read_limit_per_ip_minute, 60)


async def question_guard(
    request: Request,
    client: Annotated[ClientContext, Depends(client_context)],
    player: Annotated[str, Depends(required_player)],
) -> AsyncIterator[str]:
    """Rate limits and a per-IP concurrency slot, all checked before anything is charged."""
    settings = get_settings_dep(request)
    await _limit(request, "ask-player", player, settings.question_limit_per_player_minute, 60)
    await _limit(request, "ask-ip", client.ip_hash, settings.question_limit_per_ip_minute, 60)
    abuse = cast(AbuseStore, _state(request, "abuse_store"))
    try:
        acquired = await abuse.acquire_slot(
            "ask-ip", client.ip_hash, settings.question_concurrency_per_ip, ttl_s=60
        )
    except RedisError as exc:
        raise ServiceUnavailableError() from exc
    if not acquired:
        raise QuestionInProgressError("Too many questions in flight from this network.")
    try:
        yield player
    finally:
        with contextlib.suppress(RedisError):  # the slot expires on its own
            await abuse.release_slot("ask-ip", client.ip_hash)


DailyWordServiceDep = Annotated[DailyWordService, Depends(get_daily_word_service)]
GameServiceDep = Annotated[GameService, Depends(get_game_service)]
SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
ClientDep = Annotated[ClientContext, Depends(client_context)]
OptionalPlayer = Annotated[str | None, Depends(optional_player)]
RequiredPlayer = Annotated[str, Depends(required_player)]
QuestionPlayer = Annotated[str, Depends(question_guard)]
ReadLimited = Depends(read_rate_limit)
