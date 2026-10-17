# Progress

## Status

Phase: **0 — Engineering environment setup**. No application code yet.

## Log

### 2026-10-17 — Claude Code tooling (`chore/claude-tooling`)

Done:
- Added `.claude/settings.json`: official plugin marketplace, 7 enabled plugins (feature-dev, pr-review-toolkit, commit-commands, claude-md-management, pyright-lsp, typescript-lsp, security-guidance), deny rules for reading `.env` files.
- Added project skills: `tenq-game-integrity`, `tenq-ai-judge-testing`, `tenq-deployment-audit`.
- Added `CLAUDE.md`, this file, ADR 0001, and placeholder `requirements.md` / `architecture.md`.

Deferred (see ADR 0001): Playwright MCP, Context7, GitHub MCP, code-review plugin.

## Next

1. Write `docs/requirements.md` (gameplay rules: game day timezone, question types allowed, attempt refund policy on AI failure, leaderboard rules).
2. Write `docs/architecture.md` and ADRs for storage split (Redis vs SQLite) and identity (signed cookie).
3. Scaffold backend (FastAPI + pytest) and frontend (Vite + TS) with CI running lint, type check, and tests.
