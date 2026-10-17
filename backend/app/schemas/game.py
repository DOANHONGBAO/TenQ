"""API contract models for the game (docs/api-contract.md sections 3 and 4)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.clock import next_reset_at
from app.models.game import (
    Answer,
    AttemptKind,
    GameState,
    GameStatus,
    Leaderboard,
    LeaderboardEntry,
)
from app.models.hints import HINT_COUNT, HINT_EVERY
from app.schemas.common import UtcTimestamp


class AskRequest(BaseModel):
    """Only the question text. Any other field (attempts, status, timing) is rejected."""

    model_config = ConfigDict(extra="forbid")

    # Hard upper bound before validation so huge payloads are rejected cheaply.
    question: str = Field(max_length=1000)


class GuessRequest(BaseModel):
    """Only the guessed word. Any other field is rejected."""

    model_config = ConfigDict(extra="forbid")

    guess: str = Field(max_length=100)


class HistoryEntryOut(BaseModel):
    number: int
    question: str  # the question text, or the guessed word for kind == "guess"
    answer: Answer
    asked_at: UtcTimestamp
    kind: AttemptKind


class GameStateOut(BaseModel):
    game_date: date
    status: GameStatus
    max_questions: Literal[10] = 10
    used: int
    remaining: int
    in_progress: bool
    history: list[HistoryEntryOut]
    started_at: UtcTimestamp | None
    finished_at: UtcTimestamp | None
    duration_ms: int | None
    hints: list[str]
    hints_total: int
    # Attempts until the next hint unlocks; null when all hints are shown or the game is over.
    next_hint_in: int | None
    server_time: UtcTimestamp
    next_reset_at: UtcTimestamp

    @classmethod
    def build(cls, state: GameState, now: UtcTimestamp) -> "GameStateOut":
        return cls(
            game_date=state.game_date,
            status=state.status,
            used=state.used,
            remaining=state.remaining,
            in_progress=state.in_progress,
            history=[
                HistoryEntryOut(
                    number=h.number,
                    question=h.question,
                    answer=h.answer,
                    asked_at=h.asked_at,
                    kind=h.kind,
                )
                for h in state.history
            ],
            started_at=state.started_at,
            finished_at=state.finished_at,
            duration_ms=state.duration_ms,
            hints=list(state.hints),
            hints_total=HINT_COUNT,
            next_hint_in=_next_hint_in(state),
            server_time=now,
            next_reset_at=next_reset_at(now),
        )


class AskResponse(BaseModel):
    number: int
    answer: Answer
    game: GameStateOut


class LeaderboardEntryOut(BaseModel):
    rank: int
    display_name: str
    questions: int
    duration_ms: int

    @classmethod
    def build(cls, entry: LeaderboardEntry) -> "LeaderboardEntryOut":
        return cls(
            rank=entry.rank,
            display_name=entry.display_name,
            questions=entry.questions,
            duration_ms=entry.duration_ms,
        )


class LeaderboardMeOut(BaseModel):
    rank: int
    questions: int
    duration_ms: int


class LeaderboardOut(BaseModel):
    game_date: date
    entries: list[LeaderboardEntryOut]
    me: LeaderboardMeOut | None
    total_winners: int

    @classmethod
    def build(cls, board: Leaderboard) -> "LeaderboardOut":
        me = None
        if board.me is not None:
            me = LeaderboardMeOut(
                rank=board.me.rank, questions=board.me.questions, duration_ms=board.me.duration_ms
            )
        return cls(
            game_date=board.game_date,
            entries=[LeaderboardEntryOut.build(e) for e in board.entries],
            me=me,
            total_winners=board.total_winners,
        )


def _next_hint_in(state: GameState) -> int | None:
    if state.status.is_finished or len(state.hints) >= HINT_COUNT:
        return None
    return HINT_EVERY - state.used % HINT_EVERY
