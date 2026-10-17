"""Validate a private word list and load it into SQLite.

Usage:
    uv run python -m app.scripts.seed_words secrets/words.json
    uv run python -m app.scripts.seed_words --dev     # 365 obviously fake words for local dev
    docker compose run --rm -T api python -m app.scripts.seed_words - < backend/secrets/words.json
                                                      # "-" reads the list from stdin, so the
                                                      # private file never needs a mount

Output never includes the words themselves, only counts and the list fingerprint.
"""

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from pydantic import ValidationError

from app.core.config import get_settings
from app.models.daily_game import DailyGameConfig
from app.models.hints import derive_hints
from app.models.word import InvalidWordListError, PartOfSpeech, WordEntry, validate_word_list
from app.models.word_schedule import word_list_sha256
from app.repositories.database import apply_migrations
from app.repositories.word_repository import SqliteWordRepository
from app.schemas.word_seed import WordSeedFile

_LETTERS = "abcdefghijklmnopqrstuvwxyz"


def dev_entries(count: int) -> list[WordEntry]:
    """Deterministic fake words such as `zzdevaab`; never valid English answers."""
    entries: list[WordEntry] = []
    for i in range(count):
        suffix = _LETTERS[i // 676] + _LETTERS[(i // 26) % 26] + _LETTERS[i % 26]
        entry = WordEntry(
            word=f"zzdev{suffix}",
            part_of_speech=PartOfSpeech.NOUN,
            category="development placeholder",
            definition="A fake entry used only for local development and tests.",
            attributes=("fake", "development only"),
        )
        entries.append(replace(entry, hints=derive_hints(entry)))
    return entries


def load_entries(path: Path) -> list[WordEntry]:
    data = sys.stdin.buffer.read() if str(path) == "-" else path.read_bytes()
    items = WordSeedFile.validate_json(data)
    return [item.to_entry() for item in items]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("file", nargs="?", type=Path, help="JSON word list outside the repo")
    source.add_argument("--dev", action="store_true", help="seed fake development words")
    args = parser.parse_args(argv)

    config = DailyGameConfig()
    try:
        entries = dev_entries(config.word_count) if args.dev else load_entries(args.file)
        validate_word_list(entries, config.word_count)
    except (OSError, ValidationError, InvalidWordListError) as exc:
        # Pydantic errors may echo input values; print only the error count for those.
        if isinstance(exc, ValidationError):
            print(f"error: word list has {exc.error_count()} schema errors", file=sys.stderr)
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1

    settings = get_settings()
    apply_migrations(settings.database_path)
    SqliteWordRepository(settings.database_path).replace_words(entries)
    fingerprint = word_list_sha256(sorted(e.word for e in entries))
    print(f"seeded {len(entries)} words into {settings.database_path} (sha256 {fingerprint[:12]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
