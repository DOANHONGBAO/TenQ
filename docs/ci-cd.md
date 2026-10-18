# CI/CD

Two separate workflows:

| Workflow | File | Trigger | Has secrets? | Deploys? |
|----------|------|---------|--------------|----------|
| CI | `.github/workflows/ci.yml` | every pull request and every push to `main` | no | no |
| CD | `.github/workflows/cd.yml` | after CI **succeeds** for a **push to main** and only when the repository variable `DEPLOY_ENABLED=true`; or manually with a SHA | yes (Environment `production`) | backend only |

The frontend is deployed by Vercel's own GitHub integration on every push to `main` (production) and on pull requests (previews).

## CI jobs (all with `permissions: contents: read`, actions pinned by commit SHA)

| Job | What it runs |
|-----|--------------|
| backend | Redis service; `uv sync --frozen`; `ruff check`, `ruff format --check`; `pytest` with coverage (XML/HTML artifact); business-logic coverage gate ≥ 80% |
| frontend | `npm ci`; ESLint; Vitest; `npm run build` (includes `tsc -b`, the TypeScript check); Playwright E2E (desktop + mobile); report artifact on failure |
| containers | `infra/scripts/integration.sh` with `docker compose` (build, health, exposure, smoke, restart, down/up persistence, graceful shutdown); `compose.yaml + compose.prod.yaml config`; API image built for **linux/arm64** with QEMU/buildx |
| security | `pip-audit --strict` on the locked runtime dependencies; `npm audit --omit=dev --audit-level=high`; gitleaks over the full git history (`.gitleaks.toml` allow-lists the patterned fake test keys only); bundle check that no server-side variable names or test secrets reach `dist/assets` |

Locally verified on 2026-10-17: pip-audit "No known vulnerabilities found", npm audit "found 0 vulnerabilities", gitleaks "no leaks found" (one finding — a fake test key in `backend/tests/conftest.py` — is allow-listed), bundle clean. All free for public and private repositories within GitHub's free minutes.

Recommended (OWNER, Settings > Branches): protect `main`, require the four CI jobs and one review before merging.

## CD flow

1. CI finishes successfully for a push to `main` → `cd.yml` starts with `SHA = workflow_run.head_sha` (the exact tested commit).
2. Job `deploy` uses the GitHub Environment **production**. Add a **required reviewer** there if every deploy should wait for your click.
3. SSH material comes from secrets and is written to files with `0600`/`0644`; it is never echoed, and GitHub masks secret values in logs. Host key checking is strict against a pinned `known_hosts`.
4. On the VM: `git fetch`, extract `deploy/remote-deploy.sh` **from the target commit**, run it with the SHA:
   - checkout `--detach <SHA>`, `docker compose build --pull api` tagged `tenq-api:<SHA>`, `up -d --remove-orphans` (never `down -v`: volumes are untouched),
   - wait for `api` and `nginx` to be healthy and `GET /api/v1/health` through nginx over TLS to succeed,
   - success: record `current_sha`/`previous_sha`, prune old images except current and previous,
   - failure: print logs, check out the previous SHA, `up -d` with its existing image, re-check health, exit non-zero (the workflow turns red).
5. Optional public check: if the repository variable `PUBLIC_URL` is set (`https://<project>.vercel.app`), the job calls `/api/v1/health` through Vercel.

Manual redeploy or rollback: Actions > cd > Run workflow > enter a 40-character SHA.

## Secrets and variables — OWNER

Settings > Environments > `production`:

| Name | Kind | Value |
|------|------|-------|
| `DEPLOY_HOST` | secret | VM public IP |
| `DEPLOY_USER` | secret | `deploy` |
| `DEPLOY_SSH_KEY` | secret | private key of a key pair made **only** for CD: `ssh-keygen -t ed25519 -f tenq_deploy -N ""`; put `tenq_deploy.pub` in `/home/deploy/.ssh/authorized_keys` on the VM |
| `DEPLOY_KNOWN_HOSTS` | secret | `ssh-keyscan -t ed25519 VM_IP`, after comparing the fingerprint with `sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` on the VM |
| `PUBLIC_URL` | variable | `https://<project>.vercel.app` |
| `DEPLOY_ENABLED` | variable (repository) | `true` once the VM is ready; until then automatic deploys are skipped (home hosting, `home-hosting.md`, is updated by hand) |

SSH reachability: GitHub-hosted runners use changing IP ranges, so port 22 must accept them. Options (all free): (a) open 22 to `0.0.0.0/0` with key-only auth (the Ubuntu default) and the `restrict` option on the deploy key in `authorized_keys` (a `from=` filter is not possible because runner IPs change); (b) keep 22 restricted and deploy manually with `sh deploy/remote-deploy.sh <sha>`; (c) a self-hosted runner on the VM (no inbound SSH, but runs workflow code on production — only for this private, owner-only repository). Default recommendation: (a) with `fail2ban` installed.

## What CD never does

- Remove volumes, prune volumes, or run `docker compose down -v`.
- Deploy a commit whose CI failed, or a pull request.
- Print environment files or secrets (the remote script reads the origin secret into a variable for the health probe and never echoes it).
- Touch Vercel, Cloudflare, or Oracle resources.
