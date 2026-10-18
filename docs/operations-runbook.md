# Operations Runbook

All commands run on the VM in `/opt/tenq/app` unless noted. Shorthand used below:
```bash
export TENQ_RELEASE=$(cat /opt/tenq/state/current_sha)
alias dc='docker compose -f compose.yaml -f compose.prod.yaml'
```

## Daily health

```bash
dc ps                                   # all three "healthy"
dc logs --since 1h nginx | grep -c '"status":5'      # 5xx count in the last hour
dc logs --since 1h api | grep -iE "error|unavailable|budget" | tail
df -h / && docker system df             # disk (boot volume ~50 GB)
sudo certbot certificates               # expiry of the 160-hour certificate (renews automatically)
systemctl list-timers | grep -E "tenq|certbot"
```
Free external uptime check (optional): any free uptime monitor pinging `https://<project>.vercel.app/api/v1/health` every 5 minutes. It also keeps the VM from looking idle to Oracle's reclamation rule.

## Common incidents

| Symptom | Check | Action |
|---------|-------|--------|
| Players see "judge is busy" | `dc logs api \| grep -E "ollama|budget|circuit"` | Provider down or quota/budget used: wait; raise `TENQ_AI_DAILY_BUDGET` only if quota allows; check model access with `app.scripts.check_ollama_models` |
| "We'll be right back" | `dc ps`, `dc logs api` | Restart the unhealthy service: `dc up -d`; if a deploy caused it, `docs/rollback.md` |
| All requests 403 | `dc logs nginx \| tail` shows `origin_ok:0` | `ORIGIN_SECRET` in Vercel differs from `NGINX_ORIGIN_SECRET`/`TENQ_ORIGIN_SECRETS` |
| TLS errors via Vercel | `sudo certbot certificates`, `ls -l /opt/tenq/tls` | `sudo certbot renew` (hook reloads nginx); check port 80 is open for HTTP-01 |
| Redis memory errors (503) | `dc exec redis sh -c 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli info memory'` | `maxmemory` 256 MB with `noeviction`; raise in `infra/redis/redis.conf` and container limit together |
| Disk filling | `docker system df` | `docker image prune` (images only; never `volume prune`) |
| Oracle reclamation e-mail | Oracle console | Keep the uptime monitor; consider Pay As You Go only with owner approval (ADR 0011) |

## Secret rotation

- **Origin secret** (dual window): add the new value to `TENQ_ORIGIN_SECRETS` as `new,old`; nginx accepts one value, so: set Vercel `ORIGIN_SECRET=new` and redeploy Vercel, set `NGINX_ORIGIN_SECRET=new`, `dc up -d nginx api`, then remove `old` from `TENQ_ORIGIN_SECRETS`. Expect a few seconds of 403s between the Vercel redeploy and the nginx restart; do it at a quiet hour.
- **Session secret**: move the current value to `TENQ_SESSION_SECRET_PREVIOUS`, set a new `TENQ_SESSION_SECRET`, `dc up -d api`. Players keep their sessions (re-signed on use).
- **Redis password**: change `redis.env` and the password inside `TENQ_REDIS_URL`, then `dc up -d redis api`.
- **Ollama key / Turnstile secret**: replace in `api.env`, `dc up -d api`.
- **Word selection key / player hash key**: do **not** rotate casually (future words / all player identities change). Only after a leak; see ADR 0012.

## Backups and restore

Nightly at 03:30 UTC (`tenq-backup.timer`): `/opt/tenq/backups/<UTC time>/tenq.sqlite3` (online SQLite backup) and `redis-data.tgz` (RDB + AOF). Kept 14 days, root-only. Copy them off the VM regularly (they contain the word list and results).

Restore SQLite:
```bash
dc stop api
docker run --rm -v tenq_sqlite-data:/data -v /opt/tenq/backups/<time>:/b:ro alpine:3.20 \
  sh -c 'cp /b/tenq.sqlite3 /data/tenq.sqlite3 && rm -f /data/tenq.sqlite3-wal /data/tenq.sqlite3-shm && chown 10001:10001 /data/tenq.sqlite3'
dc start api
```
Restore Redis:
```bash
dc stop api redis
docker run --rm -v tenq_redis-data:/data -v /opt/tenq/backups/<time>:/b:ro alpine:3.20 \
  sh -c 'rm -rf /data/* && tar xzf /b/redis-data.tgz -C /data'
dc start redis api
```

## UTC reset

Nothing runs at midnight: the day is part of every Redis key and of the SQLite pin, so the new day starts by itself at 00:00 UTC and old keys expire two days later. To check after midnight: `curl https://<project>.vercel.app/api/v1/puzzles/today` shows the new `game_date`; yesterday's answer becomes available at `/api/v1/puzzles/<yesterday>/answer`.

## Production validation checklist (Part E)

Mark each item only after running it against the live endpoints. Until then production is **not verified**.

| # | Check | How | Expected |
|---|-------|-----|----------|
| 1 | HTTPS origin | `curl -v https://ORIGIN_IP/nginx-health` | valid Let's Encrypt chain for the IP, TLS 1.2/1.3 |
| 2 | Direct bypass blocked | `curl -s https://ORIGIN_IP/api/v1/health` | 403 `FORBIDDEN_ORIGIN` |
| 3 | API through Vercel | `curl -s https://<project>.vercel.app/api/v1/health` | 200 `{"status":"ok"}` |
| 4 | Cookie | open the site, DevTools > Application > Cookies | `tenq_sid`, HttpOnly, Secure, SameSite=Lax, Path=/api, host `<project>.vercel.app` |
| 5 | Turnstile | first visit in a private window | session created; `dc logs api` shows Siteverify 200; no test-key warnings |
| 6 | Real client IP | play one question; `dc logs nginx \| tail -3` | `"origin_ok":1` and your public IP |
| 7 | Rate limiting | two questions within 2 s | second returns 429 with `X-RateLimit-Source: nginx` |
| 8 | Ollama errors | temporarily set a wrong `TENQ_OLLAMA_MODEL`, ask once, restore | polite 503, attempt not charged |
| 9 | Persistence | play, then `dc restart`, reload page | same attempts and history |
| 10 | Deploy pipeline | merge a trivial PR | CI green, CD green, `current_sha` = merge commit |
| 11 | Rollback | Actions > cd > Run workflow with the previous SHA | healthy, state unchanged |
| 12 | No lost state after deploy | compare `/api/v1/game/today` before/after item 10 | identical |
| 13 | UTC reset | after 00:00 UTC | new `game_date`, fresh 10 attempts |
| 14 | Free tier only | Oracle Billing > Cost analysis; Vercel Usage; Cloudflare plan | 0.00 cost, Always Free labels, Hobby plan |
| 15 | No secrets in the bundle | `curl -s https://<project>.vercel.app/assets/*.js \| grep -E "TENQ_\|OLLAMA_API_KEY\|ORIGIN_SECRET"` | no output |
