"""Vocabulary entries and the rules a seeded word list must satisfy."""

import re
from dataclasses import dataclass
from enum import StrEnum

WORD_PATTERN = re.compile(r"^[a-z]{2,32}$")
CATEGORY_PATTERN = re.compile(r"^[a-z]+( [a-z]+)*$")


class PartOfSpeech(StrEnum):
    NOUN = "noun"
    VERB = "verb"
    ADJECTIVE = "adjective"
    ADVERB = "adverb"


@dataclass(frozen=True, slots=True)
class WordEntry:
    """A candidate secret word plus metadata the AI judge may use in later phases."""

    word: str
    part_of_speech: PartOfSpeech
    category: str
    definition: str
    attributes: tuple[str, ...]
    # Progressive hints, hardest first (app.models.hints). Empty = derive from metadata.
    hints: tuple[str, ...] = ()

    def __repr__(self) -> str:
        return f"WordEntry(category={self.category!r}, word=<redacted>)"


class InvalidWordListError(ValueError):
    """The word list cannot be used. Messages never quote the words themselves."""


def validate_word_list(entries: list[WordEntry], expected_count: int) -> None:
    from app.models.hints import hint_problems  # local import: hints depends on WordEntry

    """Raise InvalidWordListError unless the list is complete, unique, and well formed."""
    problems: list[str] = []
    if len(entries) != expected_count:
        problems.append(f"expected {expected_count} words, got {len(entries)}")

    seen: set[str] = set()
    for position, entry in enumerate(entries, start=1):
        if not WORD_PATTERN.fullmatch(entry.word):
            problems.append(f"entry {position}: word must match [a-z]{{2,32}}")
        if entry.word in seen:
            problems.append(f"entry {position}: duplicate word")
        seen.add(entry.word)
        if not CATEGORY_PATTERN.fullmatch(entry.category) or len(entry.category) > 40:
            problems.append(f"entry {position}: category must be lower-case words, max 40")
        if not 10 <= len(entry.definition) <= 200:
            problems.append(f"entry {position}: definition must be 10-200 characters")
        if re.search(rf"\b{re.escape(entry.word)}s?\b", entry.definition.lower()):
            problems.append(f"entry {position}: definition must not contain the word")
        if not 1 <= len(entry.attributes) <= 8:
            problems.append(f"entry {position}: 1-8 attributes required")
        if any(not 1 <= len(a) <= 40 for a in entry.attributes):
            problems.append(f"entry {position}: attributes must be 1-40 characters")
        problems.extend(f"entry {position}: {p}" for p in hint_problems(entry.word, entry.hints))

    if problems:
        shown = "; ".join(problems[:10])
        more = f" (+{len(problems) - 10} more)" if len(problems) > 10 else ""
        raise InvalidWordListError(f"invalid word list: {shown}{more}")
