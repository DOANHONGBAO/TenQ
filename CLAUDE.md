# TenQ.ai — Claude Code Guide

Daily AI 10-questions deduction game. Zero-login, single-player. Every player gets the same secret per game day and at most 10 questions answered by an AI judge.

## Read first

1. `docs/requirements.md` — product rules (source of truth for gameplay)
2. `docs/architecture.md` — components and data flow
3. `docs/decisions/` — ADRs; do not contradict an accepted ADR without proposing a new one
4. `docs/progress.md` — current status and next step

## Stack

- Frontend: React + TypeScript + Vite (hosted on Vercel)
- Backend: Python, FastAPI, Pydantic
- AI: Ollama Cloud API
- Storage: Redis (game state, cache), SQLite (durable data)
- Security: Cloudflare Turnstile, signed HttpOnly cookies
- Infra: Docker, Docker Compose, Nginx on Oracle Cloud Always Free
- CI/CD: GitHub Actions; tests: pytest, Playwright

## Rules

- Work on feature branches (`feat/*`, `fix/*`, `chore/*`); never commit to `main` directly.
- Do not push, merge, deploy, or change cloud resources without explicit approval.
- Free/open-source and free tiers only; flag anything that could incur cost.
- Never print, log, commit, or return secrets: the daily secret word, API keys, cookie secrets, tokens. `.env` files are denied to Claude by `.claude/settings.json`.
- Never report tests as passing unless they were executed in this session.
- Code, identifiers, comments, commit messages, and docs: English. Explanations to the user: Vietnamese.
- Update `docs/progress.md` at the end of every task.

## Project skills

Located in `.claude/skills/`:

- `tenq-game-integrity` — secret selection, 10-attempt limit, concurrency, idempotency, leaderboard
- `tenq-ai-judge-testing` — Ollama client, output validation, prompt injection, caching, provider errors
- `tenq-deployment-audit` — Docker, Nginx, CI/CD, environments, free-tier and production safety

## Commands

Not defined yet — add build, test, and lint commands here once the backend and frontend are scaffolded.
