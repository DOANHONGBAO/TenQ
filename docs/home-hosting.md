# Temporary hosting on the owner's computer

Until the Oracle VM exists (see `deployment.md`), the backend can run on the owner's Fedora machine and be reached through **Tailscale Funnel**, while the frontend runs on **Vercel**. Both public URLs are stable. All services used are free; nothing here needs a payment method.

```
Players ─► https://<project>.vercel.app            (Vercel: SPA + /api route, adds x-origin-secret)
              │ HTTPS
              ▼
           https://<machine>.<tailnet>.ts.net      (Tailscale Funnel: valid TLS, terminated by tailscaled)
              │ HTTP on the loopback interface
              ▼
           nginx 127.0.0.1:8080 ─► api ─► redis     (compose.yaml, unchanged)
```

Why this keeps the production security model: Vercel overwrites the client IP headers and adds the origin secret; nginx (with `NGINX_ENFORCE_ORIGIN=on`) refuses anything without the secret, including people who call the `ts.net` URL directly; nginx is published only on `127.0.0.1`, so the only way in from the internet is Funnel. The machine opens no inbound port on the router, and its home IP is not exposed.

Limits to accept: the site is down whenever the computer sleeps or is off (the frontend still loads from Vercel and shows the maintenance screen); Funnel is in beta with non-configurable bandwidth limits (Tailscale KB "Funnel", checked 2026-10-18); home upload speed limits throughput; data lives on this computer, so back it up.

## 1. Tailscale (OWNER)

```bash
sudo systemctl enable --now tailscaled          # start the Tailscale daemon now and at boot
sudo tailscale up                               # prints a login URL: log in with your account
sudo tailscale set --operator=$USER             # lets your user manage serve/funnel without sudo
tailscale status                                # this machine should be listed
```
In the Tailscale admin console: **DNS → enable MagicDNS and HTTPS certificates**, then **Access controls → allow Funnel** for this machine (the console offers a button that adds the `funnel` node attribute). The public name is `https://<machine>.<tailnet>.ts.net` (shown by `tailscale funnel status` later). Optionally rename the machine in the console first, because the name is part of the URL.

## 2. Production environment on this computer (OWNER, secrets)

Use the same files as Docker Compose, with production values (table in `deployment.md`, A10):
- `infra/env/api.env`: `TENQ_ENV=production`, three different hex keys, `TENQ_REDIS_URL` with the Redis password, `TENQ_ORIGIN_SECRETS=<origin secret>`, `TENQ_CORS_ORIGINS=https://<project>.vercel.app`, real Turnstile secret, `TENQ_TURNSTILE_ALLOWED_HOSTNAMES=<project>.vercel.app`, `TENQ_AI_JUDGE=ollama` with key, model, and `TENQ_OLLAMA_THINK=low`.
- `infra/env/nginx.env`: `NGINX_ORIGIN_SECRET=<same origin secret>`, `NGINX_ENFORCE_ORIGIN=on`.
- `infra/env/redis.env`: `REDIS_PASSWORD`.

The API refuses to start in production with a test Turnstile secret, the mock judge, an `http://` CORS origin, or without origin secrets.

## 3. Start, seed, stop

```bash
infra/scripts/home-host.sh up        # checks the env files, starts the stack, waits for health, turns Funnel on
podman-compose run --rm -T api python -m app.scripts.seed_words - < backend/secrets/words.json   # once
infra/scripts/home-host.sh status
infra/scripts/home-host.sh down      # Funnel off, containers stopped, volumes kept
```
After a reboot run `home-host.sh up` again (rootless Podman does not start containers at boot by itself).

To apply new code or changed `infra/env/*.env` values: `git pull`, then `home-host.sh up` (it rebuilds and recreates the containers; volumes are kept). After editing hints in `backend/secrets/words.json`, run the seed command again.

## 4. Vercel and Turnstile (OWNER)

- Cloudflare → Turnstile → Add widget: hostname `<project>.vercel.app`, mode **Invisible**. Site key → Vercel; secret → `api.env`.
- `frontend/vercel.json`: replace `ORIGIN_HOST` with `<machine>.<tailnet>.ts.net` (through a pull request).
- Vercel → Add New → Project → import the repository: Root Directory `frontend`, preset Vite. Environment variables (Production): `VITE_TURNSTILE_SITE_KEY`, `VITE_API_BASE_URL=/api/v1`, `ORIGIN_SECRET` (same origin secret; not `VITE_`, so never in the bundle). Deploy.

## 5. Checks

| Check | Command or action | Expected |
|-------|-------------------|----------|
| Funnel TLS | `curl -s https://<machine>.<tailnet>.ts.net/nginx-health` | `{"status":"ok"}` with a valid certificate |
| Direct bypass blocked | `curl -s https://<machine>.<tailnet>.ts.net/api/v1/health` | 403 `FORBIDDEN_ORIGIN` |
| Through Vercel | `curl -s https://<project>.vercel.app/api/v1/health` | 200 |
| Game | open `https://<project>.vercel.app` in a private window | session starts, a question gets an answer |
| Real client IP | `podman-compose logs --tail 5 nginx` | `"origin_ok":1` and your public IP, not 127.0.0.1 |
| Cookie | DevTools → Application → Cookies | `tenq_sid`, HttpOnly, Secure, SameSite=Lax |
| No local ports exposed | `ss -tlnp` | 8080 only on 127.0.0.1; no 6379 or 8000 |

## Backups

`podman volume export tenq_sqlite-data > ~/tenq-backup-sqlite.tar` and the same for `tenq_redis-data`, while the stack is stopped or quiet. Keep copies off the machine; they contain the word list.

## Moving to Oracle later

Nothing here changes the Oracle plan: set the VM IP (or hostname) in `vercel.json`, follow `deployment.md`, then stop home hosting with `home-host.sh down`. To move today's data, export the two volumes above and import them on the VM.
