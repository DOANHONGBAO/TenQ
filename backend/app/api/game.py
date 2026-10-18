import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Query, Response

from app.api.deps import (
    GameServiceDep,
    NamePlayer,
    OptionalPlayer,
    QuestionPlayer,
    ReadLimited,
    RequiredPlayer,
)
from app.core.errors import BadRequestError
from app.schemas.game import (
    AskRequest,
    AskResponse,
    GameStateOut,
    GuessRequest,
    LeaderboardOut,
    PlayerNameOut,
    PlayerNameRequest,
)

router = APIRouter(tags=["game"])


def _check_idempotency_key(value: str | None) -> str:
    try:
        parsed = uuid.UUID(value or "")
    except ValueError:
        raise BadRequestError("Idempotency-Key must be a UUID v4.") from None
    if parsed.version != 4:
        raise BadRequestError("Idempotency-Key must be a UUID v4.")
    return str(parsed)


@router.get("/game/today", response_model=GameStateOut, dependencies=[ReadLimited])
async def get_game(
    service: GameServiceDep, player: RequiredPlayer, response: Response
) -> GameStateOut:
    """The caller's state for the current UTC day (session required: POST /session)."""
    response.headers["Cache-Control"] = "no-store"
    state = await service.state(player)
    return GameStateOut.build(state, service.now())


@router.post("/game/today/questions", response_model=AskResponse)
async def ask_question(
    body: AskRequest,
    service: GameServiceDep,
    player: QuestionPlayer,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AskResponse:
    key = _check_idempotency_key(idempotency_key)
    result = await service.ask(player, body.question, key)
    response.headers["Cache-Control"] = "no-store"
    if result.replayed:
        response.headers["Idempotent-Replayed"] = "true"
    return AskResponse(
        number=result.number,
        answer=result.answer,
        game=GameStateOut.build(result.game, service.now()),
    )


@router.post("/game/today/guesses", response_model=AskResponse)
async def guess_word(
    body: GuessRequest,
    service: GameServiceDep,
    player: QuestionPlayer,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AskResponse:
    """Guess the word directly. Costs one of the 10 attempts; correct = WIN, wrong = NO."""
    key = _check_idempotency_key(idempotency_key)
    result = await service.guess(player, body.guess, key)
    response.headers["Cache-Control"] = "no-store"
    if result.replayed:
        response.headers["Idempotent-Replayed"] = "true"
    return AskResponse(
        number=result.number,
        answer=result.answer,
        game=GameStateOut.build(result.game, service.now()),
    )


@router.get("/leaderboard/today", response_model=LeaderboardOut, dependencies=[ReadLimited])
async def leaderboard_today(
    service: GameServiceDep,
    player: OptionalPlayer,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> LeaderboardOut:
    response.headers["Cache-Control"] = "no-store"
    return LeaderboardOut.build(await service.leaderboard(limit, player))


@router.post("/players/me/name", response_model=PlayerNameOut)
async def set_player_name(
    body: PlayerNameRequest, service: GameServiceDep, player: NamePlayer, response: Response
) -> PlayerNameOut:
    """Today's winner chooses the name shown on the leaderboard (kept for later days)."""
    response.headers["Cache-Control"] = "no-store"
    return PlayerNameOut(display_name=await service.set_name(player, body.name))
