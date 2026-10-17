"""Keyed yearly word schedule.

For each calendar year the server derives a secret permutation of the word list with
HMAC-SHA256(selection_key, ...) and walks it one word per day:

    word(date) = words[perm_year[day_of_year - 1]]          for day_of_year 1..365

Without the server-side key the order is indistinguishable from random, so publishing this
code reveals nothing about future answers. Within a common year every word appears exactly
once.

Leap years have 366 days but there are only 365 words, so one repeat is unavoidable. The
chosen, intentional behavior: day 366 (31 December) reuses the word of an early-year day
`perm_year[leap_slot]` with leap_slot in [2, 182], also derived from the key. That repeat is
at least 183 days after its first use, never adjacent, and it is the only repeat in the year.

Year boundaries: permutations of consecutive years are independent, so 1 January could
equal 31 December of the year before. If the new year's first word would equal the previous
year's last word, the first two positions are swapped. Positions 2 and later are never
touched by that swap, and `leap_slot >= 2`, so "last word of year Y-1" is computable from
year Y-1's raw permutation without recursion.
"""

import hashlib
import hmac
from collections.abc import Iterator
from datetime import date
from functools import lru_cache

SCHEDULE_DAYS = 365
_LEAP_SLOT_MIN = 2
_LEAP_SLOT_MAX = 182
_UINT64 = 2**64


def _uint64_stream(key: bytes, label: str) -> Iterator[int]:
    """Endless stream of 64-bit integers: HMAC-SHA256(key, label:counter), 4 per block."""
    counter = 0
    while True:
        block = hmac.new(key, f"{label}:{counter}".encode(), hashlib.sha256).digest()
        for offset in range(0, 32, 8):
            yield int.from_bytes(block[offset : offset + 8], "big")
        counter += 1


def _randbelow(stream: Iterator[int], n: int) -> int:
    """Uniform integer in [0, n) by rejection sampling, so no value is favored."""
    limit = _UINT64 - (_UINT64 % n)
    while True:
        value = next(stream)
        if value < limit:
            return value % n


@lru_cache(maxsize=16)
def _raw_permutation(key: bytes, year: int, n: int) -> tuple[int, ...]:
    """Fisher-Yates shuffle of range(n) driven by the keyed stream for `year`."""
    order = list(range(n))
    stream = _uint64_stream(key, f"tenq:v1:perm:{year}")
    for i in range(n - 1, 0, -1):
        j = _randbelow(stream, i + 1)
        order[i], order[j] = order[j], order[i]
    return tuple(order)


@lru_cache(maxsize=16)
def _leap_slot(key: bytes, year: int) -> int:
    stream = _uint64_stream(key, f"tenq:v1:leap:{year}")
    return _LEAP_SLOT_MIN + _randbelow(stream, _LEAP_SLOT_MAX - _LEAP_SLOT_MIN + 1)


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _last_index_of_year(key: bytes, year: int, n: int) -> int:
    raw = _raw_permutation(key, year, n)
    return raw[_leap_slot(key, year)] if _is_leap(year) else raw[SCHEDULE_DAYS - 1]


@lru_cache(maxsize=16)
def yearly_permutation(key: bytes, year: int, n: int = SCHEDULE_DAYS) -> tuple[int, ...]:
    """The schedule for `year`: position d-1 holds the word index for day-of-year d."""
    if n != SCHEDULE_DAYS:
        raise ValueError(f"the yearly schedule needs exactly {SCHEDULE_DAYS} words, got {n}")
    order = list(_raw_permutation(key, year, n))
    if year > 1 and order[0] == _last_index_of_year(key, year - 1, n):
        order[0], order[1] = order[1], order[0]
    return tuple(order)


def word_index_for(key: bytes, day: date, n: int = SCHEDULE_DAYS) -> int:
    """Index into the canonical (sorted) word list for the UTC game date `day`."""
    if len(key) < 32:
        raise ValueError("selection key must be at least 32 bytes")
    order = yearly_permutation(key, day.year, n)
    day_of_year = day.timetuple().tm_yday
    if day_of_year <= SCHEDULE_DAYS:
        return order[day_of_year - 1]
    return order[_leap_slot(key, day.year)]  # 31 December of a leap year


def word_list_sha256(words: list[str]) -> str:
    """Fingerprint of the canonical word list, recorded on each pinned day."""
    return hashlib.sha256("\n".join(words).encode()).hexdigest()
