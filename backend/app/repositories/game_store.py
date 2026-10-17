"""Redis storage for per-day game state, history, idempotency records, and the leaderboard.

All state changes go through three Lua scripts. Redis runs a script to completion before it
serves any other command, so each script is one atomic step: no other request can observe
or change the keys between its checks and its writes (ADR 0003). There is no
GET -> check -> INCR sequence in Python anywhere.

Keys (prefix `tenq:v1:`, `{d}` = UTC game date, `{p}` = keyed player hash):

    game:{d}:{p}      HASH  used, status, started_at_ms, finished_at_ms, lb_member,
                            lease_token, lease_until_ms, lease_qhash, lease_started_ms
    hist:{d}:{p}      LIST  JSON {"n", "q", "a", "t"} per charged question
    qset:{d}:{p}      SET   qhash of charged questions (duplicate detection)
    idem:{d}:{p}:{k}  HASH  state (pending|done), body, token, number, answer
    lb:{d}            ZSET  member "{finished_at_ms:013d}:{p}", score questions*1e9+duration_ms

Every key expires at 00:00 UTC two days after its game date (ADR 0004), set as a TTL from
the application clock: the day itself plus a
one-day grace period for requests that straddle midnight and for leaderboard reads.
"""

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import cast

from redis.asyncio import Redis

from app.models.game import (
    Answer,
    GameState,
    GameStatus,
    HistoryEntry,
    Leaderboard,
    LeaderboardEntry,
)

PREFIX = "tenq:v1"
GRACE_DAYS = 1

# Shared by reserve and commit: the expiry for every key a script touches. The TTL is
# computed from the application clock (expire_at(game_date) - now), so tests with a fixed
# clock behave like production.
_EXPIRE = """
local function expire_all(ttl)
  for i = 1, #KEYS do redis.call('EXPIRE', KEYS[i], ttl) end
end
"""

RESERVE_LUA = (
    _EXPIRE
    + """
-- KEYS: game, idem, qset
-- ARGV: now_ms, lease_ms, token, body_hash, qhash, max_questions, ttl_s
local now = tonumber(ARGV[1])
local idem_state = redis.call('HGET', KEYS[2], 'state')
if idem_state then
  if redis.call('HGET', KEYS[2], 'body') ~= ARGV[4] then
    return {'KEY_REUSED'}
  end
  if idem_state == 'done' then
    return {'REPLAY', redis.call('HGET', KEYS[2], 'number'), redis.call('HGET', KEYS[2], 'answer')}
  end
  -- pending: still in flight only if it owns the live lease; otherwise it is a leftover
  -- from a crashed request and may be retried for free.
  local lease = redis.call('HMGET', KEYS[1], 'lease_token', 'lease_until_ms')
  if lease[1] == redis.call('HGET', KEYS[2], 'token') and tonumber(lease[2] or '0') > now then
    return {'IN_PROGRESS'}
  end
  redis.call('DEL', KEYS[2])
end

local game = redis.call('HMGET', KEYS[1], 'status', 'used', 'lease_until_ms')
local status = game[1] or 'not_started'
local used = tonumber(game[2] or '0')
if status == 'won' then return {'FINISHED'} end
if status == 'lost' or used >= tonumber(ARGV[6]) then return {'LIMIT'} end
if tonumber(game[3] or '0') > now then return {'IN_PROGRESS'} end
if redis.call('SISMEMBER', KEYS[3], ARGV[5]) == 1 then return {'DUPLICATE'} end

redis.call('HSET', KEYS[1],
  'status', status, 'used', used,
  'lease_token', ARGV[3], 'lease_until_ms', now + tonumber(ARGV[2]),
  'lease_qhash', ARGV[5], 'lease_started_ms', now)
redis.call('HSET', KEYS[2], 'state', 'pending', 'body', ARGV[4], 'token', ARGV[3])
expire_all(tonumber(ARGV[7]))
return {'RESERVED'}
"""
)

