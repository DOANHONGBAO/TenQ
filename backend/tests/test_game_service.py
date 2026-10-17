"""GameService against a real Redis and the fake judge (ADR 0003 critical cases)."""

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from redis.asyncio import Redis

from app.core.errors import (
    AIInvalidResponseError,
    AIUnavailableError,
    AttemptLimitReachedError,
    DuplicateQuestionError,
    GameFinishedError,
    IdempotencyKeyReusedError,
    QuestionInProgressError,
    ServiceUnavailableError,
)
from app.integrations.ai_judge import AIJudgeError, FakeAIJudge
from app.models.clock import FixedClock
from app.models.game import MAX_QUESTIONS, Answer, GameStatus
from app.repositories.game_store import RedisGameStore, expire_at
from app.services.daily_word_service import DailyWordService
from app.services.game_service import GameService
from tests.conftest import JUDGE_TIMEOUT_S, LEASE_MS, TEST_REDIS_URL

pytestmark = pytest.mark.anyio

PLAYER = "a" * 32


def key() -> str:
    return str(uuid.uuid4())


def q(n: int) -> str:
    return f"Is it question number {n}?"


async def test_first_question_starts_the_game(game_service: GameService) -> None:
    before = await game_service.state(PLAYER)
    assert before.status is GameStatus.NOT_STARTED and before.used == 0

    result = await game_service.ask(PLAYER, q(1), key())

    assert (result.number, result.answer) == (1, Answer.NO)
    assert result.game.status is GameStatus.IN_PROGRESS
    assert result.game.used == 1 and result.game.remaining == 9
    assert result.game.started_at is not None


async def test_two_concurrent_requests_charge_once(
    game_service: GameService, judge: FakeAIJudge
) -> None:
    judge.gate = asyncio.Event()
    first = asyncio.create_task(game_service.ask(PLAYER, q(1), key()))
    await asyncio.sleep(0.05)  # first request now holds the lease and waits for the judge

    with pytest.raises(QuestionInProgressError):
        await game_service.ask(PLAYER, q(2), key())  # a different request id
    judge.gate.set()
    await first

    state = await game_service.state(PLAYER)
    assert state.used == 1
    assert judge.calls == 1


async def test_fifty_concurrent_requests_never_exceed_ten(game_service: GameService) -> None:
    outcomes: list[str] = []

    async def player_tab(n: int) -> None:
        idem = key()
        while True:
            try:
                await game_service.ask(PLAYER, q(n), idem)
                outcomes.append("charged")
                return
            except QuestionInProgressError:
                await asyncio.sleep(0)  # another tab holds the lease; retry the same request
            except (AttemptLimitReachedError, GameFinishedError):
                outcomes.append("refused")
                return

    await asyncio.gather(*(player_tab(n) for n in range(50)))

    state = await game_service.state(PLAYER)
    assert outcomes.count("charged") == MAX_QUESTIONS
    assert outcomes.count("refused") == 40
    assert state.used == MAX_QUESTIONS and state.status is GameStatus.LOST
    assert [h.number for h in state.history] == list(range(1, 11))


async def test_fifty_concurrent_lua_reservations_grant_one_lease(
    store: RedisGameStore, clock: FixedClock
) -> None:
    day = clock.now().date()
    results = await asyncio.gather(
        *(
            store.reserve(
                game_date=day,
                player_hash=PLAYER,
                idempotency_key=key(),
                body_hash=f"b{i}",
                qhash=f"q{i}",
                token=f"t{i}",
                now=clock.now(),
                lease_ms=LEASE_MS,
            )
            for i in range(50)
        )
    )
    assert sum(r.outcome == "RESERVED" for r in results) == 1
    assert sum(r.outcome == "IN_PROGRESS" for r in results) == 49


async def test_retry_with_same_request_id_is_not_charged_twice(
    game_service: GameService, judge: FakeAIJudge
) -> None:
    idem = key()
    first = await game_service.ask(PLAYER, q(1), idem)
    retry = await game_service.ask(PLAYER, q(1), idem)

    assert retry.replayed and not first.replayed
    assert (retry.number, retry.answer) == (first.number, first.answer)
    assert (await game_service.state(PLAYER)).used == 1
    assert judge.calls == 1


async def test_retry_while_pending_is_in_progress(
    game_service: GameService, judge: FakeAIJudge
) -> None:
    judge.gate = asyncio.Event()
    idem = key()
    first = asyncio.create_task(game_service.ask(PLAYER, q(1), idem))
    await asyncio.sleep(0.05)

    with pytest.raises(QuestionInProgressError):
        await game_service.ask(PLAYER, q(1), idem)
    judge.gate.set()
    await first
    assert (await game_service.ask(PLAYER, q(1), idem)).replayed


async def test_same_request_id_with_different_question_is_rejected(
    game_service: GameService,
) -> None:
    idem = key()
    await game_service.ask(PLAYER, q(1), idem)
    with pytest.raises(IdempotencyKeyReusedError):
        await game_service.ask(PLAYER, q(2), idem)


