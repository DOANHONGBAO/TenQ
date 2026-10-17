"""Minimal in-process circuit breaker.

CLOSED: calls flow; consecutive failures are counted.
OPEN: after `failure_threshold` failures, calls are refused until `open_seconds` pass.
HALF_OPEN: one trial call is allowed; success closes the circuit, failure reopens it.
"""

import time
from collections.abc import Callable
from enum import StrEnum


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        open_seconds: float = 30.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = failure_threshold
        self._open_seconds = open_seconds
        self._now = monotonic
        self._failures = 0
        self._opened_at: float | None = None
        self._open_for = open_seconds
        self._trial_running = False

    @property
    def state(self) -> BreakerState:
        if self._opened_at is None:
            return BreakerState.CLOSED
        if self._now() - self._opened_at >= self._open_for:
            return BreakerState.HALF_OPEN
        return BreakerState.OPEN

    def allow(self) -> bool:
        state = self.state
        if state is BreakerState.CLOSED:
            return True
        if state is BreakerState.HALF_OPEN and not self._trial_running:
            self._trial_running = True
            return True
        return False

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None
        self._trial_running = False

    def record_failure(self) -> None:
        self._failures += 1
        if self._trial_running or self._failures >= self._threshold:
            self._open(self._open_seconds)

    def trip(self, seconds: float) -> None:
        """Open immediately, e.g. after an authentication or billing error."""
        self._open(seconds)

    def _open(self, seconds: float) -> None:
        self._opened_at = self._now()
        self._open_for = seconds
        self._trial_running = False
