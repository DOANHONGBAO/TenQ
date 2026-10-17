#!/bin/sh
# Nightly backup of SQLite (online backup API) and Redis (AOF + RDB) into /opt/tenq/backups.
# Keeps 14 days. Files are root-only. Copy them off the VM (or rely on Oracle boot-volume
# backups, 5 free) for disaster recovery: they contain the secret word list and results.
set -eu
cd /opt/tenq/app
OUT=/opt/tenq/backups/$(date -u +%Y%m%dT%H%M%SZ)
umask 077
mkdir -p "$OUT"
dc() { docker compose -f compose.yaml -f compose.prod.yaml "$@"; }
export TENQ_RELEASE=$(cat /opt/tenq/state/current_sha)

# SQLite: consistent copy while the API keeps running.
dc exec -T api python -c "import sqlite3; s=sqlite3.connect('/data/tenq.sqlite3'); d=sqlite3.connect('/tmp/backup.sqlite3'); s.backup(d); d.close()"
docker cp "$(dc ps -q api):/tmp/backup.sqlite3" "$OUT/tenq.sqlite3"
dc exec -T api rm -f /tmp/backup.sqlite3

# Redis: fresh RDB snapshot, then archive the whole data directory (RDB + AOF).
dc exec -T redis sh -c 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli BGSAVE' >/dev/null
sleep 5
docker run --rm -v tenq_redis-data:/data:ro -v "$OUT":/backup docker.io/library/alpine:3.20 \
    tar czf /backup/redis-data.tgz -C /data .

find /opt/tenq/backups -mindepth 1 -maxdepth 1 -type d -mtime +14 -exec rm -rf {} +
echo "backup: $OUT"
