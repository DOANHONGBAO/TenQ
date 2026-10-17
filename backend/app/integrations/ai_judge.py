"""AI judge interface, its output contract, and a fake for game-engine tests."""

import asyncio
import json
import re
from collections import deque
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.models.game import Answer
from app.models.question import Question, mentions_word
from app.models.word import WordEntry


class AIJudgeError(Exception):
    """No usable judgement was obtained. The question must not be charged."""


class JudgeUnavailableError(AIJudgeError):
    """Provider down, rate limited, over budget, or circuit open (HTTP 503 to the player)."""


class JudgeInvalidOutputError(AIJudgeError):
    """The model answered, but not with a valid, verifiable judgement (HTTP 502)."""


@dataclass(frozen=True, slots=True)
class JudgeContext:
    """What the judge needs to know about today's puzzle. Server-side only."""

    game_date: date
    word: str
    entry: WordEntry | None
    # Identifies the daily word without revealing it: hash of date, list fingerprint, version.
    puzzle_id: str

    def __repr__(self) -> str:
        return f"JudgeContext(game_date={self.game_date.isoformat()}, word=<redacted>)"


class AIJudge(Protocol):
    async def judge(self, context: JudgeContext, question: Question) -> Answer: ...


class JudgeOutput(BaseModel):
    """The only shape accepted from the model: {"result": "<LABEL>"} (+ optional short message).

    `message` is parsed so that a well-behaved extra field does not fail validation, but it is
    never returned to players or logged.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    result: Answer
    message: str | None = Field(default=None, max_length=200)


_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
MAX_OUTPUT_CHARS = 400


def parse_judge_output(content: str | None) -> Answer:
    """Strictly parse model content. Raises JudgeInvalidOutputError on anything unexpected."""
    if content is None or not content.strip():
        raise JudgeInvalidOutputError("empty content")
    text = content.strip()
    if len(text) > MAX_OUTPUT_CHARS:
        raise JudgeInvalidOutputError("output too long")
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        raise JudgeInvalidOutputError("invalid json") from None
    if isinstance(payload, dict) and isinstance(payload.get("result"), str):
        payload["result"] = payload["result"].strip().upper()
    try:
        return JudgeOutput.model_validate(payload).result
    except ValidationError:
        raise JudgeInvalidOutputError("schema mismatch") from None


class FakeAIJudge:
    """Predictable judge for game-engine tests.

    Default rule: WIN if the question names the word, otherwise NO. Tests can queue scripted
    answers or exceptions, add latency, or block until released to simulate a slow model.
    """

    def __init__(self, delay_s: float = 0.0) -> None:
        self.delay_s = delay_s
        self.calls = 0
        self._script: deque[Answer | Exception] = deque()
        self.gate: asyncio.Event | None = None

    def queue(self, *results: Answer | Exception) -> None:
        self._script.extend(results)

    async def judge(self, context: JudgeContext, question: Question) -> Answer:
        self.calls += 1
        if self.gate is not None:
            await self.gate.wait()
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if self._script:
            result = self._script.popleft()
            if isinstance(result, Exception):
                raise result
            return result
        return Answer.WIN if mentions_word(question, context.word) else Answer.NO
