# TenQ.ai — Claude Code Guide

Daily AI 10-questions deduction game. Zero-login, single-player: every player gets the same secret per game day and at most 10 questions answered by an AI judge.

## Read before changing code

1. `docs/product-spec.md` — product rules; the only source of gameplay requirements. If a rule is missing, ask the owner — do not invent it.
2. `docs/architecture.md` — components and data flow
3. `docs/decisions/` — ADRs; propose a new ADR instead of silently contradicting one
4. `docs/engineering-conventions.md` — code style, structure, errors, logging, testing, security
5. `docs/development-workflow.md` — task loop, branching, commits, PRs
6. `docs/progress.md` — current status and next step

## Stack

React + TypeScript + Vite (Vercel) · FastAPI + Pydantic (Python) · Ollama Cloud · Redis + SQLite · Cloudflare Turnstile, signed HttpOnly cookies · Docker Compose + Nginx on Oracle Cloud Always Free · GitHub Actions · pytest + Playwright

## Hard rules

- Branch per task (`feat/*`, `fix/*`, `chore/*`, `docs/*`); never commit to `main`.
- Never push, merge, deploy, or change cloud resources. The project owner pushes all code.
- Commits are authored solely by the owner: no `Co-Authored-By`, `Claude-Session`, or other AI trailers; no "Generated with" lines in PR text; commit with `--no-gpg-sign`.
- Free/open-source and free tiers only; flag anything that could incur cost.
- Never print, log, commit, or return secrets (daily secret word, API keys, cookie secrets, tokens).
- Never claim tests passed unless they ran in this session; report the exact command.
- Code, identifiers, comments, commits, and docs in English. Explanations to the owner in Vietnamese.
- End every task by updating `docs/progress.md`.

## Project skills (`.claude/skills/`)

- `tenq-game-integrity` — daily secret, 10-attempt limit, concurrency, idempotency, leaderboard
- `tenq-ai-judge-testing` — Ollama client, output validation, prompt injection, caching, provider errors
- `tenq-deployment-audit` — Docker, Nginx, CI/CD, environments, free-tier and production safety

## Commands

None yet. Add exact build, lint, type-check, and test commands here when `backend/` and `frontend/` are scaffolded.
