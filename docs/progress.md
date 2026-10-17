# Progress

## Status

Phase: **06 — Anonymous identity and anti-abuse (in review)** on `feature/anonymous-identity-security`, stacked on PR #4 (Phases 04 and 05).
Next: owner reviews and merges PR #4, then reviews Phase 06; production values (Turnstile site and secret keys, origin secret, Vercel routes transform) are set in Phase 10.

## Log

### 2026-10-17 — Phase 06: anonymous identity and anti-abuse (`feature/anonymous-identity-security`)

Done:
- `core/session.py`: cookie `<player_id>.<issued_at>.<HMAC>` with server-side 365-day expiry, future-timestamp rejection, current+previous secret rotation with re-signing; `Identifiers` (player hash, daily IP hash, UA hash) keyed by the new `TENQ_PLAYER_HASH_KEY`.
- `core/client_ip.py` + `OriginGuardMiddleware`: forwarded IP trusted only with a valid `x-origin-secret` (`TENQ_ORIGIN_SECRETS`, required in production); otherwise TCP peer; direct origin access refused with `403 FORBIDDEN_ORIGIN` (health exempt).
- `integrations/turnstile.py` + `services/session_service.py` + `POST /api/v1/session`: Siteverify with success, hostname allow-list, action `session`, `challenge_ts` ≤ 300 s, test keys refused in production, fail closed on outage; Redis replay cache (off only for Cloudflare test keys, which reuse one dummy token).
- `repositories/abuse_store.py` + dependencies: fixed-window limits (sessions per IP hash and per device hash, questions per player and per IP hash, reads per IP hash), per-IP in-flight question slots, all before `reserve` so blocked requests are never charged.
- `BodySizeLimitMiddleware` (4 KB, Content-Length and streaming), generic `500` handler, `405` mapping; `GET /game/today` now requires a session.
- Frontend: invisible Turnstile loader (`lib/turnstile.ts`, token reset after use), `useAnonymousSession` (single setup per page load), privacy notice footer and `public/privacy.html`.
- ADR 0014; threat model (T-07, T-08, T-09, T-12 updated; T-21 to T-24 added; section 6 on the 10-questions-per-device limit), architecture section 9, API contract, data model, README, `.env.example`.

Verified on 2026-10-17: backend `ruff check`, `ruff format --check`, `pytest` 291 passed (39 new security tests); frontend `npm run lint`, `npm run build`; live run in the browser pane: the invisible test widget produced a token, the backend validated it against the real Siteverify endpoint with the test secret, and the page showed "Anonymous session ready"; a reload reused the cookie.

Facts checked (vercel.com/docs/headers/request-headers, vercel.com/docs/routing/rewrites, developers.cloudflare.com/turnstile server-side validation and testing pages, plus one Siteverify call with the test secret): see ADR 0014.

### 2026-10-17 — Phase 05: Ollama AI judge and semantic caching (to be committed on `feature/ai-judge`)

Done:
- `integrations/ollama_client.py`: pooled httpx2 client, Bearer auth, per-attempt timeouts inside an overall deadline, bounded retries with jittered backoff and Retry-After, typed errors (401/403, 402, 429, 5xx, timeout, connection, malformed envelope), token and latency logging without prompts.
- `integrations/ai_judge.py`: `JudgeContext`, `JudgeOutput` (`{"result": LABEL}`, `extra="forbid"`), strict `parse_judge_output`; `integrations/judge_prompt.py` (prompt version `2026-10-17.1`, question sent as JSON data); `integrations/ollama_mock.py` (`MockOllamaProvider` transport).
- `models/judge_rules.py`: deterministic PENALTY (open-ended, several questions, manipulation) and exact-guess WIN.
- `services/judge_service.py` (`HybridJudge`): rules, shared daily cache, single-flight + Redis lock, circuit breaker, hourly/daily budget (Lua), concurrency limit, one strict re-ask, WIN verification. `repositories/judge_cache.py`, `core/circuit_breaker.py`.
- GameService maps invalid output to `502 AI_INVALID_RESPONSE` and provider problems to `503 AI_UNAVAILABLE`, both uncharged; the judge never touches attempts or the leaderboard.
- Redis TTLs are now computed from the application clock (`EXPIRE ttl`) instead of absolute `EXPIREAT`, so fixed-clock tests stay valid on any real date.
- Settings: `TENQ_AI_JUDGE` (`mock` default, production requires `ollama`), `TENQ_OLLAMA_API_KEY` (or `OLLAMA_API_KEY`), `TENQ_OLLAMA_MODEL` (no default), `TENQ_OLLAMA_THINK`, budgets, concurrency; empty `.env` values mean unset.
- Scripts: `check_ollama_models` (list + optional single probe), `evaluate_judge` (accuracy and consistency, mock by default, live capped at 120 requests). Opt-in `live_ai` pytest marker.
- ADR 0013; architecture 4.3, data model keys, roadmap, README, `.env.example`, judge skill checklist updated.

