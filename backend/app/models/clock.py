"""UTC clock abstraction and game-day arithmetic.

Nothing else in the backend may read the system clock (ADR 0004). Every time value is a
timezone-aware UTC datetime, so the host's local timezone or the player's device clock can
never influence which game day it is.
"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Return the current instant as a timezone-aware UTC datetime."""
        ...


class SystemUTCClock:
    """Production clock. `datetime.now(UTC)` ignores the TZ setting of the host."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """Test clock that returns a settable instant."""

    def __init__(self, instant: datetime) -> None:
        self._instant = to_utc(instant)

    def now(self) -> datetime:
        return self._instant

    def set(self, instant: datetime) -> None:
        self._instant = to_utc(instant)


def to_utc(instant: datetime) -> datetime:
    """Convert an aware datetime to UTC. Naive datetimes are rejected, never guessed."""
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("naive datetime: an explicit timezone is required")
    return instant.astimezone(UTC)


def game_date_at(instant: datetime) -> date:
    """The game day an instant belongs to: its calendar date in UTC."""
    return to_utc(instant).date()


def next_reset_at(instant: datetime) -> datetime:
    """The next 00:00:00 UTC strictly after `instant`."""
    return datetime.combine(game_date_at(instant) + timedelta(days=1), time.min, tzinfo=UTC)
