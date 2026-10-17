"""Fake Cloudflare Siteverify endpoint for tests (no network)."""

import json
from collections import deque
from datetime import datetime

import httpx2

from app.models.clock import FixedClock


class TurnstileMock:
    """Answers like Siteverify. By default every token passes with a fresh challenge_ts."""

    def __init__(self, clock: FixedClock, hostname: str = "localhost") -> None:
        self.clock = clock
        self.hostname = hostname
        self.requests: list[dict[str, object]] = []
        self._script: deque[dict[str, object] | httpx2.Response | Exception] = deque()

    def queue(self, *steps: dict[str, object] | httpx2.Response | Exception) -> None:
        self._script.extend(steps)

    def success(self, **overrides: object) -> dict[str, object]:
        body: dict[str, object] = {
            "success": True,
            "challenge_ts": self.clock.now().isoformat().replace("+00:00", "Z"),
            "hostname": self.hostname,
            "action": "session",
            "error-codes": [],
        }
        body.update(overrides)
        return body

    @staticmethod
    def failure(*codes: str) -> dict[str, object]:
        return {"success": False, "error-codes": list(codes)}

    def challenge_at(self, moment: datetime) -> dict[str, object]:
        return self.success(challenge_ts=moment.isoformat().replace("+00:00", "Z"))

    @property
    def calls(self) -> int:
        return len(self.requests)

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self._handle)

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        if not body.get("response"):
            return httpx2.Response(200, json=self.failure("missing-input-response"))
        step = self._script.popleft() if self._script else self.success()
        if isinstance(step, Exception):
            raise step
        if isinstance(step, httpx2.Response):
            return step
        return httpx2.Response(200, json=step)
