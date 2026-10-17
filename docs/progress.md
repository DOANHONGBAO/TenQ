# Progress

## Status

Phase: **0 — Engineering workspace bootstrap**. No application code yet.
Blocked on: approved product specification (`docs/product-spec.md`).

## Log

### 2026-10-17 — Workspace bootstrap (`chore/claude-workspace`)

Done:
- Renamed `docs/requirements.md` to `docs/product-spec.md`; placeholder lists expected sections only, no invented rules.
- Added `docs/engineering-conventions.md`, `docs/development-workflow.md`, ADR 0002 (Proposed), ADR index and template.
- Rewrote `CLAUDE.md` (shorter; owner-only authorship and no-push rules; links to new docs).
- Added `.gitignore` and `.editorconfig`.
- Replaced a literal U+202E (bidi override) character in the AI judge injection corpus with its escaped form.

Known issue: commit `7b95005` on `main` carries `Co-Authored-By` / `Claude-Session` trailers. Removing them requires rewriting `main`; owner decision pending.

### 2026-10-17 — Claude Code tooling (`chore/claude-tooling`, PR #1, merged)

- Added `.claude/settings.json` (official marketplace, 7 plugins, `.env` read deny rules), three project skills, `CLAUDE.md`, ADR 0001, docs skeleton.
- Deferred (ADR 0001): Playwright MCP, Context7, GitHub MCP, code-review plugin.

## Next

1. Owner provides the approved specification → fill `docs/product-spec.md`.
2. Write `docs/architecture.md` from the spec; ADRs for storage split (Redis vs SQLite) and identity (signed cookie).
3. Scaffold `backend/` and `frontend/` per `docs/engineering-conventions.md`, with CI running lint, type check, and tests.
