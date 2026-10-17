"""Cloudflare Turnstile server-side validation (Siteverify).

Checked against https://developers.cloudflare.com/turnstile/ on 2026-10-17:
- POST https://challenges.cloudflare.com/turnstile/v0/siteverify with secret, response,
  optional remoteip and idempotency_key; JSON response with success, challenge_ts,
  hostname, action, error-codes.
- Tokens are valid for 300 seconds and can be validated only once.
- Test secrets (1x/2x/3x...AA) return hostname "example.com", no action, and
  metadata.result_with_testing_key = true.

Every outcome other than an explicit, fully checked success is a failure (fail closed).
"""

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import httpx2

logger = logging.getLogger(__name__)

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TOKEN_MAX_AGE = timedelta(seconds=300)
MAX_TOKEN_LENGTH = 2048


class TurnstileOutcome(StrEnum):
    OK = "ok"
    REJECTED = "rejected"  # the token is bad: 403 TURNSTILE_FAILED
    UNAVAILABLE = "unavailable"  # Cloudflare unreachable or erroring: 503, fail closed


@dataclass(frozen=True, slots=True)
class TurnstileResult:
    outcome: TurnstileOutcome
    reason: str


class TurnstileVerifier:
    def __init__(
        self,
        http: httpx2.AsyncClient,
        secret: str,
        *,
        allowed_hostnames: Sequence[str],
        expected_action: str,
        allow_test_keys: bool,
        timeout_s: float = 5.0,
    ) -> None:
        self._http = http
        self._secret = secret
        self._hostnames = {h.lower() for h in allowed_hostnames}
        self._action = expected_action
        self._allow_test_keys = allow_test_keys
        self._timeout_s = timeout_s

    async def verify(self, token: str, remote_ip: str | None, now: datetime) -> TurnstileResult:
        if not token or len(token) > MAX_TOKEN_LENGTH:
            return TurnstileResult(TurnstileOutcome.REJECTED, "missing-or-oversized-token")
        payload: dict[str, str] = {
            "secret": self._secret,
            "response": token,
            "idempotency_key": str(uuid.uuid4()),
        }
        if remote_ip:
            payload["remoteip"] = remote_ip
        try:
            response = await self._http.post(SITEVERIFY_URL, json=payload, timeout=self._timeout_s)
        except httpx2.TransportError as exc:
            logger.warning("turnstile siteverify unreachable: %s", type(exc).__name__)
            return TurnstileResult(TurnstileOutcome.UNAVAILABLE, "unreachable")
        if response.status_code != 200:
            logger.warning("turnstile siteverify http %d", response.status_code)
            return TurnstileResult(TurnstileOutcome.UNAVAILABLE, f"http-{response.status_code}")
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("not an object")
        except ValueError:
            return TurnstileResult(TurnstileOutcome.UNAVAILABLE, "malformed-response")
        return self._check(data, now)

    def _check(self, data: dict[str, object], now: datetime) -> TurnstileResult:
        errors = data.get("error-codes") or []
        error_list = [str(e) for e in errors] if isinstance(errors, list) else []
        if data.get("success") is not True:
            if "internal-error" in error_list:
                return TurnstileResult(TurnstileOutcome.UNAVAILABLE, "internal-error")
            if any(e in ("missing-input-secret", "invalid-input-secret") for e in error_list):
                logger.error("turnstile secret rejected by Cloudflare: check configuration")
                return TurnstileResult(TurnstileOutcome.UNAVAILABLE, "bad-secret")
            return TurnstileResult(TurnstileOutcome.REJECTED, ",".join(error_list) or "failed")

        metadata = data.get("metadata")
        is_test = isinstance(metadata, dict) and metadata.get("result_with_testing_key") is True
        if is_test and not self._allow_test_keys:
            logger.error("turnstile test key used where real keys are required")
            return TurnstileResult(TurnstileOutcome.REJECTED, "test-key-not-allowed")

        hostname = str(data.get("hostname") or "").lower()
        if hostname not in self._hostnames:
            return TurnstileResult(TurnstileOutcome.REJECTED, "hostname-mismatch")

        action = data.get("action")
        if action != self._action and not (is_test and action in (None, "")):
            return TurnstileResult(TurnstileOutcome.REJECTED, "action-mismatch")

        try:
            solved = datetime.fromisoformat(str(data.get("challenge_ts")).replace("Z", "+00:00"))
        except ValueError:
            return TurnstileResult(TurnstileOutcome.REJECTED, "bad-challenge-ts")
        if solved.tzinfo is None:
            solved = solved.replace(tzinfo=UTC)
        if now - solved > TOKEN_MAX_AGE:
            return TurnstileResult(TurnstileOutcome.REJECTED, "token-expired")
        return TurnstileResult(TurnstileOutcome.OK, "ok")
