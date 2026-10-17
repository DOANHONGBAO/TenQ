# TenQ.ai

Daily AI 10-questions deduction game. Zero login, single player: everyone gets the same secret each game day and at most 10 questions answered by an AI judge.

> Status: Phase 07 (React frontend). The game is playable locally end to end: start Redis, the backend, and the frontend, then open http://localhost:5173. See [docs/roadmap.md](docs/roadmap.md).

## Repository layout

```
backend/    FastAPI service (Python 3.12, uv)
frontend/   React + TypeScript + Vite app
docs/       requirements, architecture, API contract, ADRs, roadmap, progress
.claude/    Claude Code settings and project skills
```

## Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Git | any recent | `git --version` |
| uv | 0.12 or newer | `uv --version` |
| Python | 3.12 (installed by uv) | `uv python find 3.12` |
| Node.js | 22.12 or newer (see `frontend/.nvmrc`) | `node --version` |
| npm | 10 or newer | `npm --version` |
| Podman or Docker | any recent | `podman --version` |

On Fedora: `sudo dnf install git uv nodejs podman`.

## Redis

Redis 7.2 (the last BSD-licensed release line) runs in a container:

```bash
# for the app (port 6379)
podman run -d --name tenq-redis -p 127.0.0.1:6379:6379 docker.io/library/redis:7.2-alpine
# for the tests (port 6390, database 15 is flushed by every test)
podman run -d --name tenq-redis-test -p 127.0.0.1:6390:6379 docker.io/library/redis:7.2-alpine redis-server --save "" --appendonly no
```

After a reboot: `podman start tenq-redis tenq-redis-test`. Redis tests are skipped with a clear message when the test instance is not running; set `TENQ_TEST_REDIS_URL` to use another one.

## Backend

```bash
cd backend
uv python install 3.12          # once; uv keeps it separate from the system Python
uv sync                         # creates backend/.venv with the exact versions in uv.lock
cp .env.example .env            # local settings; .env is git-ignored
python3 -c "import secrets; print(secrets.token_hex(32))"
                                # paste into .env as TENQ_WORD_SELECTION_KEY=...
python3 -c "import secrets; print(secrets.token_hex(32))"
                                # run again, paste as TENQ_SESSION_SECRET=... (must differ)
python3 -c "import secrets; print(secrets.token_hex(32))"
                                # and once more for TENQ_PLAYER_HASH_KEY=... (must differ)
uv run python -m app.scripts.seed_words --dev                # fake words, or:
uv run python -m app.scripts.prepare_hints secrets/words.json  # once: add editable hints
uv run python -m app.scripts.seed_words secrets/words.json   # private curated list
uv run uvicorn app.main:create_app --factory --reload
```

Check: `curl http://127.0.0.1:8000/api/v1/health` returns `{"status":"ok"}`, and `curl http://127.0.0.1:8000/api/v1/puzzles/today` returns today's UTC date and reset time (never the word).

Players need a session first: `POST /api/v1/session` with a Turnstile token. The frontend does this automatically with Cloudflare's invisible test key (`1x00000000000000000000BB`) and the backend's test secret from `.env.example`. With `curl`, the test secret accepts any token, but each token string can be used only once:

```bash
curl -c /tmp/tenq.cookies -b /tmp/tenq.cookies -H 'Content-Type: application/json' \
     -d '{"turnstile_token": "XXXX.DUMMY.TOKEN.XXXX"}' http://127.0.0.1:8000/api/v1/session
curl -c /tmp/tenq.cookies -b /tmp/tenq.cookies -H "Idempotency-Key: $(python3 -c 'import uuid; print(uuid.uuid4())')" \
     -H 'Content-Type: application/json' -d '{"question": "Is it alive?"}' \
     http://127.0.0.1:8000/api/v1/game/today/questions
```

The curated word list (`backend/secrets/words.json`), the selection key, and the SQLite file (`backend/data/`) are secret and git-ignored. Keep an encrypted backup of the key and the list: losing the key changes every future, not yet pinned day. Interactive docs: http://127.0.0.1:8000/api/docs (disabled in production).

Quality checks:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## AI judge (Ollama Cloud)

By default (`TENQ_AI_JUDGE=mock`) questions go through the full judge pipeline against a built-in mock: no network, no key, no cost. To use the real API:

1. Create an API key at ollama.com and put it in `backend/.env` as `TENQ_OLLAMA_API_KEY=...` (never commit or paste it anywhere).
2. Ollama does not publish which models the free plan includes. Check what your key can use (1 request, plus 1 per probe):
   ```bash
   uv run python -m app.scripts.check_ollama_models
   uv run python -m app.scripts.check_ollama_models --probe <model-name>
   ```
3. Set `TENQ_OLLAMA_MODEL=<model-name>` and `TENQ_AI_JUDGE=ollama`, then restart the API. For thinking models such as `gpt-oss` also set `TENQ_OLLAMA_THINK=low`: otherwise reasoning can use up `num_predict` and the JSON answer is cut off (`done_reason=length`).
4. Optional, costs quota: measure accuracy and consistency on a small labelled set, and run the 2-request smoke test:
   ```bash
   uv run python -m app.scripts.evaluate_judge --live --max-requests 30 --repeat 2
   TENQ_LIVE_AI=1 uv run pytest -m live_ai
   ```

`TENQ_AI_HOURLY_BUDGET` and `TENQ_AI_DAILY_BUDGET` cap model HTTP attempts (retries included). When a budget is used up or the provider is down, players get a polite "try again" message and are not charged.

## Frontend

```bash
cd frontend
npm ci                          # exact versions from package-lock.json
npm run dev                     # http://localhost:5173
```

The dev server proxies `/api` to the backend on port 8000, so start the backend first. Frontend structure, state flow, and accessibility notes: [docs/frontend.md](docs/frontend.md).

Quality checks:

```bash
npm run lint                    # ESLint, zero warnings allowed
npm test                        # Vitest component and unit tests
npm run build                   # TypeScript type check (tsc -b) + production build
```

## Configuration

| Environment | How it is selected | Notes |
|-------------|--------------------|-------|
| `local` | `TENQ_ENV=local` in `backend/.env` | Readable logs, API docs on |
| `test` | set by the pytest fixtures | Ignores any `.env` file |
| `production` | `TENQ_ENV=production` on the server | JSON logs, API docs off, https-only CORS, no DEBUG |

All backend settings are `TENQ_*` environment variables listed in `backend/.env.example`. Frontend `VITE_*` variables are public (bundled into JavaScript) and must never hold secrets. Real `.env` files are never committed.

## Documentation

Start with [CLAUDE.md](CLAUDE.md), then [docs/requirements.md](docs/requirements.md), [docs/architecture.md](docs/architecture.md), and [docs/progress.md](docs/progress.md).