async def test_duplicate_question_is_refused_for_free(game_service: GameService) -> None:
    await game_service.ask(PLAYER, "Is it alive?", key())
    with pytest.raises(DuplicateQuestionError):
        await game_service.ask(PLAYER, "  is it ALIVE ? ", key())
    assert (await game_service.state(PLAYER)).used == 1


async def test_judge_failure_is_free_and_retryable(
    game_service: GameService, judge: FakeAIJudge
) -> None:
    judge.queue(AIJudgeError("provider down"))
    idem = key()
    with pytest.raises(AIUnavailableError):
        await game_service.ask(PLAYER, q(1), idem)
    assert (await game_service.state(PLAYER)).used == 0

    result = await game_service.ask(PLAYER, q(1), idem)  # same key, now succeeds
    assert result.number == 1 and not result.replayed


async def test_judge_timeout_is_free(
    store: RedisGameStore,
    word_service: DailyWordService,
    clock: FixedClock,
) -> None:
    slow = FakeAIJudge(delay_s=0.5)
    service = GameService(store, word_service, slow, clock, lease_ms=1000, judge_timeout_s=0.1)
    with pytest.raises(AIUnavailableError):
        await service.ask(PLAYER, q(1), key())
    state = await service.state(PLAYER)
    assert state.used == 0 and not state.in_progress


async def test_unverifiable_win_is_not_charged(
    game_service: GameService, judge: FakeAIJudge
) -> None:
    judge.queue(Answer.WIN)  # the question does not name the word
    with pytest.raises(AIInvalidResponseError):
        await game_service.ask(PLAYER, q(1), key())
    assert (await game_service.state(PLAYER)).used == 0


async def test_win_on_tenth_question(
    game_service: GameService, word_service: DailyWordService
) -> None:
    for n in range(1, 10):
        await game_service.ask(PLAYER, q(n), key())
    word = word_service.puzzle_for_today().word

    result = await game_service.ask(PLAYER, f"Is it a {word}?", key())

    assert result.answer is Answer.WIN and result.number == 10
    assert result.game.status is GameStatus.WON and result.game.remaining == 0
    board = await game_service.leaderboard(50, PLAYER)
    assert board.total_winners == 1 and board.me is not None and board.me.questions == 10
    with pytest.raises(GameFinishedError):
        await game_service.ask(PLAYER, q(11), key())


async def test_ten_misses_lose_and_block_further_questions(game_service: GameService) -> None:
    for n in range(1, 11):
        await game_service.ask(PLAYER, q(n), key())
    state = await game_service.state(PLAYER)
    assert state.status is GameStatus.LOST and state.finished_at is not None
    with pytest.raises(AttemptLimitReachedError):
        await game_service.ask(PLAYER, q(11), key())
    assert (await game_service.leaderboard(50, PLAYER)).me is None


async def test_every_non_win_answer_costs_one(
    game_service: GameService, judge: FakeAIJudge
) -> None:
    judge.queue(Answer.YES, Answer.NO, Answer.IRRELEVANT, Answer.PENALTY)
    for n in range(1, 5):
        await game_service.ask(PLAYER, q(n), key())
    state = await game_service.state(PLAYER)
    assert state.used == 4
    assert [h.answer for h in state.history] == [
        Answer.YES,
        Answer.NO,
        Answer.IRRELEVANT,
        Answer.PENALTY,
    ]


async def test_restart_keeps_state_and_recovers_crashed_request(
    game_service: GameService,
    word_service: DailyWordService,
    clock: FixedClock,
    redis: Redis,
) -> None:
    await game_service.ask(PLAYER, q(1), key())

    # A request reserved a lease and then the process died before commit.
    store = RedisGameStore(redis, MAX_QUESTIONS)
    crashed_key = key()
    await store.reserve(
        game_date=clock.now().date(),
        player_hash=PLAYER,
        idempotency_key=crashed_key,
        body_hash="x",
        qhash="y",
        token="dead",
        now=clock.now(),
        lease_ms=LEASE_MS,
    )

    # "Restart": brand-new client, store, and service objects.
    fresh_redis = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    restarted = GameService(
        RedisGameStore(fresh_redis, MAX_QUESTIONS),
        word_service,
        FakeAIJudge(),
        clock,
        lease_ms=LEASE_MS,
        judge_timeout_s=JUDGE_TIMEOUT_S,
    )
    state = await restarted.state(PLAYER)
    assert state.used == 1 and state.in_progress
    with pytest.raises(QuestionInProgressError):
        await restarted.ask(PLAYER, q(2), key())

    clock.set(clock.now() + timedelta(milliseconds=LEASE_MS + 1))  # the dead lease expires
    result = await restarted.ask(PLAYER, q(2), key())
    assert result.number == 2  # the crashed request was never charged
    await fresh_redis.aclose()


