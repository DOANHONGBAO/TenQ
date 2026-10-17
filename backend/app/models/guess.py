"""Direct guesses typed into the guess box. Judged by exact comparison, never by the AI."""

import hashlib
import re
from dataclasses import dataclass

_GUESS = re.compile(r"^(?:(?:a|an|the)\s+)?([a-z]{2,32})$")


class InvalidGuessError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class Guess:
    text: str  # as typed, trimmed
    word: str  # normalized: lower case, article removed

    @property
    def qhash(self) -> str:
        # Separate namespace from questions so "walrus" and "Is it walrus?" never collide.
        return hashlib.sha256(f"guess:{self.word}".encode()).hexdigest()[:32]


def parse_guess(raw: str) -> Guess:
    text = " ".join(raw.split())
    if not text:
        raise InvalidGuessError("empty")
    match = _GUESS.fullmatch(text.lower())
    if match is None:
        raise InvalidGuessError("one_word_letters_only")
    return Guess(text=text, word=match.group(1))


def guess_is_correct(guess: Guess, secret: str) -> bool:
    """The exact word or a simple plural, case-insensitive (OQ-03)."""
    return guess.word in {secret, secret + "s", secret + "es"}