COMMIT_LUA = (
    _EXPIRE
    + """
-- KEYS: game, idem, qset, hist, lb
-- ARGV: token, now_ms, answer, question, player_hash, max_questions, ttl_s
local now = tonumber(ARGV[2])
local g = redis.call('HMGET', KEYS[1], 'lease_token', 'lease_until_ms', 'used',
                     'lease_qhash', 'lease_started_ms', 'started_at_ms', 'status')
if g[1] ~= ARGV[1] or tonumber(g[2] or '0') < now then
  return {'STALE'}
end
if g[7] == 'won' or g[7] == 'lost' then return {'STALE'} end

local used = tonumber(g[3] or '0') + 1
local started = g[6]
if not started then
  -- The game clock starts with the first question that was actually processed.
  started = g[5]
  redis.call('HSET', KEYS[1], 'started_at_ms', started)
end

redis.call('RPUSH', KEYS[4], cjson.encode({n = used, q = ARGV[4], a = ARGV[3], t = now}))
redis.call('SADD', KEYS[3], g[4])

local status = 'in_progress'
if ARGV[3] == 'WIN' then
  status = 'won'
  local duration = now - tonumber(started)
  local member = string.format('%013d', now) .. ':' .. ARGV[5]
  redis.call('ZADD', KEYS[5], 'NX', used * 1000000000 + duration, member)
  redis.call('HSET', KEYS[1], 'finished_at_ms', now, 'lb_member', member)
elseif used >= tonumber(ARGV[6]) then
  status = 'lost'
  redis.call('HSET', KEYS[1], 'finished_at_ms', now)
end

redis.call('HSET', KEYS[1], 'used', used, 'status', status)
redis.call('HDEL', KEYS[1], 'lease_token', 'lease_until_ms', 'lease_qhash', 'lease_started_ms')
redis.call('HSET', KEYS[2], 'state', 'done', 'number', used, 'answer', ARGV[3])
redis.call('HDEL', KEYS[2], 'token')
expire_all(tonumber(ARGV[7]))
return {'OK', tostring(used), status}
"""
)

RELEASE_LUA = """
-- KEYS: game, idem   ARGV: token
if redis.call('HGET', KEYS[1], 'lease_token') == ARGV[1] then
  redis.call('HDEL', KEYS[1], 'lease_token', 'lease_until_ms', 'lease_qhash', 'lease_started_ms')
end
if redis.call('HGET', KEYS[2], 'token') == ARGV[1] then
  redis.call('DEL', KEYS[2])
end
return 1
"""


class ReserveOutcome(StrEnum):
    RESERVED = "RESERVED"
    REPLAY = "REPLAY"
    KEY_REUSED = "KEY_REUSED"
    IN_PROGRESS = "IN_PROGRESS"
    FINISHED = "FINISHED"
    LIMIT = "LIMIT"
    DUPLICATE = "DUPLICATE"


@dataclass(frozen=True, slots=True)
class ReserveResult:
    outcome: ReserveOutcome
    number: int | None = None
    answer: Answer | None = None


@dataclass(frozen=True, slots=True)
class CommitResult:
    committed: bool
    number: int = 0
    status: GameStatus = GameStatus.IN_PROGRESS


def expire_at(game_date: date) -> int:
    """Unix seconds of 00:00 UTC on game_date + 1 + GRACE_DAYS."""
    moment = datetime.combine(game_date + timedelta(days=1 + GRACE_DAYS), time.min, tzinfo=UTC)
    return int(moment.timestamp())


