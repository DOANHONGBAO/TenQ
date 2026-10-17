# ADR 0004: UTC game day and calendar-based key expiration

- Status: Proposed
- Date: 2026-10-17

## Context

The game resets at 00:00 UTC (BR-03). Keys need cleanup, and requests can straddle midnight.

## Options considered

1. **Fixed TTL of 24 h from key creation** — a game started at 23:50 would survive until 23:50 the next day; expiry does not match the business day and is hard to reason about.
2. **Key namespaced by `game_date` + `EXPIREAT` at a fixed UTC instant** — the day boundary comes from the key name; expiry is only cleanup.

## Decision

- One function computes `game_date` (UTC) from an injectable clock; nothing else reads the system clock.
- All per-day keys include `game_date` and expire with `EXPIREAT` at 00:00 UTC of `game_date + 2 days`.
- `game_date` is fixed when a question is reserved; its commit applies to that day even if it finishes after midnight.
- `next_reset_at` and `server_time` are returned to the client; the UI never relies on the device clock or timezone.

## Consequences

- The reset is exact and independent of key age.
- One extra day of retention allows late commits, leaderboard reads, and the result retry queue.
- Tests freeze the clock at boundary instants (23:59:59.999, 00:00:00.000) and across leap days.
