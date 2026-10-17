---
name: tenq-game-integrity
description: Reviews TenQ game-state correctness. Use when writing, changing, or reviewing code that selects the daily secret, counts or enforces the 10-question limit, handles guesses or game completion, stores per-player session state (Redis keys, signed cookies), or computes and writes leaderboard entries. Also use when asked whether the game can be cheated, double-counted, or raced. Not for AI prompt/judge logic (use tenq-ai-judge-testing) or infrastructure (use tenq-deployment-audit).
---

# TenQ Game Integrity Review

TenQ's core promise: every player gets the same secret for a given game day, gets at most 10 questions, and the leaderboard reflects only legitimate, completed games. This skill checks code against that promise.

## Procedure

1. **Locate the game-state path.** Find where these live (names may differ; search, don't assume):
   - daily secret selection and the definition of "game day" (timezone, rollover time)
   - the per-player attempt counter and where it is incremented
   - guess submission / game completion
   - leaderboard write and read paths
   - the identity source (signed HttpOnly cookie, session id)
2. **Trace one request end to end.** For a question request, write down the exact order: validate input → load session → check attempt budget → call judge → persist attempt → respond. Note every point where two concurrent requests could interleave.
3. **Check each invariant** in [references/invariants.md](references/invariants.md). For each one, record: holds / violated / not yet implemented, with `file:line` evidence.
4. **Check tests.** For each invariant that is implemented, confirm a test exists that would fail if it broke. Concurrency invariants need a test that actually issues parallel requests, not a sequential loop.
5. **Report** using the format below. Propose fixes as minimal diffs; do not rewrite unrelated code.

## Output format

```
## Game integrity review — <scope>
| # | Invariant | Status | Evidence | Fix |
|---|-----------|--------|----------|-----|
...
### Missing tests
- <test name>: <what it must assert>
### Risk summary
<1–3 sentences: worst realistic exploit and its impact>
```

## Key rules

- The attempt check and the attempt increment must be one atomic operation (Redis `INCR` compared after, a Lua script, or `WATCH/MULTI`). A read-then-write in Python is a race even if it "looks" sequential under `async`.
- Charge the attempt **before** or **atomically with** calling the AI judge, and define explicitly whether a provider failure refunds it. Either choice is acceptable only if documented and tested.
- The secret never leaves the server before the game ends: not in responses, error messages, logs, client bundles, cookies, or cache keys readable by the client.
- Never trust client-supplied attempt counts, scores, timestamps, or "game finished" flags.
- Retries of the same request (network replay, double click) must not consume two attempts — require an idempotency key or request id.
