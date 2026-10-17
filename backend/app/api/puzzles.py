from datetime import date

from fastapi import APIRouter, Response
from starlette.concurrency import run_in_threadpool

from app.api.deps import DailyWordServiceDep
from app.schemas.puzzle import PuzzleAnswerResponse, PuzzleTodayResponse

router = APIRouter(prefix="/puzzles", tags=["puzzles"])


@router.get("/today", response_model=PuzzleTodayResponse)
async def puzzle_today(service: DailyWordServiceDep, response: Response) -> PuzzleTodayResponse:
    """Today's UTC game date and reset time. Pins today's word server-side; never returns it."""
    await run_in_threadpool(service.puzzle_for_today)
    response.headers["Cache-Control"] = "no-store"
    return PuzzleTodayResponse(
        game_date=service.current_game_date(),
        server_time=service.now(),
        next_reset_at=service.next_reset_at(),
    )


@router.get("/{game_date}/answer", response_model=PuzzleAnswerResponse)
async def puzzle_answer(
    game_date: date, service: DailyWordServiceDep, response: Response
) -> PuzzleAnswerResponse:
    """The word of a past UTC game date. Today and future dates return 403."""
    word = await run_in_threadpool(service.revealed_word, game_date)
    response.headers["Cache-Control"] = "public, max-age=86400"
    return PuzzleAnswerResponse(game_date=game_date, word=word)
