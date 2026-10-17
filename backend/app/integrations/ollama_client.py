"""Ollama Cloud chat client (POST https://ollama.com/api/chat, Bearer auth).

One pooled httpx2 AsyncClient per process. Every call has an overall deadline; retries are
bounded and happen only for timeouts, connection errors, HTTP 429, and 5xx, with jittered
exponential backoff and Retry-After honored when it fits inside the deadline. Prompts and
the API key are never logged.
"""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx2

logger = logging.getLogger(__name__)


class OllamaError(Exception):
    retryable = False


class OllamaAuthError(OllamaError):
    """401/403: missing or wrong API key. Configuration problem, never retried."""


class OllamaPaymentRequiredError(OllamaError):
    """402: the model is not included in the account's plan, or credits ran out."""


class OllamaRateLimitedError(OllamaError):
    retryable = True

    def __init__(self, message: str, retry_after_s: float | None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class OllamaServerError(OllamaError):
    retryable = True


class OllamaTimeoutError(OllamaError):
    retryable = True


class OllamaConnectionError(OllamaError):
    retryable = True


class OllamaBadResponseError(OllamaError):
    """Unexpected HTTP status (4xx other than the above) or malformed response envelope."""


@dataclass(frozen=True, slots=True)
class ChatResult:
    content: str | None
    prompt_tokens: int
    output_tokens: int
    attempts: int
    done_reason: str | None = None


@dataclass(frozen=True, slots=True)
class OllamaOptions:
    model: str
    temperature: float = 0.0
    num_predict: int = 512
    think: bool | str | None = None  # None = do not send; some models only accept levels
    connect_timeout_s: float = 3.0
    read_timeout_s: float = 12.0
    max_retries: int = 2
    backoff_base_s: float = 0.5


def make_http_client(
    base_url: str, api_key: str | None, transport: httpx2.AsyncBaseTransport | None = None
) -> httpx2.AsyncClient:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return httpx2.AsyncClient(
        base_url=base_url,
        headers=headers,
        limits=httpx2.Limits(max_connections=10, max_keepalive_connections=5),
        transport=transport,
    )


def _retry_after(response: httpx2.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


class OllamaClient:
    def __init__(
        self,
        http: httpx2.AsyncClient,
        options: OllamaOptions,
        before_attempt: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """`before_attempt` is an async callable run before every HTTP attempt (budget check)."""
        self._http = http
        self._options = options
        self._before_attempt = before_attempt

    @property
    def model(self) -> str:
        return self._options.model

    async def chat(self, messages: list[dict[str, str]], deadline_s: float) -> ChatResult:
        opts = self._options
        body: dict[str, Any] = {
            "model": opts.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": opts.temperature, "num_predict": opts.num_predict},
        }
        if opts.think is not None:
            body["think"] = opts.think

        started = time.monotonic()
        attempt = 0
        while True:
            attempt += 1
            remaining = deadline_s - (time.monotonic() - started)
            if remaining <= 0:
                raise OllamaTimeoutError("deadline exceeded")
            if self._before_attempt is not None:
                await self._before_attempt()
            try:
                return await self._attempt(body, remaining, attempt)
            except OllamaError as exc:
                if not exc.retryable or attempt > opts.max_retries:
                    raise
                delay = opts.backoff_base_s * (2 ** (attempt - 1)) * random.uniform(0.5, 1.5)  # noqa: S311 - jitter, not crypto
                if isinstance(exc, OllamaRateLimitedError) and exc.retry_after_s is not None:
                    delay = max(delay, exc.retry_after_s)
                if time.monotonic() - started + delay >= deadline_s:
                    raise
                logger.warning(
                    "ollama attempt %d failed (%s); retrying in %.2fs",
                    attempt,
                    type(exc).__name__,
                    delay,
                )
                await asyncio.sleep(delay)

    async def _attempt(self, body: dict[str, Any], remaining_s: float, attempt: int) -> ChatResult:
        opts = self._options
        timeout = httpx2.Timeout(
            timeout=min(opts.read_timeout_s, remaining_s),
            connect=min(opts.connect_timeout_s, remaining_s),
        )
        t0 = time.monotonic()
        try:
            response = await self._http.post("/api/chat", json=body, timeout=timeout)
        except httpx2.TimeoutException:
            raise OllamaTimeoutError("timeout") from None
        except httpx2.TransportError:
            raise OllamaConnectionError("connection error") from None

        status = response.status_code
        if status in (401, 403):
            raise OllamaAuthError(f"http {status}")
        if status == 402:
            raise OllamaPaymentRequiredError("http 402")
        if status == 429:
            raise OllamaRateLimitedError("http 429", _retry_after(response))
        if status >= 500:
            raise OllamaServerError(f"http {status}")
        if status != 200:
            raise OllamaBadResponseError(f"http {status}")

        try:
            data = response.json()
            message = data.get("message") or {}
            content = message.get("content")
            done_reason = data.get("done_reason")
            prompt_tokens = int(data.get("prompt_eval_count") or 0)
            output_tokens = int(data.get("eval_count") or 0)
        except (ValueError, AttributeError, TypeError):
            raise OllamaBadResponseError("malformed envelope") from None
        if done_reason == "length":
            # Usually a thinking model spent num_predict on reasoning; see TENQ_OLLAMA_THINK.
            logger.warning("ollama output truncated (done_reason=length, tokens=%d)", output_tokens)
        logger.info(
            "ollama ok model=%s attempt=%d latency_ms=%d prompt_tokens=%d output_tokens=%d",
            opts.model,
            attempt,
            int((time.monotonic() - t0) * 1000),
            prompt_tokens,
            output_tokens,
        )
        return ChatResult(
            content=content if isinstance(content, str) else None,
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
            attempts=attempt,
            done_reason=done_reason if isinstance(done_reason, str) else None,
        )
