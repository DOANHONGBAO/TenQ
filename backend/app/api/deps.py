import time
from typing import Annotated, cast

from fastapi import Depends, Request, Response

from app.core.config import Environment, Settings
from app.core.errors import SessionRequiredError
from app.core.session import COOKIE_MAX_AGE_S, COOKIE_NAME, SessionCodec
from app.services.daily_word_service import DailyWordService
from app.services.game_service import GameService


def get_daily_word_service(request: Request) -> DailyWordService:
    return cast(DailyWordService, request.app.state.daily_word_service)


def get_game_service(request: Request) -> GameService:
    return cast(GameService, request.app.state.game_service)


def _codec(request: Request) -> SessionCodec:
    return cast(SessionCodec, request.app.state.session_codec)


def optional_player(request: Request) -> str | None:
    """Player hash from a valid session cookie, or None."""
    codec = _codec(request)
    player_id = codec.verify(request.cookies.get(COOKIE_NAME))
    return None if player_id is None else codec.player_hash(player_id)


def required_player(player: Annotated[str | None, Depends(optional_player)]) -> str:
    if player is None:
        raise SessionRequiredError()
    return player


def player_or_new_session(request: Request, response: Response) -> str:
    """Reuse a valid session, or start a new anonymous one (Turnstile gate: Phase 06)."""
    existing = optional_player(request)
    if existing is not None:
        return existing
    codec = _codec(request)
    value, player_id = codec.issue(int(time.time()))
    settings = cast(Settings, request.app.state.settings)
    response.set_cookie(
        COOKIE_NAME,
        value,
        max_age=COOKIE_MAX_AGE_S,
        path="/api",
        httponly=True,
        secure=settings.env is Environment.PRODUCTION,
        samesite="lax",
    )
    return codec.player_hash(player_id)


DailyWordServiceDep = Annotated[DailyWordService, Depends(get_daily_word_service)]
GameServiceDep = Annotated[GameService, Depends(get_game_service)]
OptionalPlayer = Annotated[str | None, Depends(optional_player)]
RequiredPlayer = Annotated[str, Depends(required_player)]
PlayerOrNew = Annotated[str, Depends(player_or_new_session)]
