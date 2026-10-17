# ADR 0009: Redis persistence settings and SQLite as the durable record

- Status: Proposed
- Date: 2026-10-17

## Context

Redis holds live state. A container restart or VM reboot must not wipe today's attempt counters (that would let players re-ask questions) or the leaderboard.

## Options considered

1. **Redis without persistence** — fastest; any restart resets the day. Rejected.
2. **RDB snapshots only** — compact, but can lose minutes of writes.
3. **AOF `appendfsync everysec` + RDB** — at most about 1 s of writes lost on a crash; the standard production balance.
4. **AOF `always`** — no loss, much slower; unnecessary here.
5. **Everything in SQLite, no Redis** — simpler, but atomic counters, TTLs, and rate limits would be reimplemented; the stack already chose Redis.

## Decision

- Redis: AOF `everysec` plus RDB, data on a named Docker volume, `maxmemory 256mb`, `maxmemory-policy noeviction`, password required, internal network only.
- SQLite is the durable record for pinned puzzles and completed results. Results are written after `commit` with `INSERT OR IGNORE`; failures go to a Redis retry list drained by a background task.
- If Redis data is lost, the leaderboard is rebuilt from SQLite; live in-progress games for that day are lost (documented residual risk).

## Consequences

- A clean restart loses nothing; a hard crash loses at most about a second.
- `noeviction` turns memory pressure into visible `503` errors rather than silent rule violations.
- Two stores must stay consistent for results; idempotent writes make retries safe.
- Backups cover SQLite (nightly) and Redis RDB (daily copy).