Verified on 2026-10-17: `ruff check`, `ruff format --check`, `pytest` 251 passed (Redis 7.2.16); `evaluate_judge` in mock mode runs end to end (mock accuracy is not meaningful).

Live evaluation by the owner (`gpt-oss:20b`, prompt `2026-10-17.1`, 30 requests, repeat 2): model-only accuracy 0.857, consistency 0.867, 4 of 30 outputs invalid, ~110 output tokens and 1.8 s per call. Diagnosis with 2 extra requests: without `think`, gpt-oss spends `num_predict=256` on reasoning and the JSON is truncated (`done_reason=length`); with `think=low` the answer is complete (22 tokens). The same probe showed the model answering WIN to "Is the secret word apple?" for another word (rejected by the server-side check). Follow-ups made: `wrong_explicit_guess` rule (deterministic NO, no AI call), prompt `2026-10-17.2` ("guessing any other word is NO"), default `num_predict` 512, truncation logged, evaluation interleaves words and records failure reasons, walrus "Can you eat it?" relabelled ambiguous. Recommended setting: `TENQ_OLLAMA_THINK=low`. A new live evaluation is needed to measure the effect.

Facts checked (docs.ollama.com/cloud, docs.ollama.com/api/chat, docs.ollama.com/api/errors, ollama.com/pricing, 2026-10-17): endpoint and auth as above; `GET /api/tags` lists models; Free plan has starter usage on unpublished starter models, monthly reset, 1 concurrent request; errors are `{"error": ...}` with 429 and 500/502 documented.

### 2026-10-17 — Phase 04: game engine and Redis atomic state (`feature/game-engine`)

Done:
- `models/game.py` (status machine, answers, score, anonymous display name), `models/question.py` (OQ-04 checks, normalization, server-side WIN token check).
- `repositories/game_store.py`: Lua `reserve` / `commit` / `release`; keys per UTC date and player hash; `EXPIREAT` at 00:00 UTC of date + 2; history; duplicate set; idempotency hash; leaderboard ZSET with member `{finished_at_ms:013d}:{player_hash}` for deterministic ties.
- `services/game_service.py`: reserve, judge with timeout, verify WIN, commit or release; Redis errors become 503 without charging.
- `integrations/ai_judge.py`: `AIJudge` protocol and `FakeAIJudge` (scripted answers, failures, delay, gate).
- `core/session.py`: minimal signed `tenq_sid` cookie and keyed player hash; new settings `TENQ_SESSION_SECRET`, `TENQ_REDIS_URL`, `TENQ_QUESTION_LEASE_MS`, `TENQ_JUDGE_TIMEOUT_S`, `TENQ_AI_JUDGE` (production refuses the fake judge).
- API: `GET /game/today`, `POST /game/today/questions` (UUID v4 `Idempotency-Key`, body accepts only `question`), `GET /leaderboard/today`; error codes from the contract.
- Docs: API contract (status `in_progress`, session issuance until Phase 06, replay semantics, tie-breaking), data model (keys and scripts as built), architecture row, roadmap, README (Redis via Podman), `.env.example`.

Verified on 2026-10-17 with Redis 7.2.16 (Podman, port 6390): `ruff check`, `ruff format --check`, `pytest` 144 passed, three full runs and fifteen runs of the concurrency, midnight, and restart tests without a failure; a live uvicorn served session creation, two charged questions, a duplicate refusal, and the leaderboard.

