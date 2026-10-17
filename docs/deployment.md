# Production Deployment (free tier)

Status: **prepared, not deployed.** Nothing in this document has been run against real cloud accounts yet. Steps marked **OWNER** need an account, a console click, or a secret, and only the owner performs them.

Target: Oracle Cloud Always Free VM (API + Redis + Nginx) behind Vercel (static SPA + `/api` rewrite). Cost: **0**. Any step that could cost money is called out.

Facts checked on 2026-10-17: Oracle Always Free Ampere A1 = 1,500 OCPU hours and 9,000 GB hours per month ("equivalent to 2 OCPUs and 12 GB of memory"), 200 GB block storage, 10 TB egress, instances only in the home region, idle reclamation when CPU p95, network, and memory are all under 20% for 7 days (docs.oracle.com, Always Free Resources). Let's Encrypt issues IP-address certificates (160-hour "shortlived" profile, HTTP-01 or TLS-ALPN-01 only); Certbot supports them from 5.3 (`--ip-address`) and webroot from 5.4 (letsencrypt.org 2026-01-15, eff.org 2026-03). Vercel external rewrites forward `x-real-ip`/`x-forwarded-for` (overwritten by Vercel) and a `routes` transform can set `x-origin-secret` (vercel.com/docs/routing/rewrites).

---

## Part A — Oracle Cloud VM

### A1. Account and eligibility — OWNER

1. Sign up at cloud.oracle.com. Oracle asks for a card to verify identity; **Always Free resources are not charged**, but do not click "Upgrade to Pay As You Go" (that is the only way paid usage starts) — see ADR 0011.
2. Note your **home region** (Profile > Tenancy). Always Free compute must be created there.
3. Billing > Budgets: create a budget of USD 1 with an email alert (free) as a safety net.

### A2. Shape and architecture

- Shape **VM.Standard.A1.Flex** (Ampere, **arm64**), **1 OCPU / 6 GB** (leaves half of the free allowance spare; 2 OCPU / 12 GB is also free).
- Every image we use is multi-arch (python:3.12-slim, uv, redis:7.2-alpine, nginx-unprivileged, alpine); the API image is **built on the VM**, so it is native arm64. CI also builds the image for `linux/arm64` to catch problems early.
- If A1 capacity is unavailable in your region ("Out of host capacity"), retry later or use **VM.Standard.E2.1.Micro** (amd64, 1 GB RAM — tight; lower the container memory limits).

### A3. Create the VM — OWNER (console)

Compute > Instances > Create:
- Image: **Canonical Ubuntu 24.04** (aarch64 for A1).
- Shape: as above. Boot volume: default (about 50 GB, within the 200 GB free).
- Networking: "Create new virtual cloud network" + public subnet, **assign a public IPv4 address**. Write the IP down (later: `ORIGIN_IP`).
- SSH keys: paste your public key (A4).

### A4. SSH key — OWNER (your laptop)

```bash
ssh-keygen -t ed25519 -f ~/.ssh/tenq_oracle -C "tenq admin"   # creates a key pair; the .pub goes to Oracle
ssh -i ~/.ssh/tenq_oracle ubuntu@ORIGIN_IP                      # first login (user "ubuntu")
```
`ssh-keygen` creates the private key (keep it secret) and public key; Oracle installs the public key for user `ubuntu`, so only your private key can log in. Password login is disabled on Oracle Ubuntu images.

### A5. VCN security list — OWNER (console)

Networking > VCN > Security Lists > Default: ingress rules
| Source | Protocol / port | Why |
|--------|-----------------|-----|
| `YOUR_PUBLIC_IP/32` | TCP 22 | SSH only from you (update when your IP changes) |
| `0.0.0.0/0` | TCP 80 | Let's Encrypt HTTP-01 and redirect to HTTPS |
| `0.0.0.0/0` | TCP 443 | Vercel → API (Vercel egress IPs are not fixed, so 443 must be open; the origin secret is the gate) |

Remove any other ingress rule (6379 and 8000 must never be listed). For SSH from GitHub Actions see `docs/ci-cd.md` (that needs 22 open more widely, mitigated by key-only auth).

### A6. Base system (on the VM)

