"""Deterministic question checks (OQ-04) and normalization for duplicate detection (OQ-05)."""

import hashlib
import re
from dataclasses import dataclass

MIN_LENGTH = 3
MAX_LENGTH = 150
_WHITESPACE = re.compile(r"\s+")
_TRAILING_PUNCTUATION = re.compile(r"[\s?!.]+$")


class InvalidQuestionError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class Question:
    text: str  # trimmed, as the player wrote it
    normalized: str

    @property
    def qhash(self) -> str:
        return hashlib.sha256(self.normalized.encode()).hexdigest()[:32]


def parse_question(raw: str) -> Question:
    text = _WHITESPACE.sub(" ", raw.strip())
    if len(text) < MIN_LENGTH:
        raise InvalidQuestionError("too_short")
    if len(text) > MAX_LENGTH:
        raise InvalidQuestionError("too_long")
    if not all(" " <= ch <= "~" for ch in text):
        raise InvalidQuestionError("invalid_characters")
    if not text.endswith("?"):
        raise InvalidQuestionError("not_a_question")
    normalized = _TRAILING_PUNCTUATION.sub("", text.lower())
    return Question(text=text, normalized=normalized)


def mentions_word(question: Question, word: str) -> bool:
    """Server-side WIN check (OQ-03): the exact word or a simple plural appears as a token."""
    tokens = set(re.findall(r"[a-z]+", question.normalized))
    return bool(tokens & {word, word + "s", word + "es"})
