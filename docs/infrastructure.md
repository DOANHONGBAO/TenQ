# Infrastructure (Docker Compose)

Files: `compose.yaml`, `backend/Dockerfile`, `backend/.dockerignore`, `infra/nginx/`, `infra/redis/redis.conf`, `infra/env/*.env.example`, `infra/scripts/`.

## Containers and networks

```
internet / Vercel
      │ :8080 (local, 127.0.0.1)  ·  :80/:443 in production (Phase 10, TLS)
┌─────▼───────────────────────── network "edge" ─┐
│ nginx (nginx-unprivileged 1.28, uid 101)       │  only published port
└─────┬───────────────────────── network "app" ──┘
      │ http://api:8000  (re-resolved every 10 s)
┌─────▼──────────────────────────────────────────┐
│ api (FastAPI, uid 10001, read-only rootfs)     │──► internet: Ollama Cloud, Cloudflare Siteverify
└─────┬───────────────────────── network "data" ─┘  ("app" network has egress)
      │ redis://:password@redis:6379  (internal: true, no route to the internet)
┌─────▼────────────────┐   volumes: redis-data (AOF + RDB), sqlite-data (/data/tenq.sqlite3)
│ redis 7.2 (AOF)      │
└──────────────────────┘
```

| Service | Image | Published | Limits | Health check | Restart |
|---------|-------|-----------|--------|--------------|---------|
| nginx | `nginxinc/nginx-unprivileged:1.28-alpine` | `127.0.0.1:8080` (configurable) | 0.25 CPU, 64 MB | `GET /nginx-health` | unless-stopped |
| api | built from `backend/Dockerfile` (186 MB, amd64 tested) | none (`expose: 8000`) | 1 CPU, 512 MB | `GET /api/v1/health` | unless-stopped |
| redis | `redis:7.2-alpine` (last BSD-licensed line) | none | 0.5 CPU, 384 MB (`maxmemory 256mb`, `noeviction`) | `redis-cli ping` with password | unless-stopped |

Totals (about 1.75 CPU, under 1 GB) fit an Oracle Always Free Ampere A1 VM with room to spare. All base images are multi-arch (amd64 and arm64); build on the VM itself or with `docker buildx build --platform linux/arm64`.

## Request path

1. **Browser → Vercel**: `https://<site>/api/v1/...` is rewritten to the Oracle origin. Vercel overwrites `X-Forwarded-For`/`X-Real-IP` with the visitor IP and adds `X-Origin-Secret` (ADR 0014).
2. **nginx**: if `X-Origin-Secret` matches `NGINX_ORIGIN_SECRET`, the client IP is `X-Real-IP`; otherwise it is the TCP peer address, and with `NGINX_ENFORCE_ORIGIN=on` the request is refused with `403 FORBIDDEN_ORIGIN`. Then: body ≤ 4 KB, client/upstream timeouts, rate limits on that client IP (questions and guesses 1 per 2 s, everything 10 r/s burst 20, 20 connections), security headers, no caching.
3. **nginx → api**: nginx overwrites `X-Real-IP`/`X-Forwarded-For` with the client IP it computed and stamps its own `X-Origin-Secret`, so the API (which nothing else can reach) trusts `X-Real-IP` only from nginx. `proxy_read_timeout 30s` exceeds the AI judge deadline.
4. **api → redis / SQLite / Ollama / Cloudflare**: game state and limits in Redis over the internal `data` network; durable data in SQLite on `sqlite-data`; outbound HTTPS through the `app` network.

### Telling the two kinds of 429 apart

| Source | Status | Headers | Body |
|--------|--------|---------|------|
| nginx | 429 | `X-RateLimit-Source: nginx`, `Retry-After: 2` | `{"error": {"code": "RATE_LIMITED", ..., "source": "edge"}}` |
| api | 429 | `Retry-After: <window seconds>` | `{"error": {"code": "RATE_LIMITED", "message": ..., "request_id": ...}}` (no `source`) |

Upstream errors pass through unchanged (`proxy_intercept_errors off`); only nginx's own 413/429/502/503/504 use the edge bodies.

## Why Redis must never be public

- **It holds everything that decides the game**: attempt counters, leases, history, leaderboard, judgement cache, and rate-limit counters. Anyone who can write to Redis can give themselves unlimited questions, top the leaderboard, or reset limits.
- **It is designed for trusted networks**: Redis speaks a plain-text protocol without TLS here, and a password is the only barrier; internet-wide scanners probe port 6379 constantly and brute-force or exploit exposed instances (cryptominer and data-wipe campaigns are routine).
- **Some commands are dangerous**: `CONFIG`, `DEBUG`, `FLUSHALL` can change persistence paths, crash, or wipe data. They are renamed away in `redis.conf`, but defence in depth means not exposing the port at all.
- **Here**: no `ports:` mapping, only on the `data` network with `internal: true` (no route in or out), password required, `protected-mode yes`. Verified: `podman port tenq_redis_1` is empty and the container cannot reach the internet.

## Persistence

- Redis: `appendonly yes`, `appendfsync everysec` (at most about 1 s of writes lost on a crash), RDB preamble and snapshots, files on `redis-data`. SIGTERM makes Redis flush before exit (`stop_grace_period: 20s`).
- SQLite: `/data/tenq.sqlite3` on `sqlite-data`, owned by uid 10001; migrations run at API start-up.
- `docker compose down` keeps volumes; `docker compose down -v` deletes them (all game data).

## Commands

```bash
infra/scripts/gen-env.sh                     # local only: random secrets into infra/env/*.env
docker compose build
docker compose up -d
docker compose run --rm -T api python -m app.scripts.seed_words - < backend/secrets/words.json
docker compose ps
docker compose logs -f api nginx
infra/scripts/smoke.sh                       # routing, headers, session, rate limit, spoofing, body limit
docker compose restart                       # state must survive
docker compose down && docker compose up -d  # containers recreated, volumes kept
cd frontend && TENQ_DEV_API_TARGET=http://127.0.0.1:8080 npm run dev   # SPA against the stack
```

With Podman (as used for verification on Fedora): `podman-compose` with the same arguments. Bind mounts use `,z` for SELinux hosts.
