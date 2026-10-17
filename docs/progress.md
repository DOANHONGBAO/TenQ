# Progress

## Status

Phase: **01 — Requirements and architecture (in review)**. No application code yet.
Next: Phase 02 after owner approval of Phase 01 and of the open questions in `requirements.md` section 4.

## Log

### 2026-10-17 — Phase 01: requirements and architecture (`docs/phase-01-architecture`)

Done:
- `docs/requirements.md` (renamed back from `product-spec.md`): BR-01 to BR-12 approved by owner, NFR-01 to NFR-08, open questions OQ-01 to OQ-10 with proposed defaults, traceability table.
- `docs/architecture.md`: system, request sequence, concurrency, and state machine diagrams (Mermaid); responsibilities; AI lifecycle; deployment; free-tier table; rate limits; persistence; secrets; failure matrix.
- `docs/api-contract.md`, `docs/data-model.md`, `docs/security-threat-model.md`, `docs/roadmap.md`.
- ADR 0003 to 0011 (all Proposed).
- Skills aligned: judge checklist uses the five labels and label-only output; game invariants A2, A4, L3 match the design.

Key decisions (Proposed):
- Redis Lua reserve / commit / release with one lease per player (ADR 0003).
- Per-day keys with `EXPIREAT` at 00:00 UTC of day + 2 (ADR 0004).
- `Idempotency-Key` on question submissions (ADR 0005).
- Signed random-id cookie, HMAC-hashed ids and daily-salted IP hashes (ADR 0006).
- Vercel external rewrite to the Oracle VM with an origin secret and a Let's Encrypt IP certificate (ADR 0007).
- Keyed per-cycle permutation for the word, pinned daily in SQLite; list and seed only on the VM (ADR 0008).
- Redis AOF `everysec` + RDB, `noeviction`; SQLite for durable results (ADR 0009).
- Single-label judge output with strict parsing and server-verified WIN (ADR 0010).
- Free-tier limits and degradation policy (ADR 0011).

Facts checked on 2026-10-17 (official pages): Ollama Cloud plans and API, Oracle Always Free limits and idle reclamation, Vercel Hobby limits and rewrites, Turnstile plan limits, Let's Encrypt IP certificates.

### 2026-10-17 — Workspace bootstrap (`chore/claude-workspace`)

- Conventions, workflow, ADR 0002, ADR index and template, `.gitignore`, `.editorconfig`; fixed a literal U+202E character in the injection corpus.
- `main` history rewritten by the owner to remove AI attribution trailers (done 2026-10-17).

### 2026-10-17 — Claude Code tooling (PR #1, merged)

- `.claude/settings.json` (official marketplace, 7 plugins, `.env` read deny rules), three project skills, `CLAUDE.md`, ADR 0001.

## Open issues

| ID | Issue | Owner action |
|----|-------|--------------|
| I-01 | OQ-01 to OQ-10 need confirmation | Review `requirements.md` section 4 |
| I-02 | Vercel rewrite behavior (Set-Cookie, forwarded IP, timeout) not yet tested in practice | Approve an early connectivity spike or keep it in Phase 10 |
| I-03 | Ollama Cloud free quota has no published numbers | Measure in Phase 05; budget set in Phase 11 |
| I-04 | Oracle idle reclamation risk for a lightly used VM | Decide later whether Pay As You Go is acceptable (ADR 0011) |
| I-05 | Whether Ollama Cloud honors `format` is unverified | Not needed by the design (ADR 0010) |
| I-06 | Branch `chore/claude-workspace` not yet pushed; this branch is stacked on it | Push and merge it first |
