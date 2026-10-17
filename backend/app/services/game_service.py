"""Use case: play today's game (ask a question, read state, read the leaderboard).

One question goes through reserve -> judge -> commit (or release):

1. Validate the text (no Redis, no AI) and fix the UTC game date for the whole request.
2. `reserve` (one atomic Lua script) checks the idempotency key, finished/limit, the
   single in-flight lease, and duplicates, then grants a lease. Nothing is charged yet.
3. Ask the judge outside Redis. Failures and unverifiable WINs `release` the lease: free.
4. `commit` (one atomic Lua script) charges exactly one attempt if the lease is still ours.

Clients only send the question text. Attempts, status, and timing come from Redis and the
server clock, never from the payload.
"""

import asyncio
import hashlib
import logging
import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime

from redis.exceptions import RedisError

from app.core.errors import (
    AIInvalidResponseError,
    AIUnavailableError,
    AttemptLimitReachedError,
    DuplicateQuestionError,
    GameFinishedError,
    IdempotencyKeyReusedError,
    InvalidGuessAppError,
    InvalidQuestionAppError,
    QuestionInProgressError,
    ServiceUnavailableError,
)
from app.integrations.ai_judge import (
    AIJudge,
    AIJudgeError,
    JudgeContext,
    JudgeInvalidOutputError,
)
from app.models.clock import Clock, game_date_at
from app.models.game import Answer, AttemptKind, GameState, Leaderboard
from app.models.guess import InvalidGuessError, guess_is_correct, parse_guess
from app.models.hints import visible_hint_count
from app.models.question import InvalidQuestionError, mentions_word, parse_question
from app.repositories.game_store import RedisGameStore, ReserveOutcome
from app.services.daily_word_service import DailyWordService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Attempt:
    game_date: date
    player_hash: str
    idempotency_key: str
    token: str


@dataclass(frozen=True, slots=True)
class AskResult:
    number: int
    answer: Answer
    game: GameState
    replayed: bool


