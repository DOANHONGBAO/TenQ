---
name: tenq-ai-judge-testing
description: Tests and reviews TenQ's AI judge integration with Ollama Cloud. Use when writing, changing, or reviewing the Ollama client, judge prompts, parsing or validation of model output, judgement caching, retries/timeouts, quota or rate-limit handling, or prompt-injection defenses for player questions. Also use when designing pytest fixtures or fakes for the AI provider. Not for attempt counting or leaderboard logic (use tenq-game-integrity).
---

# TenQ AI Judge Testing

The judge answers a player's question about the secret. It is the least deterministic, most attackable, and most expensive component. Treat its output as untrusted input and its availability as unreliable.

## Procedure

1. **Map the judge boundary.** Identify: the client module that calls Ollama, the prompt template, the response schema, the cache layer, the error mapping to HTTP responses. Read the current Ollama Cloud API docs (via WebFetch or Context7) before asserting request/response shapes — do not rely on memory.
2. **Review against** [references/judge-checklist.md](references/judge-checklist.md). Record status and `file:line` evidence for each item.
3. **Check the test harness.** Tests must never call the real provider by default. Require a fake/stub provider injected through a typed interface (e.g. a `Protocol`), plus an opt-in, marked integration test (`@pytest.mark.live_ai`) excluded from CI unless explicitly enabled.
4. **Run the injection corpus.** Use [references/injection-corpus.md](references/injection-corpus.md) as parametrized test inputs. Each must yield a schema-valid judgement and must not reveal the secret.
5. **Report** with the format below.

## Output format

```
## AI judge review — <scope>
| Area | Item | Status | Evidence | Fix |
|------|------|--------|----------|-----|
### Tests to add
- <test>: <input> → <expected>
### Cost/quota note
<expected calls per game, cache hit assumptions, behavior at quota exhaustion>
```

## Key rules

- Parse model output into a strict Pydantic model (`extra="forbid"`, enum/Literal answers). Anything that fails validation is a provider error, never passed through to the player.
- The secret goes in the system/instruction part; the player question is delimited and described as data. Never concatenate the question into instructions.
- Post-check the judge output: reject if it contains the secret word or close variants before the game ends.
- Cache key = hash of (game_day, normalized question, prompt version, model id). Never include raw secrets or player ids in keys visible outside the server; bump prompt version when the template changes.
- Every provider call has an explicit timeout, bounded retries with backoff only on retryable errors (timeouts, 429, 5xx), and maps final failure to a stable API error code.
- Never log full prompts containing the secret, or API keys. Log request ids, latency, status, token counts.
