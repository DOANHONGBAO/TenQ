# TenQ.ai

Daily AI 10-questions deduction game. Zero login, single player: everyone gets the same secret each game day and at most 10 questions answered by an AI judge.

> Status: Phase 02 (repository and local development setup). Gameplay is not implemented yet. See [docs/roadmap.md](docs/roadmap.md).

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

On Fedora: `sudo dnf install git uv nodejs`. Docker is not needed yet.

## Backend

```bash
cd backend
uv python install 3.12          # once; uv keeps it separate from the system Python
uv sync                         # creates backend/.venv with the exact versions in uv.lock
cp .env.example .env            # local settings; .env is git-ignored
uv run uvicorn app.main:create_app --factory --reload
```

Check: `curl http://127.0.0.1:8000/api/v1/health` returns `{"status":"ok"}`. Interactive docs: http://127.0.0.1:8000/api/docs (disabled in production).

Quality checks:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## Frontend

```bash
cd frontend
npm ci                          # exact versions from package-lock.json
npm run dev                     # http://localhost:5173
```

The dev server proxies `/api` to the backend on port 8000, so start the backend first. The page shows "Backend online" when the health check succeeds.

Quality checks:

```bash
npm run lint                    # ESLint, zero warnings allowed
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
