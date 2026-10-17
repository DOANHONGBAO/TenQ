# Deployment Audit Checklist

## Docker images
- [ ] Base images pinned to a specific version (ideally digest); slim/distroless where practical
- [ ] Multi-stage build; build tools not in the runtime image
- [ ] Runs as a non-root user (`USER` set)
- [ ] `.dockerignore` excludes `.git`, `.env*`, `node_modules`, tests, local DB files
- [ ] `HEALTHCHECK` or compose healthcheck defined
- [ ] No secrets in `ARG`/`ENV`/layers

## Docker Compose
- [ ] Redis has no `ports:` mapping in production; reachable only on an internal network
- [ ] Redis requires a password (`requirepass`/ACL) and persistence settings are intentional
- [ ] API container exposes its port only to the Nginx network
- [ ] SQLite on a named volume with a documented backup plan
- [ ] `restart: unless-stopped`, resource limits set to fit the VM
- [ ] Separate override files per environment; production file does not mount source code

## Nginx
- [ ] HTTP → HTTPS redirect; TLS via Let's Encrypt with auto-renewal
- [ ] Security headers: HSTS, `X-Content-Type-Options`, `Referrer-Policy`, a CSP appropriate to the API
- [ ] `client_max_body_size` small (API only accepts short questions)
- [ ] `limit_req` rate limiting on question/guess endpoints
- [ ] CORS allows only the production Vercel origin (and explicit preview origins if needed)
- [ ] Proxy timeouts above the AI judge timeout, but bounded
- [ ] `server_tokens off`; access logs exclude cookies and request bodies

## Application config
- [ ] Settings via Pydantic `BaseSettings`; app fails fast on missing required secrets
- [ ] Cookie secret, Ollama API key, Turnstile secret, Redis password all from environment
- [ ] Debug/docs endpoints (`/docs`, `/openapi.json`) disabled or protected in production
- [ ] Turnstile token verified server-side

## GitHub Actions
- [ ] Top-level `permissions:` set to minimum (`contents: read`), elevated per job only
- [ ] Third-party actions pinned to full commit SHA
- [ ] No secrets used in workflows triggered by `pull_request_target` or forks
- [ ] CI runs lint, type check (pyright, tsc), pytest, Playwright before any deploy
- [ ] Production deploy uses a GitHub Environment with required reviewers
- [ ] SSH deploy key scoped to deploy user only; host key pinned (`known_hosts`), not `StrictHostKeyChecking=no`

## Vercel
- [ ] Only `VITE_*` public values configured; no backend secrets
- [ ] Preview deployments point at a non-production API or are restricted

## Oracle Cloud
- [ ] Security list / NSG allows only 22 (restricted source), 80, 443
- [ ] Host firewall (iptables/ufw) consistent with the security list
- [ ] SSH key-only auth, root login disabled, unattended security updates
- [ ] Resources within Always Free limits; budget alert configured
- [ ] Note the idle-instance reclamation policy for Always Free and how the deployment avoids it

## Operations
- [ ] Rollback procedure documented (previous image tag)
- [ ] Logs rotated; disk usage bounded
- [ ] Uptime/health monitoring using a free tool
