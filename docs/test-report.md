# Test Report — Phase 09 (Quality Assurance)

- Date: 2026-10-17. Machine: Fedora 44 host (x86_64), Python 3.12.15, Node 22.23.1, Redis 7.2.16 (Podman), Podman 5.8.7 + podman-compose 1.6.0, Playwright 1.64.1 (Chromium headless shell).
- Everything below was executed in this session unless marked **not run**. Numbers are copied from the command output.

## 1. How to reproduce

```bash
# Backend (needs the test Redis: podman run -d --name tenq-redis-test -p 127.0.0.1:6390:6379 docker.io/library/redis:7.2-alpine)
cd backend
uv run ruff check . && uv run ruff format --check .
uv run pytest --cov --cov-report=term --cov-report=xml:coverage.xml --cov-report=html:htmlcov
uv run pytest -q --cov=app/models --cov=app/services --cov=app/repositories --cov=app/core --cov-fail-under=80

# Frontend
cd frontend
npm run lint && npm test && npm run build
npx playwright install chromium && npm run test:e2e

# Containers (Docker: COMPOSE="docker compose"; default podman-compose)
infra/scripts/integration.sh          # separate "tenq-it" project, its volumes are removed at the end
infra/scripts/smoke.sh                 # against an already running stack

# Load test (offline: mock judge, local Siteverify stub, test Redis db 10)
#   1) start tools.loadtest_server with TENQ_AI_JUDGE=mock and raised limits (see section 6)
#   2) uv run python -m tools.loadtest --players 100 --questions 8 --concurrency 50 \
#        --redis redis://127.0.0.1:6390/10 --server-log /tmp/tenq-load-server.log
```

CI: `.github/workflows/ci.yml` runs the same commands in three jobs (backend with a Redis service, frontend with Playwright, containers with `docker compose`). Actions are pinned by commit SHA and the workflow has `contents: read` only. **The workflow has not run yet** (it runs after the branch is pushed).

## 2. Results

| Suite | Command | Result |
|-------|---------|--------|
| Backend lint/format | `ruff check`, `ruff format --check` | clean (78 files) |
| Backend tests | `pytest` | **336 passed**, 1 deselected (opt-in `live_ai`) |
| Frontend lint / unit+component | `npm run lint`, `npm test` | clean, **31 passed** |
| Frontend build | `npm run build` | OK |
| E2E (Playwright) | `npm run test:e2e` | **14 passed** (7 scenarios × desktop 1280×860 and Pixel 7) |
| Container integration | `infra/scripts/integration.sh` | **11/11** on the final run. Six runs while building the script: the first two failed at the persistence step (the first used the developer stack whose rate-limit counters were already used; the second cause was not isolated, after which an explicit session check was added), one aborted at the restart step (bug below), and the last three passed, the final one after the fix |
| Edge smoke (inside integration) | `infra/scripts/smoke.sh` | **13/13** |
| Load test | `tools.loadtest` | see section 6 |
| Live Ollama | `pytest -m live_ai` | **not run** (owner opt-in, costs quota) |
| Docker Engine / arm64 image | — | **not run** (no Docker or arm64 emulation on this host) |

## 3. Coverage (pytest-cov, branch coverage)

- Whole backend: **89%** (`coverage report --format=total`). The two uncovered modules are owner tools that call the real API (`scripts/check_ollama_models.py`, `scripts/evaluate_judge.py`, 0%).
- Business logic (`app/models`, `app/services`, `app/repositories`, `app/core`): **95.80%**, gate `--cov-fail-under=80` passes.

| Module | Cover | Module | Cover |
|--------|-------|--------|-------|
| models/clock, daily_game, game, guess, hints, judge_rules, question | 100% | services/game_service | 95% |
| models/word_schedule | 99% | services/daily_word_service | 96% |
| models/word | 88% | services/session_service | 98% |
| repositories/abuse_store, judge_cache | 100% | services/judge_service | 90% |
| repositories/game_store | 97% | core/session | 94% |
| repositories/word_repository | 95% | core/client_ip, circuit_breaker | 100% |
| repositories/database | 93% | core/middleware | 93% |

Uncovered lines are mostly defensive branches (`pragma`-free fallbacks such as Redis errors while releasing a lock) and the human-readable log formatter; they were reviewed, not padded with tests.

## 4. What the pyramid covers (mapping to the Phase 09 brief)

