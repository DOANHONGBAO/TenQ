"""Static rules of the daily game."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class DailyGameConfig:
    # The yearly schedule assigns one word per day of a 365-day year (see word_schedule).
    word_count: int = 365
    max_questions: int = 10
    # Bump when the selection algorithm changes; recorded on every pinned day.
    selection_version: int = 1


@dataclass(frozen=True, slots=True)
class DailyPuzzle:
    """The secret word pinned for one UTC game date.

    `word` is excluded from repr so the puzzle can never leak through logs or tracebacks.
    """

    game_date: date
    word: str
    word_list_sha256: str
    selection_version: int

    def __repr__(self) -> str:
        return f"DailyPuzzle(game_date={self.game_date.isoformat()}, word=<redacted>)"
