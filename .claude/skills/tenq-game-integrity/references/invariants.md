# TenQ Game Invariants

Each invariant lists what to verify and the test that proves it.

## Daily secret

| ID | Invariant | Verify | Test |
|----|-----------|--------|------|
| S1 | One secret per game day, identical for all players | Selection is deterministic from (game_day, server-side seed) or stored once per day; no per-request randomness | Two sessions on the same day receive judgements consistent with the same secret |
| S2 | Game day boundary is explicit | A single function computes `game_day` with an explicit timezone (UTC unless an ADR says otherwise) | Requests at 23:59:59 and 00:00:00 map to different days; DST/offset cases covered if non-UTC |
| S3 | Secret is not predictable | Seed comes from configuration/secret storage, not from the date alone or a public list order | Unit test: changing the seed changes the selection |
| S4 | Secret is not leaked | Grep responses, exceptions, logs, OpenAPI examples, frontend env for secret values | API test asserts the secret string is absent from every non-final response body |
| S5 | Word list changes do not change past/current days | Selection for an already-started day is stored or pinned | Test: append to the word list mid-day, current secret unchanged |

## Attempts

| ID | Invariant | Verify | Test |
|----|-----------|--------|------|
| A1 | At most 10 questions per player per game day | Server-side counter keyed by (player_id, game_day) | 11th request returns a defined error (e.g. 409/429) and does not call the judge |
| A2 | Check + increment is atomic | Single Redis atomic op or Lua script; no Python read-modify-write | Fire 20 concurrent requests for a fresh player → exactly 10 accepted |
| A3 | Idempotent retries | Same idempotency key returns the stored result, no new charge | Replay a request id twice → counter increases by 1 |
| A4 | Provider failure policy is defined | Code and docs agree on refund vs. charge on judge error/timeout | Simulated provider timeout → counter matches documented policy |
| A5 | Counter TTL outlives the game day | Keys expire after the day ends (plus margin), not before | TTL assertion in test |
| A6 | Finished games accept no further questions | Win/lose state blocks new attempts | Question after a correct final guess is rejected |

## Identity and session

| ID | Invariant | Verify | Test |
|----|-----------|--------|------|
| P1 | Player id comes only from a signed, HttpOnly, Secure, SameSite cookie | Signature verified on every request; tampered cookie rejected | Modified cookie → new anonymous identity or 401, never another player's state |
| P2 | Clearing cookies is a known limitation, not a hole | Rate limiting / Turnstile limits fresh-identity farming | Documented in ADR; rate-limit test exists once implemented |
| P3 | No client-trusted state | Attempt count, result, score are server-derived | Sending forged fields in the body has no effect |

## Leaderboard

| ID | Invariant | Verify | Test |
|----|-----------|--------|------|
| L1 | Only completed, server-verified games are recorded | Write happens inside the completion path, not from a client call | Direct POST to a leaderboard write route (if any) is rejected |
| L2 | One entry per player per game day | Unique constraint (SQLite) or `ZADD NX`/equivalent | Completing twice yields one entry |
| L3 | Ranking is deterministic | Tie-break rule defined (fewer questions, then earlier finish) | Tie fixture produces stable order |
| L4 | Display names are validated and escaped | Length/charset limits, no HTML injection | XSS payload name is rendered as text |