class GameService:
    def __init__(
        self,
        store: RedisGameStore,
        words: DailyWordService,
        judge: AIJudge,
        clock: Clock,
        lease_ms: int,
        judge_timeout_s: float,
    ) -> None:
        if judge_timeout_s * 1000 >= lease_ms:
            raise ValueError("the lease must outlast the judge timeout (ADR 0003)")
        self._store = store
        self._words = words
        self._judge = judge
        self._clock = clock
        self._lease_ms = lease_ms
        self._judge_timeout_s = judge_timeout_s

    def now(self) -> datetime:
        return self._clock.now()

    def today(self) -> date:
        return game_date_at(self._clock.now())

    async def state(self, player_hash: str, game_date: date | None = None) -> GameState:
        day = game_date or self.today()
        try:
            raw = await self._store.get_state(day, player_hash, self._clock.now())
        except RedisError as exc:
            raise _unavailable(exc) from exc
        return self._with_hints(raw)

    def _with_hints(self, game: GameState) -> GameState:
        """Attach the hints this player has unlocked; the server decides how many."""
        visible = visible_hint_count(game.used)
        if visible == 0:
            return game
        entry = self._words.entry_for(self._words.puzzle_for(game.game_date))
        hints = entry.hints[:visible] if entry is not None else ()
        return replace(game, hints=hints)

    async def leaderboard(self, limit: int, player_hash: str | None) -> Leaderboard:
        try:
            return await self._store.leaderboard(self.today(), limit, player_hash)
        except RedisError as exc:
            raise _unavailable(exc) from exc

    async def ask(self, player_hash: str, raw_question: str, idempotency_key: str) -> AskResult:
        try:
            question = parse_question(raw_question)
        except InvalidQuestionError as exc:
            raise InvalidQuestionAppError(details={"reason": exc.reason}) from exc

        # The game date is fixed here: a request that crosses midnight still belongs to the
        # day it started on, and its commit writes only that day's keys (ADR 0004).
        game_date = self.today()
        puzzle = self._words.puzzle_for(game_date)
        context = JudgeContext(
            game_date=game_date,
            word=puzzle.word,
            entry=self._words.entry_for(puzzle),
            puzzle_id=hashlib.sha256(
                f"{game_date.isoformat()}|{puzzle.word_list_sha256}|{puzzle.selection_version}".encode()
            ).hexdigest()[:32],
        )
        attempt = _Attempt(game_date, player_hash, idempotency_key, uuid.uuid4().hex)
        replay = await self._reserve(attempt, f"q:{question.text}", question.qhash)
        if replay is not None:
            return replay

        try:
            answer = await asyncio.wait_for(
                self._judge.judge(context, question), timeout=self._judge_timeout_s
            )
        except JudgeInvalidOutputError as exc:
            await self._safe_release(attempt)
            logger.warning("judge output rejected: %s", exc)
            raise AIInvalidResponseError() from exc
        except (AIJudgeError, TimeoutError) as exc:
            await self._safe_release(attempt)
            logger.warning("judge unavailable: %s", type(exc).__name__)
            raise AIUnavailableError() from exc
        except BaseException:
            await self._safe_release(attempt)
            raise

        if answer is Answer.WIN and not mentions_word(question, puzzle.word):
            await self._safe_release(attempt)
            logger.warning("judge returned an unverifiable WIN; question not charged")
            raise AIInvalidResponseError()
        return await self._commit(attempt, answer, question.text, AttemptKind.QUESTION)

    async def guess(self, player_hash: str, raw_guess: str, idempotency_key: str) -> AskResult:
        """A direct guess of the word: costs one attempt, judged by exact comparison (no AI)."""
        try:
            guess = parse_guess(raw_guess)
        except InvalidGuessError as exc:
            raise InvalidGuessAppError(details={"reason": exc.reason}) from exc
        game_date = self.today()
        puzzle = self._words.puzzle_for(game_date)
        attempt = _Attempt(game_date, player_hash, idempotency_key, uuid.uuid4().hex)
        replay = await self._reserve(attempt, f"g:{guess.word}", guess.qhash)
        if replay is not None:
            return replay
        answer = Answer.WIN if guess_is_correct(guess, puzzle.word) else Answer.NO
        return await self._commit(attempt, answer, guess.text, AttemptKind.GUESS)

    async def _reserve(self, attempt: _Attempt, body: str, qhash: str) -> AskResult | None:
        """Atomically reserve one attempt. Returns a replayed result, raises, or None."""
        try:
            reserved = await self._store.reserve(
                game_date=attempt.game_date,
                player_hash=attempt.player_hash,
                idempotency_key=attempt.idempotency_key,
                body_hash=hashlib.sha256(body.encode()).hexdigest(),
                qhash=qhash,
                token=attempt.token,
                now=self._clock.now(),
                lease_ms=self._lease_ms,
            )
        except RedisError as exc:
            raise _unavailable(exc) from exc

        match reserved.outcome:
            case ReserveOutcome.REPLAY:
                if reserved.number is None or reserved.answer is None:  # pragma: no cover
                    raise ServiceUnavailableError()
                game = await self.state(attempt.player_hash, attempt.game_date)
                return AskResult(reserved.number, reserved.answer, game, replayed=True)
            case ReserveOutcome.KEY_REUSED:
                raise IdempotencyKeyReusedError()
            case ReserveOutcome.IN_PROGRESS:
                raise QuestionInProgressError()
            case ReserveOutcome.FINISHED:
                raise GameFinishedError()
            case ReserveOutcome.LIMIT:
                raise AttemptLimitReachedError()
            case ReserveOutcome.DUPLICATE:
                raise DuplicateQuestionError()
            case ReserveOutcome.RESERVED:
                return None

    async def _commit(
        self, attempt: _Attempt, answer: Answer, text: str, kind: AttemptKind
    ) -> AskResult:
        try:
            committed = await self._store.commit(
                game_date=attempt.game_date,
                player_hash=attempt.player_hash,
                idempotency_key=attempt.idempotency_key,
                token=attempt.token,
                now=self._clock.now(),
                answer=answer,
                question=text,
                kind=kind,
            )
        except RedisError as exc:
            # The lease simply expires; the attempt was never charged.
            raise _unavailable(exc) from exc
        if not committed.committed:
            logger.warning("lease expired before commit; attempt not charged")
            raise AIUnavailableError()
        game = await self.state(attempt.player_hash, attempt.game_date)
        return AskResult(committed.number, answer, game, replayed=False)

    async def _safe_release(self, attempt: _Attempt) -> None:
        try:
            await self._store.release(
                game_date=attempt.game_date,
                player_hash=attempt.player_hash,
                idempotency_key=attempt.idempotency_key,
                token=attempt.token,
            )
        except RedisError:
            logger.warning("release failed; the lease will expire on its own")


def _unavailable(exc: RedisError) -> ServiceUnavailableError:
    logger.error("redis error: %s", type(exc).__name__)
    return ServiceUnavailableError()
