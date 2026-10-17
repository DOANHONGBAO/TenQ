import time
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from app.models.clock import FixedClock, SystemUTCClock, game_date_at, next_reset_at, to_utc


def test_boundary_last_microsecond_and_midnight() -> None:
    last = datetime(2026, 10, 17, 23, 59, 59, 999_999, tzinfo=UTC)
    midnight = datetime(2026, 10, 18, 0, 0, 0, tzinfo=UTC)

    assert game_date_at(last) == date(2026, 10, 17)
    assert game_date_at(midnight) == date(2026, 10, 18)
    assert game_date_at(last.replace(microsecond=0)) == date(2026, 10, 17)  # 23:59:59


@pytest.mark.parametrize("offset_hours", [-12, -5, 0, 7, 9, 14])
def test_same_instant_in_any_timezone_is_the_same_game_day(offset_hours: int) -> None:
    instant_utc = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)
    local = instant_utc.astimezone(timezone(timedelta(hours=offset_hours)))

    # The local wall-clock date differs for some offsets; the game day never does.
    assert game_date_at(local) == date(2026, 10, 17)


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError, match="naive"):
        to_utc(datetime(2026, 10, 17, 12, 0))


def test_next_reset_is_next_utc_midnight() -> None:
    assert next_reset_at(datetime(2026, 10, 17, 0, 0, tzinfo=UTC)) == datetime(
        2026, 10, 18, tzinfo=UTC
    )
    assert next_reset_at(datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)) == datetime(
        2027, 1, 1, tzinfo=UTC
    )
    assert next_reset_at(datetime(2028, 2, 28, 18, 0, tzinfo=UTC)) == datetime(
        2028, 2, 29, tzinfo=UTC
    )


def test_system_clock_ignores_host_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = SystemUTCClock()
    readings: list[datetime] = []
    for tz in ("Pacific/Kiritimati", "America/Los_Angeles", "Asia/Ho_Chi_Minh"):
        monkeypatch.setenv("TZ", tz)
        time.tzset()
        readings.append(clock.now())
    monkeypatch.delenv("TZ")
    time.tzset()

    for reading in readings:
        assert reading.utcoffset() == timedelta(0)
    assert max(readings) - min(readings) < timedelta(seconds=5)


def test_fixed_clock_normalizes_to_utc() -> None:
    clock = FixedClock(datetime(2026, 10, 18, 6, 0, tzinfo=timezone(timedelta(hours=7))))
    assert clock.now() == datetime(2026, 10, 17, 23, 0, tzinfo=UTC)
