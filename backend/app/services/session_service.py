"""Use case: start an anonymous session after a Turnstile check.

Order matters: cheap local checks first (existing session, rate limits, token replay),
the network call to Cloudflare last. Every failure path is closed: no cookie is issued
unless Siteverify returned a fully checked success.
"""

import logging
from dataclasses import dataclass

from redis.exceptions import RedisError

from app.core.errors import RateLimitedError, ServiceUnavailableError, TurnstileFailedError
from app.core.session import Identifiers, SessionCodec
from app.integrations.turnstile import TurnstileOutcome, TurnstileVerifier
from app.models.clock import Clock
from app.models.game import display_name_for
from app.repositories.abuse_store import AbuseStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ClientContext:
    """What the API knows about the caller for abuse decisions. No raw IP is stored."""

    ip: str
    ip_hash: str
    device_hash: str  # ip_hash + user agent: separates devices behind one NAT
    trusted_proxy: bool


@dataclass(frozen=True, slots=True)
class SessionLimits:
    per_ip_hour: int
    per_device_hour: int


@dataclass(frozen=True, slots=True)
class NewSession:
    cookie_value: str
    display_name: str


class SessionService:
    def __init__(
        self,
        codec: SessionCodec,
        identifiers: Identifiers,
        verifier: TurnstileVerifier,
        abuse: AbuseStore,
        clock: Clock,
        limits: SessionLimits,
        replay_guard: bool = True,
    ) -> None:
        """`replay_guard=False` only with Cloudflare test keys, which reuse one dummy token."""
        self._codec = codec
        self._ids = identifiers
        self._verifier = verifier
        self._abuse = abuse
        self._clock = clock
        self._limits = limits
        self._replay_guard = replay_guard

    async def create(self, token: str, client: ClientContext) -> NewSession:
        now = self._clock.now()
        now_s = int(now.timestamp())
        try:
            for scope, subject, limit in (
                ("session-ip", client.ip_hash, self._limits.per_ip_hour),
                ("session-device", client.device_hash, self._limits.per_device_hour),
            ):
                decision = await self._abuse.hit(scope, subject, limit, 3600, now_s)
                if not decision.allowed:
                    raise RateLimitedError(decision.retry_after_s)
            if token and self._replay_guard and not await self._abuse.claim_token(token):
                logger.info("turnstile token replay refused")
                raise TurnstileFailedError()
        except RedisError as exc:
            raise ServiceUnavailableError() from exc

        result = await self._verifier.verify(token, client.ip, now)
        if result.outcome is TurnstileOutcome.UNAVAILABLE:
            logger.warning("turnstile unavailable (%s); failing closed", result.reason)
            raise ServiceUnavailableError()
        if result.outcome is TurnstileOutcome.REJECTED:
            logger.info("turnstile rejected: %s", result.reason)
            raise TurnstileFailedError()

        value, player_id = self._codec.issue(now_s)
        return NewSession(value, display_name_for(self._ids.player_hash(player_id)))
