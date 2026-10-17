"""MockOllamaProvider: an in-process stand-in for https://ollama.com/api/chat.

It plugs into the real OllamaClient as an httpx2 transport, so local development and tests
exercise the full pipeline (HTTP, parsing, retries, cache, budget) without a network call
or an API key. Answers come from simple rules over the word facts in the system prompt;
they are plausible, not intelligent. Tests can queue failures and raw outputs.
"""

import json
import re
from collections import deque

import httpx2

_WORD = re.compile(r"The secret word is: ([a-z]+)")
_FACTS = re.compile(r"Facts about the secret word \(for judging only\): (.*)")
_STOPWORDS = {"is", "it", "a", "an", "the", "of", "does", "do", "can", "you", "used", "for"}

MockStep = httpx2.Response | Exception | str  # str = raw assistant content to return


class MockOllamaProvider:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []
        self._script: deque[MockStep] = deque()
        self.gate: object | None = None

    def queue(self, *steps: MockStep) -> None:
        self._script.extend(steps)

    @property
    def calls(self) -> int:
        return len(self.requests)

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self._handle)

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        if request.url.path != "/api/chat":
            return httpx2.Response(404, json={"error": "not found"})
        if self._script:
            step = self._script.popleft()
            if isinstance(step, Exception):
                raise step
            if isinstance(step, httpx2.Response):
                return step
            return _ok(body, step)
        return _ok(body, json.dumps({"result": self._rule_answer(body)}))

    @staticmethod
    def _rule_answer(body: dict[str, object]) -> str:
        messages = body.get("messages")
        if not isinstance(messages, list) or len(messages) < 2:
            return "PENALTY"
        system = str(messages[0]["content"])
        question = str(json.loads(messages[1]["content"])["player_question"]).lower()
        word_match = _WORD.search(system)
        word = word_match.group(1) if word_match else ""
        tokens = set(re.findall(r"[a-z]+", question)) - _STOPWORDS
        if word and tokens & {word, word + "s"}:
            return "WIN"
        facts_match = _FACTS.search(system)
        facts_text = facts_match.group(1).lower() if facts_match else ""
        fact_tokens = set(re.findall(r"[a-z]+", facts_text)) - _STOPWORDS
        return "YES" if tokens & fact_tokens else "NO"


def _ok(body: dict[str, object], content: str) -> httpx2.Response:
    return httpx2.Response(
        200,
        json={
            "model": body.get("model"),
            "created_at": "2026-10-17T00:00:00Z",
            "message": {"role": "assistant", "content": content},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 180,
            "eval_count": 8,
        },
    )
