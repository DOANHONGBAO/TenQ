"""Use case: which secret word belongs to a UTC game date.

Flow for a date:
1. If the date is pinned in SQLite, the stored word wins (restarts and list edits are safe).
2. Otherwise compute it with the keyed yearly schedule and pin it with INSERT OR IGNORE.
3. Keep the result in memory so later requests that day do not touch SQLite.
"""

import logging
import threading
from datetime import date, datetime

from app.core.errors import AnswerNotAvailableError, NotFoundError, ServiceUnavailableError
from app.models.clock import Clock, game_date_at, next_reset_at
from app.models.daily_game import DailyGameConfig, DailyPuzzle
from app.models.word import WordEntry
from app.models.word_schedule import word_index_for, word_list_sha256
from app.repositories.word_repository import WordRepository

logger = logging.getLogger(__name__)


class DailyWordService:
    def __init__(
        self,
        repository: WordRepository,
        clock: Clock,
        selection_key: bytes,
        config: DailyGameConfig | None = None,
    ) -> None:
        if len(selection_key) < 32:
            raise ValueError("selection key must be at least 32 bytes")
        self._repository = repository
        self._clock = clock
        self._key = selection_key
        self._config = config or DailyGameConfig()
        self._cache: dict[date, DailyPuzzle] = {}
        self._entries: dict[str, WordEntry] = {}
        self._lock = threading.Lock()

    def now(self) -> datetime:
        return self._clock.now()

    def current_game_date(self) -> date:
        return game_date_at(self._clock.now())

    def next_reset_at(self) -> datetime:
        return next_reset_at(self._clock.now())

    def puzzle_for_today(self) -> DailyPuzzle:
        """Server-side only. The returned word must never be sent to a client."""
        return self._puzzle_for(self.current_game_date())

    def puzzle_for(self, game_date: date) -> DailyPuzzle:
        """Puzzle of an explicit date (a request fixes its game date once, at the start)."""
        return self._puzzle_for(game_date)

    def entry_for(self, puzzle: DailyPuzzle) -> WordEntry | None:
        """Metadata for the AI judge. None if the word was removed from the list since pinning."""
        with self._lock:
            cached = self._entries.get(puzzle.word)
        if cached is not None:
            return cached
        entry = self._repository.get_entry(puzzle.word)
        if entry is not None:
            with self._lock:
                self._entries = {puzzle.word: entry}
        return entry

    def revealed_word(self, game_date: date) -> str:
        """The word of a finished day (BR-12, OQ-08). Never today's or a future word."""
        if game_date >= self.current_game_date():
            raise AnswerNotAvailableError()
        puzzle = self._repository.get_pinned(game_date)
        if puzzle is None:
            raise NotFoundError("No puzzle was played on that date.")
        return puzzle.word

    def _puzzle_for(self, game_date: date) -> DailyPuzzle:
        with self._lock:
            cached = self._cache.get(game_date)
            if cached is not None:
                return cached
            puzzle = self._repository.get_pinned(game_date) or self._pin_new(game_date)
            # Keep at most two days: a request may still finish yesterday's question.
            self._cache[game_date] = puzzle
            if len(self._cache) > 2:
                self._cache.pop(min(self._cache))
            return puzzle

    def _pin_new(self, game_date: date) -> DailyPuzzle:
        words = self._repository.list_words()
        if len(words) != self._config.word_count:
            logger.error(
                "word list not usable: %d words seeded, %d required",
                len(words),
                self._config.word_count,
            )
            raise ServiceUnavailableError()
        index = word_index_for(self._key, game_date, len(words))
        candidate = DailyPuzzle(
            game_date=game_date,
            word=words[index],
            word_list_sha256=word_list_sha256(words),
            selection_version=self._config.selection_version,
        )
        pinned = self._repository.pin(candidate, pinned_at=self._clock.now())
        logger.info("puzzle pinned for %s", game_date.isoformat())
        return pinned