```bash
sudo apt update && sudo apt full-upgrade -y          # refresh package lists and install security updates
sudo apt install -y unattended-upgrades git curl     # automatic security updates; git for the checkout
sudo dpkg-reconfigure -plow unattended-upgrades      # answer "Yes" to enable them
sudo timedatectl set-timezone UTC                    # logs and timers in UTC, like the game day
```

### A7. Docker Engine and Compose plugin (official Docker apt repository)

```bash
sudo install -m 0755 -d /etc/apt/keyrings                                         # directory for repo keys
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc   # Docker's signing key
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list                                 # add the repo (arm64 on A1)
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker                                                # start now and at boot
docker --version && docker compose version                                        # verify
```

Deploy user (used by GitHub Actions; membership of the `docker` group is effectively root on this VM, so its SSH key must be protected):
```bash
sudo adduser --disabled-password --gecos "" deploy     # no password; key-only login
sudo usermod -aG docker deploy                         # may run docker compose
sudo install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
```

### A8. Host firewall

Oracle's Ubuntu images ship an iptables policy that only accepts SSH. Open 80 and 443 and persist the rules:
```bash
sudo iptables -L INPUT -n --line-numbers                                   # find the final REJECT rule's position
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT  # insert before that REJECT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save                                              # survive reboots (/etc/iptables/rules.v4)
```
Adjust `6` to the line just above the `REJECT` shown by the first command. Docker manages its own NAT/forward rules for **published** ports only (80, 443, and `127.0.0.1:8080`); Redis and the API are not published, so nothing else is reachable.

### A9. Application directory

```bash
sudo install -d -o deploy -g deploy -m 750 /opt/tenq /opt/tenq/state /opt/tenq/acme
sudo install -d -o root -g root -m 700 /opt/tenq/backups /opt/tenq/secrets
sudo -u deploy git clone https://github.com/DOANHONGBAO/TenQ.git /opt/tenq/app
```
- `/opt/tenq/app` git checkout (the deploy script checks out exact SHAs), `/opt/tenq/state` current/previous release, `/opt/tenq/acme` ACME webroot, `/opt/tenq/tls` certificate copy for nginx (created by the certbot hook), `/opt/tenq/backups`, `/opt/tenq/secrets` (word list).
- If the repository is private: create a read-only **deploy key** on GitHub (Settings > Deploy keys) and clone over SSH — OWNER.

### A10. Production environment — OWNER (secrets)

```bash
cd /opt/tenq/app
sudo -u deploy cp infra/env/api.env.example infra/env/api.env
sudo -u deploy cp infra/env/redis.env.example infra/env/redis.env
sudo -u deploy cp infra/env/nginx.env.example infra/env/nginx.env
sudo -u deploy chmod 600 infra/env/*.env
openssl rand -hex 32     # run once per secret below; paste values into the files with an editor (never into chat)
```

| File | Variable | Production value |
|------|----------|------------------|
| api.env | `TENQ_ENV` | `production` |
| api.env | `TENQ_WORD_SELECTION_KEY`, `TENQ_SESSION_SECRET`, `TENQ_PLAYER_HASH_KEY` | three different `openssl rand -hex 32` values (keep an encrypted offline copy; the selection key decides every future word) |
| redis.env / api.env | `REDIS_PASSWORD` / `TENQ_REDIS_URL` | `openssl rand -hex 24`; URL `redis://:<password>@redis:6379/0` |
| nginx.env / api.env | `NGINX_ORIGIN_SECRET` / `TENQ_ORIGIN_SECRETS` | same `openssl rand -hex 32` value; **also** set in Vercel as `ORIGIN_SECRET` (Part C) |
| nginx.env | `NGINX_ENFORCE_ORIGIN` | `on` |
| api.env | `TENQ_CORS_ORIGINS` | `https://<project>.vercel.app` |
| api.env | `TENQ_TURNSTILE_SECRET_KEY`, `TENQ_TURNSTILE_ALLOWED_HOSTNAMES` | real Turnstile secret; `<project>.vercel.app` |
| api.env | `TENQ_AI_JUDGE`, `TENQ_OLLAMA_API_KEY`, `TENQ_OLLAMA_MODEL`, `TENQ_OLLAMA_THINK` | `ollama`, your key, e.g. `gpt-oss:20b`, `low` |

