"""Game state machine for one player and one UTC game day.

    NOT_STARTED --question--> IN_PROGRESS --WIN--> WON
         |                        |
         +----WIN (1st question)--+--10th question without WIN--> LOST

Every judged question costs exactly one of the 10 attempts, including the winning one
(BR-08). WON and LOST are terminal. The authoritative copy of this state lives in Redis and
is changed only by the Lua scripts in repositories/game_store.py; this module describes the
same rules in Python for the API layer and for tests.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

MAX_QUESTIONS = 10


class GameStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    WON = "won"
    LOST = "lost"

    @property
    def is_finished(self) -> bool:
        return self in (GameStatus.WON, GameStatus.LOST)


class Answer(StrEnum):
    YES = "YES"
    NO = "NO"
    IRRELEVANT = "IRRELEVANT"
    PENALTY = "PENALTY"
    WIN = "WIN"


def status_after(used: int, answer: Answer, max_questions: int = MAX_QUESTIONS) -> GameStatus:
    """Status after a question has been charged (`used` already includes it)."""
    if answer is Answer.WIN:
        return GameStatus.WON
    if used >= max_questions:
        return GameStatus.LOST
    return GameStatus.IN_PROGRESS


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    number: int
    question: str
    answer: Answer
    asked_at: datetime


@dataclass(frozen=True, slots=True)
class GameState:
    game_date: date
    status: GameStatus
    used: int
    in_progress: bool
    started_at: datetime | None
    finished_at: datetime | None
    history: tuple[HistoryEntry, ...] = field(default_factory=tuple)
    max_questions: int = MAX_QUESTIONS

    @property
    def remaining(self) -> int:
        return self.max_questions - self.used

    @property
    def duration_ms(self) -> int | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return int((self.finished_at - self.started_at).total_seconds() * 1000)


@dataclass(frozen=True, slots=True)
class LeaderboardEntry:
    rank: int
    player_hash: str
    questions: int
    duration_ms: int

    @property
    def display_name(self) -> str:
        return display_name_for(self.player_hash)


@dataclass(frozen=True, slots=True)
class Leaderboard:
    game_date: date
    entries: tuple[LeaderboardEntry, ...]
    me: LeaderboardEntry | None
    total_winners: int


def display_name_for(player_hash: str) -> str:
    """Anonymous, stable display name derived from the keyed player hash (no PII)."""
    return "Player-" + player_hash[:6].upper()


def leaderboard_score(questions: int, duration_ms: int) -> int:
    """Fewer questions first, then shorter duration. Exact in a Redis double (< 2**53)."""
    return questions * 1_000_000_000 + duration_ms
