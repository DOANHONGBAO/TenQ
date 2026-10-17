"""Redis counters for anti-abuse: fixed-window rate limits, concurrency slots, token replay.

    rl:{scope}:{subject}:{window_start}   STRING  requests in that window (TTL = window)
    conc:{scope}:{subject}                STRING  requests currently in flight (safety TTL)
    tsreplay:{sha256(token)}              STRING  Turnstile token already presented (TTL 300 s)

Subjects are keyed hashes (player hash, daily IP hash), never raw IPs.
"""

import hashlib
from dataclasses import dataclass
from typing import cast

from redis.asyncio import Redis

from app.repositories.game_store import PREFIX

RATE_LUA = """
-- KEYS: counter   ARGV: limit, window_s
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
local ttl = redis.call('TTL', KEYS[1])
if count > tonumber(ARGV[1]) then return {0, ttl} end
return {1, ttl}
"""

ACQUIRE_LUA = """
-- KEYS: slot counter   ARGV: limit, safety_ttl_s
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
if current >= tonumber(ARGV[1]) then return 0 end
redis.call('INCR', KEYS[1])
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 1
"""

RELEASE_LUA = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
if current <= 1 then redis.call('DEL', KEYS[1]) else redis.call('DECR', KEYS[1]) end
return 1
"""


@dataclass(frozen=True, slots=True)
class RateDecision:
    allowed: bool
    retry_after_s: int


class AbuseStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._rate = redis.register_script(RATE_LUA)
        self._acquire = redis.register_script(ACQUIRE_LUA)
        self._release = redis.register_script(RELEASE_LUA)

    async def hit(
        self, scope: str, subject: str, limit: int, window_s: int, now_s: int
    ) -> RateDecision:
        """Count one request; atomically decide whether it is within the window's limit."""
        window_start = now_s - now_s % window_s
        key = f"{PREFIX}:rl:{scope}:{subject}:{window_start}"
        allowed, ttl = cast(list[int], await self._rate(keys=[key], args=[limit, window_s]))
        retry = max(1, int(ttl)) if int(ttl) > 0 else window_s
        return RateDecision(bool(allowed), retry)

    async def acquire_slot(self, scope: str, subject: str, limit: int, ttl_s: int) -> bool:
        key = f"{PREFIX}:conc:{scope}:{subject}"
        return bool(await self._acquire(keys=[key], args=[limit, ttl_s]))

    async def release_slot(self, scope: str, subject: str) -> None:
        await self._release(keys=[f"{PREFIX}:conc:{scope}:{subject}"])

    async def claim_token(self, token: str, ttl_s: int = 300) -> bool:
        """False if this exact Turnstile token was presented before (replay)."""
        digest = hashlib.sha256(token.encode()).hexdigest()
        key = f"{PREFIX}:tsreplay:{digest}"
        return bool(await self._redis.set(key, "1", nx=True, ex=ttl_s))
