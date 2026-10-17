"""Redis storage for the shared daily judgement cache, stampede locks, and the AI budget.

    judge:{d}:{key}        STRING  validated label, shared by all players for that day
    judgelock:{d}:{key}    STRING  short-lived lock: one process computes a missing entry
    aibudget:day:{d}       STRING  AI HTTP attempts made on UTC day d
    aibudget:hour:{d}T{h}  STRING  AI HTTP attempts in that UTC hour

`key` = SHA-256(date | puzzle_id | normalized question | prompt version | model). It
contains no player data and does not reveal the word.
"""

import hashlib
from datetime import date, datetime, timedelta
from typing import cast

from redis.asyncio import Redis

from app.models.game import Answer
from app.repositories.game_store import PREFIX, ttl_seconds

BUDGET_LUA = """
-- KEYS: day, hour   ARGV: day_limit, hour_limit, day_ttl_s, hour_ttl_s
local day = tonumber(redis.call('GET', KEYS[1]) or '0')
local hour = tonumber(redis.call('GET', KEYS[2]) or '0')
if day >= tonumber(ARGV[1]) then return 'DAY' end
if hour >= tonumber(ARGV[2]) then return 'HOUR' end
redis.call('INCR', KEYS[1])
redis.call('INCR', KEYS[2])
redis.call('EXPIRE', KEYS[1], ARGV[3])
redis.call('EXPIRE', KEYS[2], ARGV[4])
return 'OK'
"""

RELEASE_LOCK_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
"""


def cache_key(
    game_date: date, puzzle_id: str, normalized_question: str, prompt_version: str, model: str
) -> str:
    material = "\n".join(
        [game_date.isoformat(), puzzle_id, normalized_question, prompt_version, model]
    )
    return hashlib.sha256(material.encode()).hexdigest()


class JudgeCache:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._budget = redis.register_script(BUDGET_LUA)
        self._release_lock = redis.register_script(RELEASE_LOCK_LUA)

    @staticmethod
    def _entry(game_date: date, key: str) -> str:
        return f"{PREFIX}:judge:{game_date.isoformat()}:{key}"

    @staticmethod
    def _lock(game_date: date, key: str) -> str:
        return f"{PREFIX}:judgelock:{game_date.isoformat()}:{key}"

    async def get(self, game_date: date, key: str) -> Answer | None:
        value = cast(str | None, await self._redis.get(self._entry(game_date, key)))
        return None if value is None else Answer(value)

    async def set(self, game_date: date, key: str, answer: Answer, now: datetime) -> None:
        """Store a validated label. NX: the first validated answer of the day wins."""
        await self._redis.set(
            self._entry(game_date, key), answer.value, nx=True, ex=ttl_seconds(game_date, now)
        )

    async def acquire_lock(self, game_date: date, key: str, token: str, ttl_ms: int) -> bool:
        return bool(await self._redis.set(self._lock(game_date, key), token, nx=True, px=ttl_ms))

    async def release_lock(self, game_date: date, key: str, token: str) -> None:
        await self._release_lock(keys=[self._lock(game_date, key)], args=[token])

    async def take_budget(self, now: datetime, day_limit: int, hour_limit: int) -> str:
        """Atomically count one AI call if both budgets allow it. Returns OK, DAY, or HOUR."""
        day = now.date()
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        hour_key = f"{PREFIX}:aibudget:hour:{hour_start.strftime('%Y-%m-%dT%H')}"
        result = await self._budget(
            keys=[f"{PREFIX}:aibudget:day:{day.isoformat()}", hour_key],
            args=[
                day_limit,
                hour_limit,
                ttl_seconds(day, now),
                max(1, int((hour_start + timedelta(hours=2) - now).total_seconds())),
            ],
        )
        return cast(str, result)

    async def usage(self, now: datetime) -> tuple[int, int]:
        day = now.date()
        hour_key = f"{PREFIX}:aibudget:hour:{now.strftime('%Y-%m-%dT%H')}"
        values = await self._redis.mget(f"{PREFIX}:aibudget:day:{day.isoformat()}", hour_key)
        return int(values[0] or 0), int(values[1] or 0)
