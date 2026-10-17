# Architecture Decision Records

An ADR records one significant decision: its context, the choice, and the consequences. ADRs are immutable once accepted — to change a decision, add a new ADR that supersedes the old one and update the old one's status.

## When to write one

- Choosing or replacing a framework, service, datastore, or hosting target
- Changing a security boundary, data model, or public API contract
- Accepting a known trade-off or limitation

## Process

1. Copy `template.md` to `NNNN-short-title.md` (next number, zero-padded).
2. Status `Proposed` in the PR; set to `Accepted` when the PR is merged.
3. Link the ADR from `docs/progress.md` and, if relevant, `docs/architecture.md`.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-claude-code-tooling.md) | Claude Code tooling for the repository | Accepted |
| [0002](0002-engineering-conventions.md) | Engineering conventions and workflow | Proposed |
| [0003](0003-atomic-game-state-redis-lua.md) | Atomic game state with Redis Lua scripts and a single question lease | Proposed |
| [0004](0004-utc-game-day-and-expiration.md) | UTC game day and calendar-based key expiration | Proposed |
| [0005](0005-idempotency-keys.md) | Idempotency keys for question submissions | Proposed |
| [0006](0006-anonymous-identity.md) | Anonymous identity with a signed random-id cookie | Proposed |
| [0007](0007-vercel-proxy-to-oracle-origin.md) | Vercel external rewrite to the Oracle origin over HTTPS | Proposed |
| [0008](0008-secret-word-management.md) | Secret word list, keyed selection, and daily pinning | Proposed |
| [0009](0009-redis-durability-and-sqlite-results.md) | Redis persistence settings and SQLite as the durable record | Proposed |
| [0010](0010-ai-judge-output-contract.md) | AI judge output contract without relying on structured outputs | Proposed |
| [0011](0011-free-tier-constraints.md) | Operating within free tiers and degrading gracefully | Proposed |
