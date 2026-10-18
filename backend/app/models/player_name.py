"""Validation of the public name a winner shows on the leaderboard (OQ-07). Pure functions."""

import re
import unicodedata

MIN_LENGTH = 2
MAX_LENGTH = 20
_ALLOWED_PUNCTUATION = frozenset(" _-.'")
_SPACES = re.compile(r"\s+")
# No links or contact details on a public board.
_BLOCKED = re.compile(r"https?|www\.|\.(com|net|org|io|vn)\b|@", re.IGNORECASE)


class InvalidPlayerNameError(ValueError):
    pass


def normalize_player_name(raw: str) -> str:
    """NFC-normalized, single-spaced name of letters (any script), digits, and a little punctuation.

    Combining marks are rejected after NFC, so precomposed Vietnamese letters pass while
    "zalgo" text stacking marks does not.
    """
    name = _SPACES.sub(" ", unicodedata.normalize("NFC", raw)).strip()
    if not MIN_LENGTH <= len(name) <= MAX_LENGTH:
        raise InvalidPlayerNameError(f"A name must be {MIN_LENGTH} to {MAX_LENGTH} characters.")
    if not all(ch.isalnum() or ch in _ALLOWED_PUNCTUATION for ch in name):
        raise InvalidPlayerNameError("Use letters, digits, spaces, and _ - . ' only.")
    if not any(ch.isalpha() for ch in name):
        raise InvalidPlayerNameError("A name needs at least one letter.")
    if _BLOCKED.search(name):
        raise InvalidPlayerNameError("Links are not allowed in names.")
    return name
