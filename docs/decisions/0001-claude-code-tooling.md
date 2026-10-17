# ADR 0001: Claude Code tooling for the repository

- Status: Accepted
- Date: 2026-10-17

## Context

Development is done with Claude Code, both in ephemeral cloud sessions started from claude.ai and potentially locally. Cloud containers are discarded at session end, and in those sessions plugin-provided MCP servers are not started. We want a reproducible, minimal, trusted tool set that works in both environments.

## Decision

1. Declare the official marketplace `anthropics/claude-plugins-official` and enable plugins in the committed `.claude/settings.json`, so every Claude Code session on this repo gets the same set:
   - `feature-dev` — structured feature workflow (explore, design, review agents)
   - `pr-review-toolkit` — specialized review agents (tests, error handling, types, silent failures)
   - `commit-commands` — commit / push / PR commands
   - `claude-md-management` — keep `CLAUDE.md` accurate
   - `pyright-lsp`, `typescript-lsp` — type-aware code intelligence (require `pyright-langserver` and `typescript-language-server` on PATH)
   - `security-guidance` — pattern warnings on edits and LLM diff review on stop
2. Keep domain review knowledge in project skills under `.claude/skills/` (committed, versioned with the code).
3. Deny Claude read access to `.env`, `.env.local`, `.env.*.local`, `.env.production`, and `secrets/`.

## Deferred

- **Playwright MCP, Context7, GitHub MCP**: MCP-based; not functional in our cloud sessions, and Context7/GitHub require extra auth. Playwright is used as a test dependency (`@playwright/test`) instead. Revisit for local development.
- **code-review plugin**: overlaps with `pr-review-toolkit`; its PR-comment posting needs an authenticated `gh`.
- **frontend-design plugin**: an equivalent skill is already available in the environment.

## Consequences

- `security-guidance` runs Python hooks on every edit and prompt and an LLM review on stop: more latency and token usage in exchange for earlier security feedback. Disable per-user if it becomes disruptive.
- Contributors must trust the official marketplace when Claude Code prompts on first open.
- No community plugins are used; adding one requires a new ADR.
- Claude never pushes; the owner pushes all branches. `commit-commands` may add AI attribution trailers by default, so its output must be checked before committing.