**Unit**: daily word selection and leap years (`test_word_schedule.py`), UTC reset and timezones (`test_clock.py`), state transitions and attempt counting (`test_game_rules.py`, `test_game_service.py`), leaderboard ranking and tie-breaks (`test_game_service.py`), JSON output validation (`test_judge_rules.py`), question normalization (`test_game_rules.py`), idempotency (`test_game_service.py`, `test_qa_hardening.py`), cookie signing and rotation (`test_security.py`), cache keys (`test_judge_service.py`), hints and guesses (`test_hints_and_guess.py`).

**Integration**: FastAPI + Redis (game, judge cache, abuse store), FastAPI + SQLite (puzzles, seeding, migration 0002), FastAPI + MockOllamaProvider (`test_judge_api.py`), FastAPI + mocked Siteverify (`test_security.py`), Nginx + backend, Redis persistence, container start/stop and graceful shutdown (`integration.sh`).

**Concurrency**: 50 concurrent submissions never exceed 10 charges; 50 parallel Lua reservations grant one lease; 12 sessions in parallel stay isolated; the same Idempotency-Key 12 times in parallel charges once; a request crossing 00:00 UTC commits to its own day; an expired judge lock left by a dead process does not block; a cancelled (interrupted) Ollama request is released and not charged; 20 identical new questions in one process and 9 across three "processes" make one model call.

**Security**: prompt-injection corpus and forced-WIN attempts; spoofed `X-Forwarded-For`/`X-Real-IP` at app and Nginx level; forged, tampered, expired, and wrong-key cookies; Turnstile token replay, expiry, missing token, wrong hostname/action, test keys in production, Siteverify outage (fail closed); every game route refuses calls without a session (no Turnstile bypass); body-size and input validation; payload fields that try to set attempts, status, hints, or dates; daily AI budget exhaustion (polite 503, not charged); a full losing game plus every read endpoint and the OpenAPI schema never contain the secret word, and neither do the logs.

**E2E** (fake API and Turnstile stub via `page.route`, offline): first visit with exactly one Turnstile token and widget reset; a full 10-question losing game then refresh; refresh mid-game keeps attempts, history, and hints; win through the guess box with focus on the result and share button; leaderboard rows; maintenance screen and recovery; no horizontal overflow on desktop and Pixel 7.

## 5. Bugs found and fixed