The API refuses to start in production with a test Turnstile secret, the mock judge, HTTP CORS origins, DEBUG logging, or without origin secrets.

Word list (from your laptop): `scp -i ~/.ssh/tenq_oracle backend/secrets/words.json ubuntu@ORIGIN_IP:/tmp/` then on the VM `sudo install -m 600 /tmp/words.json /opt/tenq/secrets/words.json && rm /tmp/words.json`.

### A11–A12. TLS bootstrap, first deploy, health checks

```bash
# Certbot >= 5.4 (IP certificates with webroot). The snap is updated automatically and installs a renewal timer.
sudo snap install --classic certbot && sudo ln -sf /snap/bin/certbot /usr/bin/certbot
certbot --version                                           # must print 5.4 or newer

# 1) Test issuance against Let's Encrypt STAGING (ports 80 must be free: nothing running yet)
sudo certbot certonly --standalone --staging --preferred-profile shortlived --ip-address ORIGIN_IP
# 2) Real certificate, then switch future renewals to the webroot served by nginx
sudo certbot certonly --standalone --preferred-profile shortlived --ip-address ORIGIN_IP
sudo certbot reconfigure --cert-name ORIGIN_IP --webroot --webroot-path /opt/tenq/acme
# 3) Hook that copies the certificate for the unprivileged nginx and reloads it after each renewal
sudo install -m 755 deploy/certbot-deploy-hook.sh /etc/letsencrypt/renewal-hooks/deploy/tenq.sh
sudo RENEWED_LINEAGE=/etc/letsencrypt/live/ORIGIN_IP sh /etc/letsencrypt/renewal-hooks/deploy/tenq.sh
sudo certbot renew --dry-run                                # proves webroot renewal works once nginx runs (after step 5)

# 4) First deploy of the current main commit (builds arm64 image, starts containers, waits for health)
cd /opt/tenq/app && sudo -u deploy git checkout main && sudo -u deploy git pull
sudo -u deploy sh deploy/remote-deploy.sh "$(git rev-parse HEAD)"

# 5) Seed the private word list (stdin; the file is never mounted into a container)
sudo cat /opt/tenq/secrets/words.json | sudo -u deploy env TENQ_RELEASE="$(git rev-parse HEAD)" \
  docker compose -f compose.yaml -f compose.prod.yaml run --rm -T api python -m app.scripts.seed_words -
```
The live directory name may differ from `ORIGIN_IP` — `sudo certbot certificates` shows it. Certificates last 160 hours; the snap timer renews them twice a day when due.

Health checks and restarts are defined in `compose.yaml` (`healthcheck`, `restart: unless-stopped`, `depends_on: service_healthy`); Docker restarts crashed containers and starts them at boot.

### A13. Persistent volumes and backups

```bash
docker volume ls | grep tenq                         # tenq_sqlite-data, tenq_redis-data
sudo install -m 644 deploy/systemd/tenq-backup.* /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now tenq-backup.timer
sudo systemctl start tenq-backup.service && ls -l /opt/tenq/backups/*/   # first backup now
```
Optional (free): Oracle boot-volume backups (5 free) via Block Storage > Boot Volumes > Backups.

### A14. Exposure checks

```bash
sudo ss -tlnp                       # expect only :22, :80, :443 and 127.0.0.1:8080 — no :6379, no :8000
docker compose -f compose.yaml -f compose.prod.yaml ps    # no port mapping for api or redis
```
From your laptop:
```bash
nc -vz -w 3 ORIGIN_IP 6379 ; nc -vz -w 3 ORIGIN_IP 8000      # both must fail (refused or timed out)
curl -s https://ORIGIN_IP/api/v1/health                        # with a valid IP certificate: 403 FORBIDDEN_ORIGIN (direct access blocked)
curl -s http://ORIGIN_IP/                                      # 301 to https
```

---

## Part B — HTTPS and origin routing

