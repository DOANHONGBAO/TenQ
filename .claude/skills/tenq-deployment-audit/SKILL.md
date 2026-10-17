---
name: tenq-deployment-audit
description: Audits TenQ deployment and delivery configuration. Use when writing, changing, or reviewing Dockerfiles, docker-compose files, Nginx config, GitHub Actions workflows, Vercel config, environment variable handling, Oracle Cloud VM/network setup, or anything that affects production safety, secrets, networking, or free-tier cost limits. Also use before any deploy, release, or infrastructure change is proposed. Not for application game logic or AI judge behavior.
---

# TenQ Deployment Audit

Target topology (verify against `docs/architecture.md`; update this skill if the ADRs change it): React/Vite frontend on Vercel → HTTPS → Nginx reverse proxy on an Oracle Cloud Always Free VM → FastAPI container → Redis (and SQLite volume) on an internal Docker network. CI/CD runs on GitHub Actions.

## Procedure

1. **Inventory.** List every file in scope: `Dockerfile*`, `docker-compose*.yml`, `nginx/**`, `.github/workflows/**`, `vercel.json`, `.env.example`, deploy scripts. Note which environment each targets (local / CI / production).
2. **Audit** each file against [references/audit-checklist.md](references/audit-checklist.md). Record status with `file:line`.
3. **Verify, don't assume.** Where possible run safe local checks: `docker compose config`, `nginx -t` in a container, `hadolint`, `actionlint`, `docker build` without pushing. State plainly which checks were run and which were only read. Never run commands against production hosts or cloud accounts without explicit approval.
4. **Check free-tier fit.** Confirm the design stays within current Oracle Always Free and Vercel Hobby limits. Look up current limits from official pages before stating numbers — they change.
5. **Report** using the format below.

## Output format

```
## Deployment audit — <scope>
| Severity | File:line | Finding | Fix |
|----------|-----------|---------|-----|
### Checks executed
- <command>: <result>
### Not verified
- <item>: <why>
### Production gate
Ready / Not ready — <blocking items>
```

Severity: **Critical** (secret exposure, public Redis, RCE path), **High** (missing TLS, root containers, unpinned third-party actions with write tokens), **Medium**, **Low**.

## Key rules

- Redis and the API container are never published on a public interface; only Nginx exposes 80/443.
- No secrets in images, compose files, workflow YAML, or the frontend bundle. `.env.example` lists names only. Vite exposes every `VITE_*` variable to the browser — none may be secret.
- Separate configuration per environment; production values exist only in the host's secret store / GitHub Environments with required reviewers.
- Deploy jobs run only from `main` (or tags), require manual approval for production, and use least-privilege `permissions:`.
- Anything that could incur cost (paid shapes, extra block volumes, paid Vercel features) must be flagged and requires explicit approval.
