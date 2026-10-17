"""Anonymous session cookie and keyed identifiers (ADR 0006).

Cookie `tenq_sid` = `<player_id>.<issued_at>.<signature>`:

- `player_id`: 128 bits from `secrets.token_bytes`, base64url (no account, no PII).
- `issued_at`: Unix seconds; sessions expire after COOKIE_MAX_AGE_S even if a client keeps
  the cookie longer, and timestamps from the future are rejected.
- `signature`: HMAC-SHA256 over `player_id.issued_at` with a cookie key derived from
  `TENQ_SESSION_SECRET`. Verification also accepts keys derived from
  `TENQ_SESSION_SECRET_PREVIOUS`, so the signing secret can be rotated without logging
  everyone out; such cookies are re-signed with the current key on their next request.

Stored identifiers never contain the raw id: `player_hash = HMAC(player_hash_key, player_id)`.
The player hash key is separate from the cookie secret, so rotating the cookie secret does
not change anyone's game state or leaderboard entry. IP addresses are reduced to a daily
`ip_hash = HMAC(ip_key, date | ip)` used only for rate limiting.
"""

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import date

COOKIE_NAME = "tenq_sid"
COOKIE_MAX_AGE_S = 365 * 24 * 3600
MAX_CLOCK_SKEW_S = 300
_MAX_COOKIE_LENGTH = 200


def _derive(secret: bytes, label: str) -> bytes:
    return hmac.new(secret, label.encode(), hashlib.sha256).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@dataclass(frozen=True, slots=True)
class VerifiedSession:
    player_id: str
    issued_at_s: int
    needs_reissue: bool  # signed with a previous key: re-sign with the current one


class SessionCodec:
    def __init__(self, current_secret: bytes, previous_secrets: tuple[bytes, ...] = ()) -> None:
        for secret in (current_secret, *previous_secrets):
            if len(secret) < 32:
                raise ValueError("session secrets must be at least 32 bytes")
        self._current = _derive(current_secret, "tenq:v1:cookie")
        self._previous = tuple(_derive(s, "tenq:v1:cookie") for s in previous_secrets)

    @staticmethod
    def _sign(key: bytes, payload: str) -> str:
        return _b64(hmac.new(key, payload.encode(), hashlib.sha256).digest())

    def issue(self, issued_at_s: int, player_id: str | None = None) -> tuple[str, str]:
        """Return (cookie_value, player_id). A new random id unless one is being re-signed."""
        player_id = player_id or _b64(secrets.token_bytes(16))
        payload = f"{player_id}.{issued_at_s}"
        return f"{payload}.{self._sign(self._current, payload)}", player_id

    def verify(self, cookie_value: str | None, now_s: int) -> VerifiedSession | None:
        """Return the session if the cookie is authentic and not expired, else None."""
        if not cookie_value or len(cookie_value) > _MAX_COOKIE_LENGTH:
            return None
        parts = cookie_value.split(".")
        if len(parts) != 3 or not parts[1].isdigit() or len(parts[0]) != 22:
            return None
        player_id, issued_raw, signature = parts
        issued_at = int(issued_raw)
        if issued_at > now_s + MAX_CLOCK_SKEW_S or now_s - issued_at > COOKIE_MAX_AGE_S:
            return None
        payload = f"{player_id}.{issued_raw}"
        if hmac.compare_digest(signature, self._sign(self._current, payload)):
            return VerifiedSession(player_id, issued_at, needs_reissue=False)
        for key in self._previous:
            if hmac.compare_digest(signature, self._sign(key, payload)):
                return VerifiedSession(player_id, issued_at, needs_reissue=True)
        return None


class Identifiers:
    """Keyed, one-way identifiers derived from TENQ_PLAYER_HASH_KEY."""

    def __init__(self, player_hash_key: bytes) -> None:
        if len(player_hash_key) < 32:
            raise ValueError("player hash key must be at least 32 bytes")
        self._player_key = _derive(player_hash_key, "tenq:v1:player-hash")
        self._ip_key = _derive(player_hash_key, "tenq:v1:ip-hash")
        self._ua_key = _derive(player_hash_key, "tenq:v1:ua-hash")

    def player_hash(self, player_id: str) -> str:
        return hmac.new(self._player_key, player_id.encode(), hashlib.sha256).hexdigest()[:32]

    def ip_hash(self, ip: str, day: date) -> str:
        """Daily-rotating: the same IP gives unrelated hashes on different days."""
        message = f"{day.isoformat()}|{ip}".encode()
        return hmac.new(self._ip_key, message, hashlib.sha256).hexdigest()[:32]

    def ua_hash(self, user_agent: str, day: date) -> str:
        message = f"{day.isoformat()}|{user_agent[:512]}".encode()
        return hmac.new(self._ua_key, message, hashlib.sha256).hexdigest()[:16]
