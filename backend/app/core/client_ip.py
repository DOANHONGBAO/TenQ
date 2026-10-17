"""Which client IP may the API trust? (Proxy trust, docs/security-threat-model.md T-05.)

Production path: browser -> Vercel (external rewrite) -> Nginx -> API. Vercel overwrites
`X-Forwarded-For` / `X-Real-IP` with the visitor's IP and does not forward client-supplied
values, and a vercel.json `routes` transform sets `X-Origin-Secret` on every proxied request
(a client cannot supply its own: the `set` operation replaces it).

Anyone can also connect to the Oracle origin directly and send any headers. So forwarded IP
headers are used only when the request carries a valid origin secret. Otherwise the TCP peer
address is the only trustworthy value. When `TENQ_ORIGIN_SECRETS` is configured (required in
production), requests without a valid secret are refused before they reach a route.
"""

import hmac
import ipaddress
from collections.abc import Sequence
from dataclasses import dataclass

ORIGIN_SECRET_HEADER = "x-origin-secret"  # noqa: S105 - a header name, not a secret
FORWARDED_IP_HEADER = "x-real-ip"


@dataclass(frozen=True, slots=True)
class ClientIP:
    ip: str
    trusted_proxy: bool  # True only if the forwarded IP came through the verified proxy


def origin_secret_valid(presented: str | None, secrets: Sequence[str]) -> bool:
    if not presented or len(presented) > 256:
        return False
    # Compare against every configured secret (current and previous) in constant time.
    matches = [hmac.compare_digest(presented.encode(), s.encode()) for s in secrets]
    return any(matches)


def _parse_ip(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.split(",")[0].strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def resolve_client_ip(
    peer_ip: str | None,
    headers: dict[str, str],
    origin_secrets: Sequence[str],
) -> ClientIP:
    """Forwarded IP only behind a verified proxy; otherwise the socket peer address."""
    if origin_secrets and origin_secret_valid(headers.get(ORIGIN_SECRET_HEADER), origin_secrets):
        forwarded = _parse_ip(headers.get(FORWARDED_IP_HEADER)) or _parse_ip(
            headers.get("x-forwarded-for")
        )
        if forwarded is not None:
            return ClientIP(forwarded, trusted_proxy=True)
    return ClientIP(_parse_ip(peer_ip) or "0.0.0.0", trusted_proxy=False)  # noqa: S104 - a label, not a bind address
