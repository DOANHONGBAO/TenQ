# Engineering Conventions

Status: Proposed in [ADR 0002](decisions/0002-engineering-conventions.md). Tool versions are pinned when each package is scaffolded, not here.

## 1. Repository layout (target)

```
backend/            FastAPI service (Python)
frontend/           React + Vite app (TypeScript)
infra/              docker-compose files, nginx config, deploy scripts
.github/workflows/  CI/CD
docs/               spec, architecture, ADRs, workflow, progress
.claude/            Claude Code settings and project skills
```

## 2. Python (backend)

- Python 3.12+. Dependencies managed by **uv** (`pyproject.toml` + committed `uv.lock`). Runtime and dev dependencies are separate groups.
- **ruff** for lint and formatting (line length 100). **pyright** in `strict` mode for `app/`; `basic` allowed for `tests/`.
- Full type hints on public functions. No `Any` in domain code without a comment explaining why.
- Naming: `snake_case` functions/modules, `PascalCase` classes, `UPPER_SNAKE` constants.
- `async` end to end on request paths; no blocking I/O inside `async def`.

### Backend module structure

```
backend/
  app/
    main.py            app factory: create_app(settings) -> FastAPI
    core/              config (Settings), logging setup, security helpers, error types
    api/               routers only: HTTP <-> schema translation, no business logic
      deps.py          dependency providers (settings, clients, current player)
    schemas/           Pydantic request/response models (API contract)
    domain/            pure game rules: no I/O, no framework imports
    services/          use cases orchestrating domain + adapters
    adapters/          redis_store.py, sqlite_store.py, ollama_client.py, turnstile.py
  tests/
    unit/              domain and services with fakes
    integration/       real Redis/SQLite, API via httpx AsyncClient
    conftest.py
```

Dependency direction: `api -> services -> domain`; `services -> adapters` only through typed `Protocol` interfaces defined next to the service. `domain` imports nothing from the other layers.

## 3. TypeScript (frontend)

- Node LTS. **npm** with committed `package-lock.json`.
- `tsconfig` with `"strict": true`, `noUncheckedIndexedAccess`, `noImplicitOverride`.
- **ESLint** (typescript-eslint, react-hooks) + **Prettier**. No `any`; use `unknown` and narrow.
- Components: `PascalCase.tsx`, one component per file. Hooks: `useThing.ts`.

### Frontend structure

```
frontend/
  src/
    app/               App root, routing, providers
    features/<name>/   components/, hooks/, api.ts, types.ts   (e.g. features/game)
    components/ui/     shared presentational components
    lib/               http client, env access, utilities
  e2e/                 Playwright tests
```

- All server calls go through `lib/http.ts` (credentials included for cookies, typed errors).
- API response types are validated at the boundary (e.g. zod) rather than trusted.
- Only `VITE_*` variables reach the browser; they must never be secret.

## 4. Configuration and environment variables

- Backend reads configuration only through a Pydantic `BaseSettings` class in `app/core/config.py`, prefix `TENQ_`. Missing required secrets fail at startup.
- `.env.example` at each package root lists every variable with a dummy value and a comment. Real `.env*` files are git-ignored and denied to Claude.
- Production secrets live in the VM's environment / GitHub Environments, never in images, compose files, or workflow YAML.
- Separate values per environment: `local`, `ci`, `production`.

## 5. Logging

- Structured JSON logs to stdout in production, human-readable locally. One logger per module (`logging.getLogger(__name__)`).
- Every request gets a `request_id` (accepted from `X-Request-ID` if valid, else generated) included in all log lines and echoed in the response header.
- Never log: secret words, cookies, API keys, Turnstile tokens, full AI prompts. Player question text is logged only as length + hash unless the spec allows otherwise.
- Levels: `INFO` for state changes, `WARNING` for handled degradations (provider retry), `ERROR` for failed requests, `DEBUG` off in production.

## 6. Errors and exceptions

- Domain and service code raise typed exceptions from `app/core/errors.py` (e.g. `AttemptLimitReached`, `JudgeUnavailable`), each with a stable `code`.
- FastAPI exception handlers map them to HTTP status codes and a single envelope:
  `{"error": {"code": "ATTEMPT_LIMIT_REACHED", "message": "...", "request_id": "..."}}`
- Unexpected exceptions return a generic 500 with the request id; stack traces only in logs.
- No bare `except:`; no swallowing exceptions without logging and a deliberate fallback.

## 7. Testing

| Layer | Tool | Rule |
|-------|------|------|
| Domain/services | pytest | Pure, fast, no network; fakes via Protocols |
| API/integration | pytest + httpx | Real Redis (Docker/CI service) for atomicity and concurrency tests |
| AI provider | pytest | Fake by default; live tests opt-in with `@pytest.mark.live_ai` |
| Frontend units | Vitest + Testing Library | Behavior, not implementation details |
| End to end | Playwright | Critical flows against a local stack with a fake judge |

- Every bug fix adds a test that fails before the fix.
- CI blocks merge on: ruff, pyright, ESLint, `tsc --noEmit`, pytest, Vitest, Playwright (smoke).
- Coverage is reported; target ≥ 85% for `domain/` and `services/`.

## 8. Git

- `main` is always deployable and protected; work happens on short-lived branches: `feat/`, `fix/`, `chore/`, `docs/`, `refactor/`, `test/`, `ci/`.
- Commit messages follow Conventional Commits: `type(scope): imperative summary` (≤ 72 chars), body explains *why*.
- Commits are authored by the project owner only, without AI attribution trailers.
- One logical change per PR; squash-merge recommended to keep `main` linear.
- Never commit generated files, secrets, local databases, or `node_modules`.

## 9. Documentation

- `product-spec.md` changes only with owner approval.
- Significant decisions get an ADR (`docs/decisions/`).
- `architecture.md` is updated in the same PR that changes the architecture.
- `progress.md` gets an entry at the end of every task.
- Public functions with non-obvious behavior get docstrings; comments explain *why*, not *what*.

## 10. Production security baseline

- HTTPS only; HSTS; strict CORS to the production frontend origin.
- Identity: signed, `HttpOnly`, `Secure`, `SameSite=Lax` cookie; signing key rotated via configuration.
- Turnstile verified server-side before rate-limited actions.
- Rate limits at Nginx and application level.
- Input validation via Pydantic with explicit length limits; output escaping by React (no `dangerouslySetInnerHTML`).
- Secret word never leaves the server before the game ends.
- Containers run as non-root; Redis is never publicly reachable.
- Dependencies: Dependabot or equivalent enabled; actions pinned by SHA.
- Detailed checks: `tenq-game-integrity`, `tenq-ai-judge-testing`, `tenq-deployment-audit` skills.