Notes:
- The owner must add `TENQ_SESSION_SECRET` to `backend/.env` and run a local Redis on port 6379.
- Pyright is still not installed (Phase 02b).

### 2026-10-17 — Phase 03: daily secret word engine (`feature/daily-secret-word`)

Done:
- `models/clock.py` (`Clock`, `SystemUTCClock`, `FixedClock`, `game_date_at`, `next_reset_at`; naive datetimes rejected), `models/daily_game.py` (`DailyGameConfig`, `DailyPuzzle` with redacted repr), `models/word.py` (entries and list validation), `models/word_schedule.py` (keyed yearly permutation, leap-day and year-boundary rules).
- `repositories/database.py` (pragmas, numbered SQL migrations), migration `0001` (`words`, `daily_puzzles`), `repositories/word_repository.py` (`WordRepository` protocol, SQLite implementation, `INSERT OR IGNORE` pinning).
- `services/daily_word_service.py` (`DailyWordService`: pinned word wins, in-memory cache, past-only reveal).
- `GET /api/v1/puzzles/today` (no word) and `GET /api/v1/puzzles/{date}/answer` (past dates only); minimal error envelope in `core/errors.py`.
- `TENQ_WORD_SELECTION_KEY` (required, 32-byte hex, `SecretStr`) and `TENQ_DATABASE_PATH` settings; `app.scripts.seed_words` (`--dev` fake words or a private JSON file; output never lists words).
- Private curated list of 365 nouns with metadata written to `backend/secrets/words.json` (git-ignored, mode 600); not in the repository.
- ADR 0012 supersedes ADR 0008's selection formula; architecture, data model, API contract (new 4.6a), threat model, roadmap (Phase 03 re-scoped, 03b added), README, CLAUDE.md updated. Local log timestamps are now UTC.

Verified on 2026-10-17: `ruff check`, `ruff format --check`, `pytest` (78 passed); the curated file passed seeding validation; a live uvicorn with that list served `/puzzles/today` (200), `/puzzles/2026-10-17/answer` (403), `/puzzles/2026-01-01/answer` (404), and neither responses nor logs contained the pinned word.

Notes:
- Pyright is still not installed (Phase 02b), so strict type checking has not been run.
- The owner must generate their own `TENQ_WORD_SELECTION_KEY` in `backend/.env`; Claude cannot read or write `.env` files.

### 2026-10-17 — Phase 02: repository and local development setup (`feature/project-bootstrap`)

Done:
- `backend/`: uv project pinned to Python 3.12 (`.python-version`, `uv.lock`); FastAPI app factory `create_app`; `core/config.py` settings with required `TENQ_ENV` (`local` / `test` / `production`) and production guards (https-only CORS, no DEBUG, API docs off); `core/logging.py` (JSON in production); `GET /api/v1/health`; empty `models/`, `services/`, `repositories/`, `integrations/` packages; Ruff and pytest configured; `.env.example`.
- `frontend/`: Vite + React 19 + TypeScript strict (`noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`); ESLint with typescript-eslint strict type-checked and react-hooks (replaced the template's oxlint); starter page showing backend status through the Vite `/api` proxy; `lib/http.ts`, `lib/env.ts`; `.env.example`.
- Root `README.md` with setup steps; `CLAUDE.md` commands; `engineering-conventions.md` backend layout renamed to `models` / `repositories` / `integrations`; roadmap Phase 02 re-scoped, remainder moved to Phase 02b.

Verified on 2026-10-17 (Fedora 44 host, uv 0.12.24, Python 3.12.15, Node 22.23.1, npm 10.9.8): `ruff check`, `ruff format --check`, `pytest` (7 passed), `npm run lint`, `npm run build`; uvicorn served `/api/v1/health` with 200; Vite served the page and proxied `/api/v1/health` with 200; the page showed "Backend online".

Notes:
- The owner's shell is an Ubuntu 24.04 distrobox without git, uv, or Node; tools run on the Fedora host (`distrobox-host-exec`).
- Branch prefix `feature/` was requested by the owner; conventions list `feat/`.
- Docker is not installed on the host (Podman 5.8 is); not needed until Redis arrives.

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
