# ADR 0003: Atomic game state with Redis Lua scripts and a single question lease

- Status: Proposed
- Date: 2026-10-17

## Context

Two requests from the same player may arrive at the same time (two tabs, double click, retry). The 10-question limit (BR-04) and "no charge on AI failure" (BR-09) must both hold. The AI call takes seconds and can fail, so the charge cannot simply happen before or after it without coordination.

## Options considered

1. **Read-modify-write in Python** — simple; race condition between read and write. Rejected.
2. **`WATCH` / `MULTI` / `EXEC` (optimistic transactions)** — atomic, but conditional logic needs a client round trip and retry loop on conflict; harder to reason about and test.
3. **Lua scripts (`EVALSHA`)** — Redis runs the whole script atomically in one round trip; conditional logic lives next to the data; easy to unit-test against a real Redis.
4. **Redis Functions** — like Lua scripts but persisted in Redis; adds deployment steps for little benefit at this size.
5. **Charge-first, refund on failure** — simple, but a crash between charge and refund loses a question permanently, violating BR-09.

## Decision

Option 3 with a **reserve / commit / release** protocol and a single lease per player:

- `reserve` atomically checks all rules and grants one lease (token + expiry). Only one question per player can be in flight.
- `commit` charges the question only if the lease token is still valid.
- `release` drops the lease on AI failure without charging.
- Expired leases (API crash) are ignored by the next `reserve`; a late `commit` with a stale token is rejected.

## Consequences

- No double charging and no lost questions, even with crashes.
- A second simultaneous question returns `409 QUESTION_IN_PROGRESS`; the UI disables the input while waiting, so normal players never see it.
- Scripts must be tested against a real Redis (not a mock) in CI.
- Lease length (30 s) must stay above the AI total deadline (20 s); enforced by a settings validator.