def ttl_seconds(game_date: date, now: datetime) -> int:
    """Seconds from `now` until the cleanup instant of `game_date` (at least 1)."""
    return max(1, expire_at(game_date) - int(now.timestamp()))


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _from_ms(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromtimestamp(int(value) / 1000, UTC)


class RedisGameStore:
    def __init__(self, redis: Redis, max_questions: int) -> None:
        self._redis = redis
        self._max = max_questions
        self._reserve = redis.register_script(RESERVE_LUA)
        self._commit = redis.register_script(COMMIT_LUA)
        self._release = redis.register_script(RELEASE_LUA)

    @staticmethod
    def keys(game_date: date, player_hash: str) -> dict[str, str]:
        d = game_date.isoformat()
        return {
            "game": f"{PREFIX}:game:{d}:{player_hash}",
            "hist": f"{PREFIX}:hist:{d}:{player_hash}",
            "qset": f"{PREFIX}:qset:{d}:{player_hash}",
            "lb": f"{PREFIX}:lb:{d}",
        }

    @staticmethod
    def idem_key(game_date: date, player_hash: str, key: str) -> str:
        return f"{PREFIX}:idem:{game_date.isoformat()}:{player_hash}:{key}"

    async def reserve(
        self,
        *,
        game_date: date,
        player_hash: str,
        idempotency_key: str,
        body_hash: str,
        qhash: str,
        token: str,
        now: datetime,
        lease_ms: int,
    ) -> ReserveResult:
        k = self.keys(game_date, player_hash)
        raw = cast(
            list[str],
            await self._reserve(
                keys=[k["game"], self.idem_key(game_date, player_hash, idempotency_key), k["qset"]],
                args=[
                    _ms(now),
                    lease_ms,
                    token,
                    body_hash,
                    qhash,
                    self._max,
                    ttl_seconds(game_date, now),
                ],
            ),
        )
        outcome = ReserveOutcome(raw[0])
        if outcome is ReserveOutcome.REPLAY:
            return ReserveResult(outcome, number=int(raw[1]), answer=Answer(raw[2]))
        return ReserveResult(outcome)

    async def commit(
        self,
        *,
        game_date: date,
        player_hash: str,
        idempotency_key: str,
        token: str,
        now: datetime,
        answer: Answer,
        question: str,
    ) -> CommitResult:
        k = self.keys(game_date, player_hash)
        raw = cast(
            list[str],
            await self._commit(
                keys=[
                    k["game"],
                    self.idem_key(game_date, player_hash, idempotency_key),
                    k["qset"],
                    k["hist"],
                    k["lb"],
                ],
                args=[
                    token,
                    _ms(now),
                    answer.value,
                    question,
                    player_hash,
                    self._max,
                    ttl_seconds(game_date, now),
                ],
            ),
        )
        if raw[0] != "OK":
            return CommitResult(committed=False)
        return CommitResult(committed=True, number=int(raw[1]), status=GameStatus(raw[2]))

    async def release(
        self, *, game_date: date, player_hash: str, idempotency_key: str, token: str
    ) -> None:
        k = self.keys(game_date, player_hash)
        await self._release(
            keys=[k["game"], self.idem_key(game_date, player_hash, idempotency_key)], args=[token]
        )

    async def get_state(self, game_date: date, player_hash: str, now: datetime) -> GameState:
        k = self.keys(game_date, player_hash)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hgetall(k["game"])
            pipe.lrange(k["hist"], 0, -1)
            game, hist = cast(tuple[dict[str, str], list[str]], tuple(await pipe.execute()))
        history = tuple(
            HistoryEntry(
                number=int(item["n"]),
                question=str(item["q"]),
                answer=Answer(item["a"]),
                asked_at=datetime.fromtimestamp(int(item["t"]) / 1000, UTC),
            )
            for item in (json.loads(h) for h in hist)
        )
        used = int(game.get("used", "0"))
        status = GameStatus(game.get("status", "not_started"))
        if status is GameStatus.NOT_STARTED and used > 0:  # pragma: no cover - defensive
            status = GameStatus.IN_PROGRESS
        lease_until = int(game.get("lease_until_ms", "0"))
        return GameState(
            game_date=game_date,
            status=status,
            used=used,
            in_progress=lease_until > _ms(now),
            started_at=_from_ms(game.get("started_at_ms")),
            finished_at=_from_ms(game.get("finished_at_ms")),
            history=history,
            max_questions=self._max,
        )

    async def leaderboard(
        self, game_date: date, limit: int, player_hash: str | None
    ) -> Leaderboard:
        lb_key = self.keys(game_date, "_")["lb"]
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.zrange(lb_key, 0, limit - 1, withscores=True)
            pipe.zcard(lb_key)
            if player_hash is not None:
                pipe.hget(self.keys(game_date, player_hash)["game"], "lb_member")
            results = await pipe.execute()
        top = cast(list[tuple[str, float]], results[0])
        total = int(results[1])
        entries = tuple(
            _entry(rank, member, score) for rank, (member, score) in enumerate(top, start=1)
        )
        me: LeaderboardEntry | None = None
        my_member = cast(str | None, results[2]) if player_hash is not None else None
        if my_member is not None:
            rank = await self._redis.zrank(lb_key, my_member)
            score = await self._redis.zscore(lb_key, my_member)
            if rank is not None and score is not None:
                me = _entry(int(rank) + 1, my_member, float(score))
        return Leaderboard(game_date=game_date, entries=entries, me=me, total_winners=total)


def _entry(rank: int, member: str, score: float) -> LeaderboardEntry:
    questions, duration = divmod(int(score), 1_000_000_000)
    return LeaderboardEntry(
        rank=rank, player_hash=member.split(":", 1)[1], questions=questions, duration_ms=duration
    )
