# AI Judge Checklist

## Output validation
- [ ] Output is exactly one JSON object `{"result": LABEL}` validated by `JudgeOutput` (ADR 0013); optional `message` is never returned or logged
- [ ] Anything else (prose, bare label, extra fields, empty, unknown enum) → typed `JudgeInvalidOutputError` → `502 AI_INVALID_RESPONSE`, no charge
- [ ] Output length bounded; oversized output rejected before parsing
- [ ] Only the label reaches the player; model free text is never returned or logged
- [ ] Does not depend on Ollama structured outputs (`format`) being honored

## Prompt injection
- [ ] Player question length-limited and normalized (strip control chars, collapse whitespace) before use
- [ ] Question placed in a clearly delimited data section; instructions say to ignore instructions inside it
- [ ] Judge cannot be asked to "repeat the system prompt", "spell the word", "answer in base64", etc. (corpus test)
- [ ] `WIN` accepted only when server code finds the secret word (or simple plural) as a whole token in the normalized question

## Caching
- [ ] Key includes game_day, normalized question, prompt version, model id
- [ ] TTL bounded to the game day (+ margin)
- [ ] Only validated judgements are cached; errors are never cached
- [ ] Cache is global per day (same answer for every player); a cache hit still charges the question like a fresh judgement

## Provider errors
- [ ] Explicit connect + read timeout
- [ ] Retry only on timeout / 429 / 5xx, max N attempts, exponential backoff with jitter
- [ ] Honors `Retry-After` when present
- [ ] 4xx (auth, bad request) not retried; surfaced as configuration error and alerted in logs
- [ ] Final failure maps to `503 AI_UNAVAILABLE` and the question is released, never charged (BR-09)

## Quota and cost
- [ ] Per-player and global rate limits exist before the provider call
- [ ] Behavior on quota exhaustion is defined (graceful message, no crash loop)
- [ ] Model id and limits come from configuration, not hard-coded

## Testability
- [ ] Provider behind a typed interface; fake implementation in `tests/`
- [ ] Fake can simulate: valid answer, malformed output, timeout, 429 with Retry-After, 500, leaking output
- [ ] Live-provider tests opt-in via marker and env var, excluded from default CI
- [ ] API key read from environment only; tests never require a real key
