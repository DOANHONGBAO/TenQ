#!/bin/sh
# Deploy one exact commit on the Oracle VM. Called by the CD workflow over SSH:
#   sh remote-deploy.sh <40-character commit SHA>
# Safe by construction: volumes are never removed (no "down -v"); the API image is tagged
# with the SHA so a rollback reuses the previous image; a failed health check rolls back.
set -eu

SHA=${1:-}
case "$SHA" in
    *[!0-9a-f]* | "") echo "deploy: expected a 40-character lowercase commit SHA" >&2; exit 2 ;;
esac
[ "${#SHA}" -eq 40 ] || { echo "deploy: expected a 40-character commit SHA" >&2; exit 2; }

APP=/opt/tenq/app
STATE=/opt/tenq/state
mkdir -p "$STATE"
cd "$APP"

dc() { release=$1; shift; TENQ_RELEASE=$release docker compose -f compose.yaml -f compose.prod.yaml "$@"; }

healthy() { # wait up to ~2 minutes for api and nginx to report healthy, then probe through nginx
    for _ in $(seq 1 40); do
        api=$(docker inspect -f '{{.State.Health.Status}}' "$(dc "$1" ps -q api)" 2>/dev/null || echo none)
        web=$(docker inspect -f '{{.State.Health.Status}}' "$(dc "$1" ps -q nginx)" 2>/dev/null || echo none)
        if [ "$api" = healthy ] && [ "$web" = healthy ]; then
            # Through nginx over TLS with the origin secret (value read from the env file,
            # never printed). -k only because the certificate names the public IP, not 127.0.0.1.
            secret=$(sed -n 's/^NGINX_ORIGIN_SECRET=//p' infra/env/nginx.env)
            if curl -fsS -k --max-time 5 -o /dev/null -H "X-Origin-Secret: $secret" \
                https://127.0.0.1/api/v1/health; then
                return 0
            fi
        fi
        sleep 3
    done
    return 1
}

previous=$(cat "$STATE/current_sha" 2>/dev/null || true)
echo "deploy: current=${previous:-none} target=$SHA"

git fetch --quiet origin
git cat-file -e "$SHA^{commit}"
git checkout --quiet --detach "$SHA"

echo "deploy: building tenq-api:$SHA"
dc "$SHA" build --pull api
echo "deploy: starting containers"
dc "$SHA" up -d --remove-orphans

if healthy "$SHA"; then
    [ -n "$previous" ] && [ "$previous" != "$SHA" ] && echo "$previous" > "$STATE/previous_sha"
    echo "$SHA" > "$STATE/current_sha"
    # Keep the three most recent API images for rollbacks; never touches volumes.
    docker image ls tenq-api --format '{{.Tag}}' | grep -vx "$SHA" | grep -vx "${previous:-none}" \
        | tail -n +2 | sed 's/^/tenq-api:/' | xargs -r docker image rm >/dev/null 2>&1 || true
    echo "deploy: OK $SHA"
    exit 0
fi

echo "deploy: health check FAILED for $SHA" >&2
dc "$SHA" logs --tail 50 api nginx >&2 || true
if [ -n "$previous" ]; then
    echo "deploy: rolling back to $previous" >&2
    git checkout --quiet --detach "$previous"
    dc "$previous" up -d --remove-orphans
    if healthy "$previous"; then
        echo "deploy: rollback to $previous is healthy" >&2
    else
        echo "deploy: rollback ALSO unhealthy: manual action needed (docs/rollback.md)" >&2
    fi
fi
exit 1
