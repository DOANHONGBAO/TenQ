"""Anonymous session cookie and keyed player hash (ADR 0006, minimal version).

Cookie value: `<player_id>.<issued_at>.<signature>` where player_id is 128 random bits
(base64url) and signature = HMAC-SHA256(cookie_key, player_id + "." + issued_at).
Only `player_hash = HMAC-SHA256(hash_key, player_id)[:32]` is ever stored or used as an
identifier, so Redis and the leaderboard never see the raw id.

Turnstile verification and key rotation arrive in Phase 06.
"""

import base64
import hashlib
import hmac
import secrets

COOKIE_NAME = "tenq_sid"
COOKIE_MAX_AGE_S = 365 * 24 * 3600


def _derive(secret: bytes, label: str) -> bytes:
    return hmac.new(secret, label.encode(), hashlib.sha256).digest()


class SessionCodec:
    def __init__(self, secret: bytes) -> None:
        if len(secret) < 32:
            raise ValueError("session secret must be at least 32 bytes")
        self._cookie_key = _derive(secret, "tenq:v1:cookie")
        self._hash_key = _derive(secret, "tenq:v1:player-hash")

    def _sign(self, payload: str) -> str:
        digest = hmac.new(self._cookie_key, payload.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    def issue(self, issued_at_s: int) -> tuple[str, str]:
        """Return (cookie_value, player_id) for a brand-new anonymous player."""
        player_id = base64.urlsafe_b64encode(secrets.token_bytes(16)).rstrip(b"=").decode()
        payload = f"{player_id}.{issued_at_s}"
        return f"{payload}.{self._sign(payload)}", player_id

    def verify(self, cookie_value: str | None) -> str | None:
        """Return the player id if the cookie is authentic, else None."""
        if not cookie_value or len(cookie_value) > 200:
            return None
        parts = cookie_value.split(".")
        if len(parts) != 3 or not parts[1].isdigit():
            return None
        payload = f"{parts[0]}.{parts[1]}"
        if not hmac.compare_digest(parts[2], self._sign(payload)):
            return None
        return parts[0]

    def player_hash(self, player_id: str) -> str:
        return hmac.new(self._hash_key, player_id.encode(), hashlib.sha256).hexdigest()[:32]
