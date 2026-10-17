"""Progressive hints: one more hint after every HINT_EVERY charged attempts.

Each word has HINT_COUNT hints ordered from hardest to easiest; the last one makes the word
unambiguous. Hints are prepared ahead of time in the private word list (owners can edit
them); `derive_hints` builds a default ladder from the word's metadata when none is given.
"""

import re

from app.models.word import WordEntry

HINT_EVERY = 2
HINT_COUNT = 4


def visible_hint_count(used: int) -> int:
    """How many hints a player with `used` charged attempts may see (0 to HINT_COUNT)."""
    return min(HINT_COUNT, max(0, used) // HINT_EVERY)


def _mentions(word: str, text: str) -> bool:
    return re.search(rf"\b{re.escape(word)}(s|es)?\b", text, re.IGNORECASE) is not None


def derive_hints(entry: WordEntry) -> tuple[str, ...]:
    """Default ladder: generic traits, category, specific traits, definition + letters.

    Metadata that names the word itself (e.g. an attribute equal to the word) is skipped.
    """
    word = entry.word
    attrs = [a for a in entry.attributes if not _mentions(word, a)] or ["(no clue)"]
    generic, specific = attrs[:2], attrs[2:] or attrs[-1:]
    category = entry.category if not _mentions(word, entry.category) else entry.part_of_speech
    return (
        f"First clue: {', '.join(generic)}.",
        f"It belongs to the category “{category}”.",
        f"More clues: {', '.join(specific)}.",
        f"{entry.definition} The word is {len(word)} characters long"
        f" and begins with “{word[0].upper()}”.",
    )


def hint_problems(word: str, hints: tuple[str, ...]) -> list[str]:
    """Reasons a hint list is unusable. Hints may describe the word but never spell it."""
    problems: list[str] = []
    if len(hints) != HINT_COUNT:
        problems.append(f"exactly {HINT_COUNT} hints required")
    for hint in hints:
        if not 5 <= len(hint) <= 200:
            problems.append("hints must be 5-200 characters")
        if _mentions(word, hint):
            problems.append("a hint must not contain the word")
    return problems
