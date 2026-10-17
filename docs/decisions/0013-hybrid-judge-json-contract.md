# ADR 0013: Hybrid judge pipeline with a JSON output contract

- Status: Proposed
- Date: 2026-10-17
- Supersedes: the single-label output format of [ADR 0010](0010-ai-judge-output-contract.md). ADR 0010's other decisions (no reliance on structured outputs, server-verified WIN, per-day cache, typed provider interface) remain.

## Context

The owner's Phase 05 brief requires the model to return a JSON object `{"result": LABEL}` (optionally a short `message`) validated with Pydantic, a hybrid pipeline in which deterministic rules run before any model call, a shared daily cache with stampede protection, bounded retries, a circuit breaker, and a global hourly and daily AI budget. Official Ollama documentation (checked 2026-10-17): `POST https://ollama.com/api/chat` with `Authorization: Bearer`; `GET /api/tags` lists models; the Free plan gives "starter usage" for an unpublished set of "starter models" and 1 concurrent request; errors are JSON `{"error": ...}` with 429 for rate limits and 500/502 for server or model failures. The cloud page does not say whether cloud models honor `format`.

## Decision

- **Output contract**: the system prompt requires exactly `{"result": "YES|NO|IRRELEVANT|PENALTY|WIN"}`. The parser strips one optional code fence, requires a single JSON object, upper-cases `result`, and validates `JudgeOutput` (`extra="forbid"`, `message` at most 200 characters). `message` is never returned or logged. One stricter re-ask is allowed; a second invalid output is `502 AI_INVALID_RESPONSE`, not charged.
- **Pipeline**: (1) format checks (existing), (2) deterministic `PENALTY` for open-ended questions, several questions, and manipulation patterns, (3) deterministic `WIN` for direct guesses ("Is it a X?", "Is the secret word X?"), (4) shared daily cache, (5) model call, (6) validation and server-side WIN check, (7) commit by GameService, (8) cache the validated label.
- **Cache**: `tenq:v1:judge:{date}:{sha256(date | puzzle_id | normalized question | prompt_version | model)}` where `puzzle_id = sha256(date | word list hash | selection version)[:32]`. Normalization is case and whitespace only. Only validated labels from the model are cached (`SET NX`, TTL to the day's cleanup instant). Stampede protection: single-flight futures inside a process plus a Redis lock (`SET NX PX`) across processes; waiters poll the cache.
- **Resilience**: per-attempt connect 3 s / read 12 s inside the overall deadline; at most 2 retries on timeout, connection error, 429 (Retry-After honored), and 5xx, with jittered exponential backoff. 401/403/402 are configuration errors: no retry, the circuit trips for 5 minutes. Circuit breaker: 5 consecutive failures open it for 30 s, then one trial call.
- **Budget**: a Lua script counts every HTTP attempt (retries included) against `TENQ_AI_HOURLY_BUDGET` and `TENQ_AI_DAILY_BUDGET`; when either is reached, the player gets a polite `503 AI_UNAVAILABLE` and is not charged. An asyncio semaphore keeps concurrent calls at `TENQ_AI_MAX_CONCURRENCY` (default 1, the free-plan limit).
- **Model choice**: configuration only (`TENQ_OLLAMA_MODEL`, no default). `app.scripts.check_ollama_models` lists visible models and probes one with a single request, because free access is account-specific and unpublished.
- **Default provider**: `TENQ_AI_JUDGE=mock` uses `MockOllamaProvider` as an HTTP transport, so local runs and tests exercise the real client without network or key. Production refuses `mock`.

## Consequences

- JSON costs a few more output tokens than a bare label, in exchange for a schema the owner can extend.
- Deterministic rules can misfire on unusual phrasing; they are intentionally narrow, and everything else goes to the model.
- Accuracy is measured, not assumed: `app.scripts.evaluate_judge` reports accuracy and consistency on a labelled set of words outside the game vocabulary, and live runs are opt-in and capped.
- The circuit breaker and single-flight are per process; across processes the Redis lock and budget still bound total calls.