| Concern | Design | To verify (Part E) |
|---------|--------|--------------------|
| Hostname without paying for DNS | Let's Encrypt **IP certificate** for the VM's public IP (free, no domain) | `curl -v https://ORIGIN_IP/nginx-health` shows a valid chain for the IP |
| TLS | Nginx TLS 1.2/1.3, HTTP/2, HSTS; validated locally with `nginx -t` and a self-signed test certificate (redirect, ACME, TLS 1.3, HSTS all behaved) | real certificate on the VM |
| Vercel → origin | `routes` entry `^/api/(.*)` → `https://ORIGIN_IP/api/$1` with a `request.headers` transform setting `x-origin-secret` from the `ORIGIN_SECRET` env var | **Not yet confirmed that Vercel accepts an IP destination and validates IP-SAN certificates**; first thing to test |
| Forwarding headers | Vercel overwrites `X-Forwarded-For`/`X-Real-IP`; nginx trusts `X-Real-IP` only with the secret, otherwise uses the peer address; the API trusts nginx's header only with the secret | game uses your real IP in rate limits (`docker compose logs nginx` shows `"origin_ok":1` and your IP) |
| Cookies | `tenq_sid` set by the API with `Path=/api; HttpOnly; Secure; SameSite=Lax`, no `Domain`, passed through by Vercel: first-party on `<project>.vercel.app` | DevTools > Application > Cookies |
| Direct bypass | `NGINX_ENFORCE_ORIGIN=on` + API `TENQ_ORIGIN_SECRETS`: direct calls get 403; only `/nginx-health` stays open | A14 curl |
| Caching | API sends `Cache-Control: no-store`; the route also sets `x-vercel-enable-rewrite-caching: 0` | response headers through Vercel |

**If Vercel cannot proxy to an IP over HTTPS** (the open question above), in order of preference:
1. **Free hostname for the IP** such as `ORIGIN_IP-with-dashes.sslip.io` (public wildcard DNS) with a normal Let's Encrypt certificate (`certbot --domain`). Cost 0; change: `vercel.json` destination and certbot command only. Risk: dependency on a third-party DNS service and Let's Encrypt rate limits shared by all its users.
2. **Minimal Vercel Function gateway**: `/api/*` handled by a tiny Node function that forwards to the origin with an HMAC over method, path, timestamp, and body hash; Nginx/API verify the HMAC and timestamp. Cost: every API call becomes a function invocation on the Hobby plan (free quota, but limited) plus cold starts; more code. Architecture change → needs an ADR and owner approval first.
Self-signed certificates or plain HTTP between Vercel and the origin are **not** acceptable defaults.

---

## Part C — Vercel — OWNER (account), values below

1. vercel.com > Add New > Project > Import `DOANHONGBAO/TenQ` (GitHub app access to that repo only).
2. **Root Directory**: `frontend`. Framework preset: **Vite**.
3. Build command `npm run build`, output `dist`, install `npm ci` (defaults for Vite).
4. Environment variables (Production):
   | Name | Value | Exposed to browser? |
   |------|-------|---------------------|
   | `VITE_TURNSTILE_SITE_KEY` | Turnstile **site key** (public) | yes (by design) |
   | `VITE_API_BASE_URL` | `/api/v1` | yes |
   | `ORIGIN_SECRET` | same value as `NGINX_ORIGIN_SECRET` | **no** — not `VITE_*`, used only by the routes transform |
5. Turnstile (dash.cloudflare.com > Turnstile > Add widget): hostname `<project>.vercel.app`, **Widget mode: Invisible**. Site key → Vercel; secret → VM `api.env`.
6. API routing: edit `frontend/vercel.json` and replace `ORIGIN_HOST` with the VM's public IP (or the fallback hostname); commit through a PR.
7. Deploy: Vercel builds every push to `main` (production) and pull requests (previews). The site is `https://<project>.vercel.app` (free). Vercel Hobby is for non-commercial use.
8. Tests: see Part E.
9. Bundle: CI job `security` fails if `TENQ_`, `OLLAMA_API_KEY`, `ORIGIN_SECRET`, or the Turnstile test secret appear in `dist/assets` (checked locally: clean).

Preview deployments have different hostnames, so Turnstile (hostname allow-list) and therefore sessions fail there by design; previews are for UI review only.

## Part D — CI/CD

See `docs/ci-cd.md`.

## Part E — Production validation

See `docs/operations-runbook.md`, section "Production validation checklist". Production is **not** considered working until every item there has been checked against the live endpoints.
