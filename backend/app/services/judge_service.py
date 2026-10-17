"""Hybrid judge: deterministic rules first, then a shared daily cache, then Ollama.

Pipeline for one question (input validation already happened in GameService):

1. Deterministic PENALTY for open-ended questions and manipulation attempts (no AI call).
2. Deterministic WIN for direct guesses of the word, and NO for an explicit guess of another
   word ("Is the secret word X?"). No AI call.
3. Shared daily cache lookup (same question, same day, same answer for every player).
4. On a miss: single-flight per process + a Redis lock across processes, so N players asking
   the same new question cause one model call (cache stampede protection).
5. Guards before every HTTP attempt: circuit breaker, global hourly/daily budget, and a
   concurrency limit (the free plan allows one concurrent request).
6. Strict parsing of {"result": LABEL}; one stricter re-ask if the output is invalid.
7. WIN from the model is accepted only if the server sees the word in the question.
8. Only validated, player-independent labels are cached; failures are never cached.

The judge only returns a label. Charging attempts and the leaderboard stay in GameService.
"""

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import Callable

from redis.exceptions import RedisError

from app.core.circuit_breaker import CircuitBreaker
from app.integrations.ai_judge import (
    JudgeContext,
    JudgeInvalidOutputError,
    JudgeUnavailableError,
    parse_judge_output,
)
from app.integrations.judge_prompt import PROMPT_VERSION, build_messages
from app.integrations.ollama_client import (
    OllamaAuthError,
    OllamaClient,
    OllamaError,
    OllamaPaymentRequiredError,
)
from app.models.clock import Clock
from app.models.game import Answer
from app.models.judge_rules import exact_guess, prefilter, wrong_explicit_guess
from app.models.question import Question, mentions_word
from app.repositories.judge_cache import JudgeCache, cache_key

logger = logging.getLogger(__name__)

CONFIG_ERROR_OPEN_S = 300.0


class BudgetExceededError(JudgeUnavailableError):
    pass


class HybridJudge:
    def __init__(
        self,
        client: OllamaClient,
        cache: JudgeCache,
        breaker: CircuitBreaker,
        clock: Clock,
        *,
        deadline_s: float,
        daily_budget: int,
        hourly_budget: int,
        max_concurrency: int = 1,
        lock_ttl_ms: int = 25_000,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._cache = cache
        self._breaker = breaker
        self._clock = clock
        self._deadline_s = deadline_s
        self._daily_budget = daily_budget
        self._hourly_budget = hourly_budget
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._lock_ttl_ms = lock_ttl_ms
        self._monotonic = monotonic
        self._inflight: dict[str, asyncio.Future[Answer]] = {}
        self.model_calls = 0  # observability and tests

    async def take_budget(self) -> None:
        """Called by the Ollama client before every HTTP attempt, retries included."""
        try:
            verdict = await self._cache.take_budget(
                self._clock.now(), self._daily_budget, self._hourly_budget
            )
        except RedisError as exc:
            raise JudgeUnavailableError("budget store unavailable") from exc
        if verdict != "OK":
            logger.warning("AI budget exhausted (%s)", verdict.lower())
            raise BudgetExceededError(f"{verdict.lower()} budget exhausted")

    async def judge(self, context: JudgeContext, question: Question) -> Answer:
        ruled = prefilter(question)
        if ruled is not None:
            return ruled
        if exact_guess(question, context.word):
            return Answer.WIN
        if wrong_explicit_guess(question, context.word):
            return Answer.NO

        key = cache_key(
            context.game_date,
            context.puzzle_id,
            question.normalized,
            PROMPT_VERSION,
            self._client.model,
        )
        cached = await self._cache_get(context, key)
        if cached is not None:
            return cached

        # Single-flight inside this process: concurrent identical questions share one future.
        existing = self._inflight.get(key)
        if existing is not None:
            return await asyncio.shield(existing)
        future: asyncio.Future[Answer] = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            answer = await self._compute_with_lock(context, question, key)
        except BaseException as exc:
            # Waiters get a normal judge error even if this caller was cancelled (timeout).
            shared = exc if isinstance(exc, Exception) else JudgeUnavailableError("cancelled")
            future.set_exception(shared)
            future.exception()  # mark retrieved so lone failures are not reported as unhandled
            raise
        else:
            future.set_result(answer)
            return answer
        finally:
            self._inflight.pop(key, None)

    async def _cache_get(self, context: JudgeContext, key: str) -> Answer | None:
        try:
            return await self._cache.get(context.game_date, key)
        except RedisError:
            logger.warning("judge cache read failed; continuing without cache")
            return None

    async def _compute_with_lock(
        self, context: JudgeContext, question: Question, key: str
    ) -> Answer:
        """Across processes: whoever holds the Redis lock calls the model; others wait for it."""
        token = uuid.uuid4().hex
        started = self._monotonic()
        while True:
            try:
                acquired = await self._cache.acquire_lock(
                    context.game_date, key, token, self._lock_ttl_ms
                )
            except RedisError:
                acquired = True  # without Redis, fall back to calling the model directly
            if acquired:
                break
            await asyncio.sleep(0.1)
            cached = await self._cache_get(context, key)
            if cached is not None:
                return cached
            if self._monotonic() - started > self._deadline_s:
                raise JudgeUnavailableError("timed out waiting for a concurrent judgement")
        try:
            cached = await self._cache_get(context, key)  # filled while we waited for the lock
            if cached is not None:
                return cached
            answer = await self._ask_model(context, question)
            try:
                await self._cache.set(context.game_date, key, answer, self._clock.now())
            except RedisError:
                logger.warning("judge cache write failed")
            return answer
        finally:
            with contextlib.suppress(RedisError):
                await self._cache.release_lock(context.game_date, key, token)

    async def _ask_model(self, context: JudgeContext, question: Question) -> Answer:
        if not self._breaker.allow():
            raise JudgeUnavailableError("circuit open")
        started = self._monotonic()
        async with self._semaphore:
            for strict in (False, True):
                remaining = self._deadline_s - (self._monotonic() - started)
                if remaining <= 0:
                    self._breaker.record_failure()
                    raise JudgeUnavailableError("deadline exceeded")
                try:
                    self.model_calls += 1
                    result = await self._client.chat(
                        build_messages(context, question, strict), deadline_s=remaining
                    )
                except (OllamaAuthError, OllamaPaymentRequiredError) as exc:
                    logger.error("ollama configuration error: %s", type(exc).__name__)
                    self._breaker.trip(CONFIG_ERROR_OPEN_S)
                    raise JudgeUnavailableError("provider configuration error") from exc
                except OllamaError as exc:
                    self._breaker.record_failure()
                    raise JudgeUnavailableError(type(exc).__name__) from exc
                try:
                    answer = parse_judge_output(result.content)
                except JudgeInvalidOutputError as exc:
                    logger.warning("invalid judge output (%s); strict=%s", exc, strict)
                    if strict:
                        self._breaker.record_failure()
                        raise
                    continue
                self._breaker.record_success()
                if answer is Answer.WIN and not mentions_word(question, context.word):
                    raise JudgeInvalidOutputError("unverifiable WIN")
                return answer
        raise JudgeInvalidOutputError("unreachable")  # pragma: no cover