async def test_redis_down_returns_service_unavailable(
    word_service: DailyWordService, clock: FixedClock
) -> None:
    dead = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)
    service = GameService(
        RedisGameStore(dead, MAX_QUESTIONS),
        word_service,
        FakeAIJudge(),
        clock,
        lease_ms=LEASE_MS,
        judge_timeout_s=JUDGE_TIMEOUT_S,
    )
    with pytest.raises(ServiceUnavailableError):
        await service.ask(PLAYER, q(1), key())
    with pytest.raises(ServiceUnavailableError):
        await service.state(PLAYER)
    with pytest.raises(ServiceUnavailableError):
        await service.leaderboard(10, None)
    await dead.aclose()


async def test_redis_failure_at_commit_does_not_charge(
    game_service: GameService,
    store: RedisGameStore,
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from redis.exceptions import ConnectionError as RedisConnectionError

    async def broken_commit(**_: object) -> None:
        raise RedisConnectionError("connection reset")

    monkeypatch.setattr(store, "commit", broken_commit)
    with pytest.raises(ServiceUnavailableError):
        await game_service.ask(PLAYER, q(1), key())
    monkeypatch.undo()

    clock.set(clock.now() + timedelta(milliseconds=LEASE_MS + 1))
    state = await game_service.state(PLAYER)
    assert state.used == 0 and not state.in_progress


async def test_midnight_during_request_commits_to_the_starting_day(
    game_service: GameService, judge: FakeAIJudge, clock: FixedClock
) -> None:
    day = date(2026, 10, 17)
    clock.set(datetime(2026, 10, 17, 23, 59, 59, 900_000, tzinfo=UTC))
    judge.gate = asyncio.Event()
    pending = asyncio.create_task(game_service.ask(PLAYER, q(1), key()))
    await asyncio.sleep(0.05)

    clock.set(datetime(2026, 10, 18, 0, 0, 0, 100_000, tzinfo=UTC))  # reset happens mid-request
    judge.gate.set()
    result = await pending

    assert result.game.game_date == day and result.game.used == 1
    assert (await game_service.state(PLAYER, day)).used == 1
    new_day = await game_service.state(PLAYER)
    assert new_day.game_date == date(2026, 10, 18)
    assert new_day.status is GameStatus.NOT_STARTED and new_day.used == 0


async def test_new_day_starts_fresh(game_service: GameService, clock: FixedClock) -> None:
    for n in range(1, 11):
        await game_service.ask(PLAYER, q(n), key())
    clock.set(datetime(2026, 10, 18, 0, 0, tzinfo=UTC))

    state = await game_service.state(PLAYER)
    assert state.status is GameStatus.NOT_STARTED and state.used == 0
    assert (await game_service.ask(PLAYER, q(1), key())).number == 1


async def test_keys_expire_at_reset_plus_grace(
    game_service: GameService, redis: Redis, clock: FixedClock
) -> None:
    idem = key()
    await game_service.ask(PLAYER, q(1), idem)
    deadline = int(datetime(2026, 10, 19, tzinfo=UTC).timestamp())
    assert expire_at(date(2026, 10, 17)) == deadline
    expected_ttl = deadline - int(clock.now().timestamp())  # 36 h from 12:00 on day 1
    keys = RedisGameStore.keys(date(2026, 10, 17), PLAYER)
    names = [keys["game"], keys["hist"], keys["qset"]]
    names.append(RedisGameStore.idem_key(date(2026, 10, 17), PLAYER, idem))
    for name in names:
        assert expected_ttl - 5 <= await redis.ttl(name) <= expected_ttl


async def test_leaderboard_ordering_and_tie_breaking(
    game_service: GameService, word_service: DailyWordService, clock: FixedClock
) -> None:
    word = word_service.puzzle_for_today().word
    win = f"Is it a {word}?"
    t0 = datetime(2026, 10, 17, 8, 0, tzinfo=UTC)

    async def play(player: str, misses: int, start: datetime, step_s: int) -> None:
        clock.set(start)
        for n in range(misses):
            await game_service.ask(player, q(n), key())
            clock.set(clock.now() + timedelta(seconds=step_s))
        await game_service.ask(player, win, key())

    # Two questions, slow / fast; one question; and an exact tie with "fast" finishing later.
    await play("b" * 32, misses=1, start=t0, step_s=60)  # 2 questions, 60 s
    await play("c" * 32, misses=1, start=t0, step_s=10)  # 2 questions, 10 s
    await play("d" * 32, misses=0, start=t0, step_s=0)  # 1 question, 0 s
    await play("e" * 32, misses=1, start=t0 + timedelta(hours=1), step_s=10)  # tie with c

    board = await game_service.leaderboard(10, "e" * 32)
    order = [(e.player_hash[0], e.questions, e.duration_ms) for e in board.entries]
    assert order == [("d", 1, 0), ("c", 2, 10_000), ("e", 2, 10_000), ("b", 2, 60_000)]
    assert board.me is not None and board.me.rank == 3
    assert [e.rank for e in board.entries] == [1, 2, 3, 4]
    assert all(e.display_name.startswith("Player-") for e in board.entries)
