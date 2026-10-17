# Roadmap

Every phase must keep the code typed, tested, and readable for a public repository (NFR-07). Each phase ends with a report, an owner review, and an owner push/merge. A phase starts only after the owner approves it. Commands are the intended ones; exact commands are fixed in `CLAUDE.md` once the tooling exists.

| Phase | Scope | Status |
|-------|-------|--------|
| 01 | Requirements and architecture (this document set) | Done |
| 02 | Repository and local development setup | Done (PR #2) |
| 02b | Backend foundation remainder and CI | Planned |
| 03 | Daily secret word engine | In review |
| 03b | Remaining domain rules (pure logic) | Planned |
| 04 | Redis game store and concurrency | Planned |
| 05 | AI judge adapter | Planned |
| 06 | Identity, Turnstile, rate limiting | Planned |
| 07 | API endpoints, SQLite, leaderboard | Planned |
| 08 | Frontend | Planned |
| 09 | End-to-end tests and full CI | Planned |
| 10 | Infrastructure and first deployment | Planned |
| 11 | Hardening, observability, launch | Planned |

## Phase 02 — Repository and local development setup

Scope (as requested by the owner): branch `feature/project-bootstrap`; Python 3.12 backend managed by uv with modules `api`, `core`, `models`, `schemas`, `services`, `repositories`, `integrations`; Pydantic settings with `local` / `test` / `production`; `GET /api/v1/health`; Ruff and pytest; React + TypeScript (strict) + Vite frontend with ESLint and a starter page calling the health endpoint; `.env.example` files; README with setup steps. No Ollama, Redis, or Turnstile.

Acceptance criteria:
- `TENQ_ENV` missing makes the app fail at startup with a validation error.
- Production settings reject `http://` CORS origins and `DEBUG` logging; API docs are disabled.
- FastAPI and Vite start locally; the starter page shows the backend status through the Vite proxy.
- Lint, type check, build, and tests pass locally.

Tests: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest` and `cd frontend && npm run lint && npm run build`

## Phase 02b — Backend foundation remainder and CI

Scope: error envelope and exception handlers, request id middleware, `/ready`, pyright strict, Docker Compose for local Redis, GitHub Actions CI (ruff, pyright, pytest, ESLint, `tsc`, secret scan).

Acceptance criteria:
- Unknown routes and unhandled exceptions return the error envelope without stack traces.
- CI passes on a pull request and runs only with `contents: read`.

Tests: `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest`

## Phase 03 — Daily secret word engine

Scope (owner brief, 2026-10-17): UTC clock abstraction and `game_date`; `DailyGameConfig`; SQLite `words` table with 365 curated entries and metadata; seed command with validation; keyed yearly permutation with explicit leap-day and year-boundary rules (ADR 0012); daily pinning in `daily_puzzles`; `DailyWordService`; `GET /puzzles/today` and `GET /puzzles/{date}/answer`; minimal error envelope. No AI, Redis, or game frontend.

Acceptance criteria:
- Same word for every timezone within one UTC day; change exactly at 00:00:00 UTC.
- Restart and word list edits do not change a pinned day.
- Common years use every word once; leap years repeat exactly one word, at least 183 days apart; no word on consecutive days, including 31 December to 1 January.
- The word never appears in today's API responses, OpenAPI schema, logs, or reprs.
- Seeding rejects wrong counts, duplicates, invalid words, and definitions that contain the word.

Tests: `uv run pytest`

## Phase 03b — Remaining domain rules

Scope: question validation and normalization, label enum, WIN verification, state transition rules, leaderboard score function. No I/O.

Acceptance criteria:
- Every rule in requirements OQ-03 and OQ-04 has a positive and a negative test.
- Coverage of `models/` is at least 90%.

## Phase 04 — Redis game store and concurrency

Scope: Lua `reserve` / `commit` / `release`, Redis adapter, idempotency, duplicate detection, EXPIREAT, rate limit counters.

Acceptance criteria:
- 50 concurrent reserves for one fresh player result in exactly one lease.
- Simulated full games never exceed 10 charged questions under concurrent load.
- Replay returns the stored response; reused key with a different body is rejected.
- Expired lease is ignored; stale commit is rejected and charges nothing.

Tests: `docker compose -f infra/compose.dev.yml up -d redis && uv run pytest tests/integration -m redis`

## Phase 05 — AI judge adapter

Scope: `JudgeProvider` protocol, Ollama Cloud client (httpx), prompt with `prompt_version`, strict parser, WIN verification, judgement cache, daily budget, concurrency cap, retries, usage logging.

Acceptance criteria:
- Fake provider covers: valid label, garbage, timeout, 429 with `Retry-After`, 500, unverified WIN, slow response beyond the deadline.
- Injection corpus never produces an accepted forged WIN.
- No test contacts the real provider unless `TENQ_LIVE_AI=1` and marked `live_ai`.

Tests: `uv run pytest -m "not live_ai"`; optional `TENQ_LIVE_AI=1 uv run pytest -m live_ai`

## Phase 06 — Identity, Turnstile, rate limiting

Scope: signed cookie with key rotation, `POST /session`, Turnstile siteverify client (with Cloudflare's test keys), IP hashing, session and question limits.

Acceptance criteria:
- Tampered, expired, or unsigned cookies are rejected; rotated keys keep old sessions valid.
- Turnstile failure or timeout never creates a session.
- Rate limits return `429` with `Retry-After`.

Tests: `uv run pytest tests -k "session or turnstile or rate_limit"`

## Phase 07 — API endpoints, SQLite, leaderboard

Scope: all endpoints in `api-contract.md`, SQLite migrations, puzzle pinning, results writer with retry queue, leaderboard (today from Redis, past from SQLite), answer endpoint for past dates.

Acceptance criteria:
- Response shapes match `api-contract.md` (contract tests against the generated OpenAPI schema).
- Answer for today returns `403`; for yesterday returns the word.
- Leaderboard order follows BR-10 including ties.
- A full game (10 questions, and a WIN game) works end to end against real Redis with a fake judge.

Tests: `uv run pytest`

## Phase 08 — Frontend

Scope: Vite + React + TypeScript app, game screen, history, remaining counter, countdown to reset, Turnstile widget, leaderboard, yesterday's answer, error states (AI unavailable, rate limited), accessibility basics.

Acceptance criteria:
- No secret or backend URL other than relative `/api` in the bundle.
- Retries reuse the same `Idempotency-Key`; input disabled while a question is in flight.
- Vitest covers state handling and error mapping.

Tests: `npm ci && npm run lint && npm run typecheck && npm run test`

## Phase 09 — End-to-end tests and full CI

Scope: Playwright against a local stack (API + Redis + fake judge + Turnstile test keys), CI job running it, coverage reporting.

Acceptance criteria:
- E2E: new session, ask questions, win, leaderboard shows the player; exhaust 10 questions; AI outage does not charge.
- CI blocks merge on any failure.

Tests: `npx playwright test`

## Phase 10 — Infrastructure and first deployment

Scope: production Dockerfiles (arm64, non-root), Compose for production, Nginx (TLS, origin secret, rate limit, headers), Let's Encrypt IP certificate, Oracle VM hardening, Vercel project with rewrites, GitHub Actions deploy with a protected environment, backups.

Start with a **connectivity spike** (can be pulled forward): Vercel rewrite to the VM with Set-Cookie, forwarded IP, timeout, and certificate renewal verified.

Acceptance criteria:
- Direct requests to the VM without the origin secret get `403`.
- Redis and API ports are not reachable from the internet (verified with an external port scan).
- Deploy is repeatable and has a documented rollback.
- `tenq-deployment-audit` review has no Critical or High findings.

Tests: `docker compose config`, `nginx -t`, external `curl` checks, `actionlint`, `hadolint`.

## Phase 11 — Hardening, observability, launch

Scope: uptime monitoring, usage dashboards from logs, AI budget calibration, backup restore drill, dependency and container scans, privacy notice, README for the portfolio.

Acceptance criteria:
- Restore from backup tested on a fresh VM.
- `pip-audit`, `npm audit`, and Trivy have no unresolved High findings.
- README explains architecture, decisions, and how to run locally.
