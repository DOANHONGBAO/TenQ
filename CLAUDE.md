# TenQ.ai — Claude Code Guide

Daily AI 10-questions deduction game. Zero-login, single-player: every player gets the same secret per game day and at most 10 questions answered by an AI judge.

## Read before changing code

1. `docs/requirements.md` — product rules; the only source of gameplay requirements. If a rule is missing, ask the owner — do not invent it.
2. `docs/architecture.md`, `docs/api-contract.md`, `docs/data-model.md`, `docs/security-threat-model.md` — design; code must match them or update them in the same PR
3. `docs/decisions/` — ADRs; propose a new ADR instead of silently contradicting one
4. `docs/engineering-conventions.md` — code style, structure, errors, logging, testing, security
5. `docs/development-workflow.md` — task loop, branching, commits, PRs
6. `docs/roadmap.md` and `docs/progress.md` — phase scope, acceptance criteria, current status. Work one phase at a time; never start the next phase without owner approval.

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

Tools run on the Fedora host (inside the Ubuntu distrobox, prefix them with `distrobox-host-exec`).

```bash
# Backend (from backend/)
uv sync                                                    # install exact versions from uv.lock
uv run uvicorn app.main:create_app --factory --reload      # http://127.0.0.1:8000/api/v1/health
uv run ruff check . && uv run ruff format --check .        # lint + format check
uv run pytest                                              # tests (Redis tests need tenq-redis-test on :6390)
uv run python -m app.scripts.seed_words --dev               # seed fake words (or: secrets/words.json)
uv run python -m app.scripts.evaluate_judge                 # judge accuracy report (mock; --live costs quota)
TENQ_LIVE_AI=1 uv run pytest -m live_ai                     # opt-in real Ollama smoke test (2 requests)

# Frontend (from frontend/)
npm ci                                                     # install exact versions from package-lock.json
npm run dev                                                # http://localhost:5173 (proxies /api to :8000)
npm run lint                                               # ESLint, zero warnings allowed
npm test                                                   # Vitest component tests
npm run test:e2e                                           # Playwright E2E (npx playwright install chromium once)
npm run build                                              # tsc -b type check + production build

# Containers (repo root; podman-compose works the same)
infra/scripts/gen-env.sh && docker compose up -d --build   # nginx on 127.0.0.1:8080
infra/scripts/smoke.sh                                     # end-to-end checks through nginx
infra/scripts/integration.sh                               # container integration test (own compose project)
```