| Phase | Bug | Fix | Guarded by |
|-------|-----|-----|-----------|
| 09 | `integration.sh`/`smoke.sh` aborted silently on the first failed check (`set -e` with a `cmd; check $?` pattern), and the state read after a restart raced container readiness — the cause of the earlier unexplained failures | no `set -e` in the test scripts, every step reports through `check`; state reads retry for up to 30 s; curl failures print `000` | `integration.sh`: two consecutive full passes after the fix (Phase 10) |
| 09 | Frontend test "unlocks one hint after every two tries" failed once on GitHub (PR #9) because it waited only 1 s for the hint on a slower runner | waits for the guess feedback first, 5 s timeouts | 5 consecutive local runs |
| 09 | Integration runs shared the developer's stack and volumes, so earlier manual rate-limit counters caused a 429 | runs in a separate `tenq-it` compose project and removes its volumes | `integration.sh` |
| 08 | After restarting only the API container, Nginx kept its old IP and returned 503 | `resolver` + `server api:8000 resolve` (re-resolve every 10 s) | manual restart test, `integration.sh` |
| 08 | Bind mounts unreadable on SELinux hosts; map bucket too small for a 64-char secret; image default server shadowed the config; `burst=0` invalid | `,z` mounts, `map_hash_bucket_size 128`, template renders `default.conf`, no-burst limit | `integration.sh`, smoke |
| 07 | Double click could send two submissions before React re-rendered | synchronous ref guard | `App.test.tsx` double-click test |
| 07 | Reset countdown never rendered (state set from a ref before it was updated) | countdown computed from a ticking `now` and the reducer's offset | `App.test.tsx` timer test |
| 06 | Cloudflare test keys return one dummy token, so the replay guard blocked every second local session | replay guard disabled only for test keys (refused in production) | `test_security.py` replay test |
| 05 | gpt-oss spent `num_predict` on reasoning and returned truncated JSON; a wrong explicit guess got WIN from the model | `think=low` guidance, `num_predict` 512, truncation logging; deterministic NO for wrong explicit guesses | `test_judge_rules.py`, live evaluation |
| 05 | Fixed-clock tests would fail after 2026-10-19 because keys used absolute `EXPIREAT` | TTL computed from the application clock | TTL tests |

No new product defects were found by the tests added in this phase; the new tests passed on their first run after test-setup corrections (they initially hit the intended per-device session limit and per-player question limit, which confirmed those limits work).

## 6. Load test (measured, offline)

Setup: one uvicorn worker started by `tools/loadtest_server.py` on the same laptop as the load generator; `TENQ_AI_JUDGE=mock` (MockOllamaProvider through the real judge pipeline, no Ollama), Siteverify answered locally (no Cloudflare), Redis 7.2 test instance db 10, abuse limits raised so the run measures throughput instead of rate limiting. Each virtual player: session, game state, 8 questions sampled from a 30-question pool, leaderboard. Not run through Nginx (its 1 question per 2 s per IP would throttle a single-IP generator by design).

| Run | Players × questions | Concurrency | Requests | Time | Throughput | Errors |
|-----|---------------------|-------------|----------|------|------------|--------|
| 1 (cold judge cache) | 100 × 8 | 50 | 1100 | 4.47 s | 246.0 req/s | 0 (0.0%) |
| 2 (warm cache) | 100 × 8 | 10 | 1100 | 4.73 s | 232.7 req/s | 0 (0.0%) |

Latency (ms):

| Endpoint | Run 1 p50 / p95 / max | Run 2 p50 / p95 / max |
|----------|-----------------------|-----------------------|
| POST /session | 237.0 / 307.8 / 365.6 | 37.4 / 57.7 / 96.3 |
| GET /game/today | 134.3 / 148.2 / 169.5 | 32.1 / 42.8 / 51.4 |
| POST /questions | 204.3 / 246.7 / 296.9 | 44.1 / 60.5 / 72.6 |
| GET /leaderboard | 108.3 / 145.5 / 149.9 | 26.2 / 32.5 / 35.8 |

- Redis: 35,082 commands in run 1 (**31.9 per request**; Lua script internals count individually), 31.3 per request in run 2.
- Judge cache: run 1 made **30 model calls for 800 questions → hit ratio 0.963** (30 distinct questions); run 2 made 0 calls → 1.0.
- Latency difference between runs is mostly queueing at concurrency 50 on one worker; both runs completed without errors.
- Rate limiters with default settings (separate server, db 9): 12 sessions from one IP+User-Agent → 10 × 201, 2 × 429; 10 rapid questions from one player → 6 × 200, 4 × 429, and exactly 6 attempts charged. The Nginx limiter (1 question / 2 s / IP) is covered by `smoke.sh`.

These are laptop numbers for one worker; they are not a prediction for the Oracle VM.

## 7. Remaining risks

1. CI ran on GitHub after PR #9 (main: all jobs green; the PR run had one flaky frontend test, fixed in Phase 10). The arm64 build runs in CI from Phase 10 on.
2. **Real AI quality** measured only on a 30-request sample (`gpt-oss:20b`, before the prompt fixes); cloud models and free quotas can change.
3. **Per-IP limits and NAT**: 1 question per 2 s per IP at Nginx and 30 sessions/h per IP can affect many players behind one address; tune with real traffic.
4. **No type checker on the backend yet** (pyright planned in roadmap 02b).
5. **Leaderboard durability** relies on Redis AOF (`everysec`); writing results to SQLite (roadmap Phase 07) is not implemented, so a lost Redis volume loses the day's leaderboard.
6. **Request IDs**: the API's error `request_id` is not the same as Nginx's `X-Request-ID` (middleware planned in 02b), which makes log correlation harder.
7. **Unhandled-exception logs** include the exception message; a future bug that puts a secret into an exception message could reach the logs.
8. **Integration flakiness**: root cause found and fixed in Phase 10 (see bug table); keep an eye on the first CI runs of the containers job.
9. **E2E uses a fake API**; a full browser run against the real stack with Turnstile test keys was done manually (Phase 06/07) but is not automated.
10. **Load test is single-worker, single-machine, offline**; behaviour under the VM's CPU limits and real network latency is unmeasured.
11. **Turnstile production keys, TLS, Vercel rewrite with `x-origin-secret`** are untested until deployment.
