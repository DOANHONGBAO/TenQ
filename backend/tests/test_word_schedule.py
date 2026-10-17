from collections import Counter
from datetime import date, timedelta

import pytest

from app.models.word_schedule import (
    SCHEDULE_DAYS,
    word_index_for,
    word_list_sha256,
    yearly_permutation,
)
from tests.conftest import TEST_KEY

OTHER_KEY = bytes(range(32))


def days_of(year: int) -> list[date]:
    start = date(year, 1, 1)
    count = (date(year + 1, 1, 1) - start).days
    return [start + timedelta(days=i) for i in range(count)]


def schedule(year: int, key: bytes = TEST_KEY) -> list[int]:
    return [word_index_for(key, d) for d in days_of(year)]


def test_permutation_is_a_permutation() -> None:
    order = yearly_permutation(TEST_KEY, 2026)
    assert sorted(order) == list(range(SCHEDULE_DAYS))


@pytest.mark.parametrize("year", [2025, 2026, 2027, 2029, 2100])
def test_common_year_uses_every_word_exactly_once(year: int) -> None:
    indices = schedule(year)
    assert len(indices) == 365
    assert len(set(indices)) == 365


@pytest.mark.parametrize("year", [2024, 2028, 2032, 2000])
def test_leap_year_repeats_exactly_one_word_far_apart(year: int) -> None:
    indices = schedule(year)
    assert len(indices) == 366
    counts = Counter(indices)
    repeated = [i for i, n in counts.items() if n > 1]

    assert len(set(indices)) == 365  # every word still appears
    assert len(repeated) == 1 and counts[repeated[0]] == 2
    first_day = indices.index(repeated[0]) + 1
    assert indices[-1] == repeated[0]  # the repeat is 31 December (day 366)
    assert 3 <= first_day <= 183  # first use in the early-year window
    assert 366 - first_day >= 183  # at least half a year apart


def test_no_word_repeats_on_consecutive_days_across_years() -> None:
    days = [d for year in range(2024, 2041) for d in days_of(year)]
    indices = [word_index_for(TEST_KEY, d) for d in days]
    for day, today, tomorrow in zip(days, indices, indices[1:], strict=False):
        assert today != tomorrow, f"same word on {day} and the next day"


def test_new_year_transition_is_checked_both_ways() -> None:
    for year in range(2025, 2060):
        assert word_index_for(TEST_KEY, date(year - 1, 12, 31)) != word_index_for(
            TEST_KEY, date(year, 1, 1)
        )


def test_deterministic_for_same_key() -> None:
    assert schedule(2026) == schedule(2026)


def test_different_key_gives_different_schedule() -> None:
    assert schedule(2026, TEST_KEY) != schedule(2026, OTHER_KEY)


def test_each_year_has_a_different_order() -> None:
    assert yearly_permutation(TEST_KEY, 2026) != yearly_permutation(TEST_KEY, 2027)


def test_schedule_is_not_day_of_year_order() -> None:
    # A naive "word[day_of_year]" schedule would be guessable from the public code.
    assert schedule(2026)[:10] != list(range(10))


def test_short_keys_are_rejected() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        word_index_for(b"too-short", date(2026, 1, 1))


def test_wrong_word_count_is_rejected() -> None:
    with pytest.raises(ValueError, match="365"):
        yearly_permutation(TEST_KEY, 2026, 300)


def test_word_list_fingerprint_depends_on_content() -> None:
    assert word_list_sha256(["zzalpha", "zzbeta"]) != word_list_sha256(["zzalpha", "zzgamma"])
    assert len(word_list_sha256(["zzalpha"])) == 64


@pytest.mark.parametrize("year", [2256, 2489])  # years where the test key needs the swap
def test_year_boundary_swap_prevents_same_word(year: int) -> None:
    from app.models.word_schedule import _raw_permutation  # pyright: ignore[reportPrivateUsage]

    raw = _raw_permutation(TEST_KEY, year, SCHEDULE_DAYS)
    last_of_previous = word_index_for(TEST_KEY, date(year - 1, 12, 31))

    assert raw[0] == last_of_previous  # without the rule, 1 January would repeat
    final = yearly_permutation(TEST_KEY, year)
    assert final[0] == raw[1] and final[1] == raw[0]
    assert final[2:] == raw[2:]
    assert word_index_for(TEST_KEY, date(year, 1, 1)) != last_of_previous
