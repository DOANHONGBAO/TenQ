"""SQLite storage for the vocabulary and the per-day pinned puzzle."""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from app.models.daily_game import DailyPuzzle
from app.models.word import PartOfSpeech, WordEntry
from app.repositories.database import transaction


class WordRepository(Protocol):
    def list_words(self) -> list[str]: ...
    def get_entry(self, word: str) -> WordEntry | None: ...
    def replace_words(self, entries: list[WordEntry]) -> None: ...
    def get_pinned(self, game_date: date) -> DailyPuzzle | None: ...
    def pin(self, puzzle: DailyPuzzle, pinned_at: datetime) -> DailyPuzzle: ...


class SqliteWordRepository:
    """Synchronous repository; call it from a worker thread inside async code."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def list_words(self) -> list[str]:
        """All words in canonical (sorted) order, the order the schedule indexes into."""
        with transaction(self._path) as conn:
            return [row[0] for row in conn.execute("SELECT word FROM words ORDER BY word")]

    def get_entry(self, word: str) -> WordEntry | None:
        with transaction(self._path) as conn:
            row = conn.execute(
                "SELECT word, part_of_speech, category, definition, attributes_json, hints_json "
                "FROM words WHERE word = ?",
                (word,),
            ).fetchone()
        if row is None:
            return None
        return WordEntry(
            word=row[0],
            part_of_speech=PartOfSpeech(row[1]),
            category=row[2],
            definition=row[3],
            attributes=tuple(json.loads(row[4])),
            hints=tuple(json.loads(row[5])),
        )

    def replace_words(self, entries: list[WordEntry]) -> None:
        """Replace the whole vocabulary atomically. Pinned days are never touched."""
        rows = [
            (
                e.word,
                e.part_of_speech.value,
                e.category,
                e.definition,
                json.dumps(e.attributes),
                json.dumps(e.hints),
            )
            for e in entries
        ]
        with transaction(self._path) as conn:
            conn.execute("DELETE FROM words")
            conn.executemany(
                "INSERT INTO words "
                "(word, part_of_speech, category, definition, attributes_json, hints_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )

    def get_pinned(self, game_date: date) -> DailyPuzzle | None:
        with transaction(self._path) as conn:
            row = conn.execute(
                "SELECT word, word_list_sha256, selection_version FROM daily_puzzles "
                "WHERE game_date = ?",
                (game_date.isoformat(),),
            ).fetchone()
        if row is None:
            return None
        return DailyPuzzle(
            game_date=game_date, word=row[0], word_list_sha256=row[1], selection_version=row[2]
        )

    def pin(self, puzzle: DailyPuzzle, pinned_at: datetime) -> DailyPuzzle:
        """Store the puzzle unless the date is already pinned; return the stored one.

        INSERT OR IGNORE on the primary key makes concurrent first requests safe: whichever
        insert lands first wins and every caller reads that same row back.
        """
        with transaction(self._path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO daily_puzzles "
                "(game_date, word, word_list_sha256, selection_version, pinned_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    puzzle.game_date.isoformat(),
                    puzzle.word,
                    puzzle.word_list_sha256,
                    puzzle.selection_version,
                    pinned_at.isoformat(),
                ),
            )
        stored = self.get_pinned(puzzle.game_date)
        if stored is None:  # pragma: no cover - the insert above guarantees a row
            raise RuntimeError("pinned puzzle missing after insert")
        return stored
