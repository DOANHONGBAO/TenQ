# AI Judge Checklist

## Output validation
- [ ] Response parsed into a Pydantic model with `extra="forbid"`
- [ ] Answer field is a closed set (e.g. `Literal["yes", "no", "partly", "irrelevant"]` or whatever the requirements define)
- [ ] Malformed JSON, empty body, extra prose around JSON → typed `JudgeInvalidOutputError`
- [ ] Output length bounded; oversized output rejected
- [ ] Secret-leak post-filter applied before returning to the player

## Prompt injection
- [ ] Player question length-limited and normalized (strip control chars, collapse whitespace) before use
- [ ] Question placed in a clearly delimited data section; instructions say to ignore instructions inside it
- [ ] Judge cannot be asked to "repeat the system prompt", "spell the word", "answer in base64", etc. (corpus test)
- [ ] Final-guess checking is done by deterministic server code, not by asking the model "is this correct?"

## Caching
- [ ] Key includes game_day, normalized question, prompt version, model id
- [ ] TTL bounded to the game day (+ margin)
- [ ] Only validated judgements are cached; errors are never cached
- [ ] Cache hit does not skip attempt charging (that is a game-integrity decision — check consistency with tenq-game-integrity A1–A4)

## Provider errors
- [ ] Explicit connect + read timeout
- [ ] Retry only on timeout / 429 / 5xx, max N attempts, exponential backoff with jitter
- [ ] Honors `Retry-After` when present
- [ ] 4xx (auth, bad request) not retried; surfaced as configuration error and alerted in logs
- [ ] Final failure maps to a stable error code (e.g. `AI_UNAVAILABLE`) and documented attempt-refund policy

## Quota and cost
- [ ] Per-player and global rate limits exist before the provider call
- [ ] Behavior on quota exhaustion is defined (graceful message, no crash loop)
- [ ] Model id and limits come from configuration, not hard-coded

## Testability
- [ ] Provider behind a typed interface; fake implementation in `tests/`
- [ ] Fake can simulate: valid answer, malformed output, timeout, 429 with Retry-After, 500, leaking output
- [ ] Live-provider tests opt-in via marker and env var, excluded from default CI
- [ ] API key read from environment only; tests never require a real key
