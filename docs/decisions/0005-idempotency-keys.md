# ADR 0005: Idempotency keys for question submissions

- Status: Proposed
- Date: 2026-10-17

## Context

Network retries, double clicks, and proxy retries can deliver the same submission twice. A repeat must not consume a second question, and the client should still learn the result.

## Options considered

1. **Deduplicate by question text only** — cannot distinguish a retry from a deliberate repeat; does not return the original result.
2. **Client-generated `Idempotency-Key` header (UUID v4) stored server-side** — standard pattern (as used by payment APIs); exact replay semantics.

## Decision

- `POST /game/today/questions` requires `Idempotency-Key`. The SPA creates it once per user submission and reuses it only for retries of that submission.
- The key is scoped to `game_date` and player, stored with the SHA-256 of the request body, inside the same `reserve` script.
- States: `pending` (returns `409 QUESTION_IN_PROGRESS`), `done` (replays the stored response with `Idempotent-Replayed: true`). A different body with the same key returns `422 IDEMPOTENCY_KEY_REUSED`.
- On `release` (AI failure) the pending record is deleted, so retrying the same key is allowed and still free.

## Consequences

- Exactly-once charging per submission.
- Repeated questions with new keys are handled separately by duplicate detection (OQ-05).
- Records expire with the day keys (ADR 0004).
