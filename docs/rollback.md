# Rollback

Every deploy builds `tenq-api:<commit SHA>` and records `/opt/tenq/state/current_sha` and `previous_sha`. The previous image is kept, so a rollback restarts it without rebuilding. Volumes (SQLite, Redis) are never touched by deploys or rollbacks.

## Automatic

`deploy/remote-deploy.sh` rolls back by itself when the new release does not become healthy within about two minutes (container health + `GET /api/v1/health` through nginx over TLS). The CD run is then red and the logs show `rolling back to <sha>`.

## Manual — backend

Fastest (on the VM):
```bash
cd /opt/tenq/app
sudo -u deploy sh deploy/rollback.sh                 # back to previous_sha
sudo -u deploy sh deploy/rollback.sh <older-sha>     # or a specific release
```
From GitHub: Actions > cd > Run workflow > SHA of the release to restore.

Then fix forward: revert the bad commit on `main` through a pull request; CI and CD redeploy.

## Manual — frontend

Vercel > Project > Deployments > pick the last good production deployment > **Promote to Production** (instant, free). Or revert the commit on `main`.

## Data

- **Schema migrations are forward-only.** A release that adds a migration (for example `0002_word_hints.sql`) leaves the database at the new version after a rollback. Migrations are written to be backward compatible (new nullable/defaulted columns), so the previous code keeps working. A migration that is not backward compatible must say so in its PR and needs a backup taken just before deploying.
- **Redis state** (today's games) survives rollbacks. If a release corrupted it, restore from `/opt/tenq/backups/<time>/redis-data.tgz` (see the runbook); this loses games after that backup.
- **SQLite restore**: stop the API (`docker compose ... stop api`), copy the backup into the volume with a temporary container, start the API. Exact commands: `docs/operations-runbook.md`.

## Configuration

Environment files are not versioned on the VM. Before changing `infra/env/*.env`, copy them (`cp api.env api.env.$(date -u +%F)`); to roll back a configuration change, restore the copy and run `docker compose -f compose.yaml -f compose.prod.yaml up -d` with the current `TENQ_RELEASE`.
