# ADR 0002: Engineering conventions and workflow

- Status: Proposed
- Date: 2026-10-17

## Context

The repository has no application code yet. Fixing conventions before scaffolding avoids reformatting and restructuring later, and gives Claude Code consistent rules to follow across sessions. Constraints: free tooling only, a single owner who is learning professional practice, Python + TypeScript stack.

## Options considered

1. **Python deps: uv** — fast, lockfile, manages Python versions; newer tool. **pip-tools / Poetry** — mature; slower (Poetry) or more manual (pip-tools).
2. **Python lint/format: ruff** — one tool replaces flake8, isort, black. **black + flake8 + isort** — three tools, same result.
3. **JS package manager: npm** — ships with Node, no extra install. **pnpm** — faster, stricter; one more tool to learn.
4. **Backend layering: api / services / domain / adapters** — testable pure domain; more folders. **Flat routers with logic** — fewer files; game rules become hard to test without HTTP and Redis.
5. **Merge strategy: squash** — linear `main`, one commit per PR. **Merge commits** — preserves branch history; noisier log.

## Decision

Adopt the conventions in `docs/engineering-conventions.md` and the workflow in `docs/development-workflow.md`: uv, ruff, pyright strict, npm, ESLint + Prettier, layered backend, feature-folder frontend, Conventional Commits, squash merge, owner-only authorship.

## Consequences

- Game rules can be unit-tested without Redis or HTTP.
- More initial structure than a prototype needs; accepted because the project's goal is production practice.
- uv and ruff must be installed in CI and locally.
- Revisit if a tool becomes unmaintained or a free-tier constraint conflicts.
