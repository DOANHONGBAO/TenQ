#!/bin/sh
# Container integration test: build, start, seed, smoke, restart, recreate, persistence,
# graceful shutdown, exposure. Runs as a separate compose project ("tenq-it") with its own
# volumes, which are deleted at the end, so local game data is untouched.
# Usage: COMPOSE="docker compose" infra/scripts/integration.sh     (default: podman-compose)
set -eu
cd "$(dirname "$0")/../.."
P=tenq-it
COMPOSE="${COMPOSE:-podman-compose} -p $P"
ENGINE=${ENGINE:-$(echo "$COMPOSE" | cut -d' ' -f1 | sed 's/-compose//')}
cid() { $ENGINE ps -aq --filter "label=com.docker.compose.project=$P" --filter "label=com.docker.compose.service=$1"; }
BASE=http://127.0.0.1:${TENQ_HTTP_PORT:-8080}
JAR=$(mktemp)
trap 'rm -f "$JAR"' EXIT
pass=0
fail=0
check() { if [ "$2" -eq 0 ]; then pass=$((pass + 1)); echo "ok   $1"; else fail=$((fail + 1)); echo "FAIL $1"; fi; }
uuid() { python3 -c 'import uuid; print(uuid.uuid4())'; }
used() {
    curl -s -b "$JAR" "$BASE/api/v1/game/today" |
        python3 -c 'import json,sys; b=json.load(sys.stdin); print(b.get("used", b))'
}
wait_healthy() {
    for _ in $(seq 1 40); do
        n=$($ENGINE ps --filter "label=com.docker.compose.project=$P" --format '{{.Status}}' | grep -c '(healthy)' || true)
        [ "$n" -ge 3 ] && return 0
        sleep 2
    done
    return 1
}

[ -e infra/env/api.env ] || infra/scripts/gen-env.sh
echo "== build and start"
$COMPOSE build >/dev/null 2>&1
$COMPOSE up -d >/dev/null 2>&1 || true
wait_healthy; check "all three containers healthy" $?
$COMPOSE run --rm -T api python -m app.scripts.seed_words --dev >/dev/null 2>&1; check "seed (fake words)" $?

echo "== exposure"
[ -z "$($ENGINE port "$(cid redis)")" ] && [ -z "$($ENGINE port "$(cid api)")" ]; check "redis and api publish no ports" $?
$ENGINE exec "$(cid redis)" sh -c 'wget -q -T 3 -O /dev/null http://example.com' >/dev/null 2>&1 && r=1 || r=0
check "redis has no internet route" $r

echo "== smoke through nginx"
LOG=$(mktemp)
infra/scripts/smoke.sh "$BASE" >"$LOG" 2>&1; check "smoke.sh ($(tail -1 "$LOG"))" $?

echo "== persistence"
code=$(curl -s -o /dev/null -w '%{http_code}' -c "$JAR" -H 'Content-Type: application/json' \
    -H 'User-Agent: tenq-integration' -d "{\"turnstile_token\": \"$(uuid)\"}" "$BASE/api/v1/session")
[ "$code" = 201 ]; check "session for persistence test ($code)" $?
sleep 2
curl -s -b "$JAR" -H "Idempotency-Key: $(uuid)" -H 'Content-Type: application/json' \
    -d '{"question": "Is it persistent?"}' "$BASE/api/v1/game/today/questions" >/dev/null
before=$(used)
# podman-compose restart can exit non-zero on stop-timeout warnings; the checks decide.
$COMPOSE restart >/dev/null 2>&1 || true
wait_healthy || true
[ "$(used)" = "$before" ]; check "game state survives restart (used=$before)" $?
$COMPOSE down >/dev/null 2>&1 || true
[ -n "$(cid api)" ] && r=1 || r=0
check "down removes containers" $r
$COMPOSE up -d >/dev/null 2>&1 || true
wait_healthy || true
[ "$(used)" = "$before" ]; check "game state survives down + up (volumes kept)" $?
$ENGINE exec "$(cid redis)" ls /data/appendonlydir >/dev/null 2>&1; check "redis AOF files on the volume" $?

echo "== graceful shutdown"
api=$(cid api)
$ENGINE stop -t 30 "$api" >/dev/null
$ENGINE logs --tail 5 "$api" 2>&1 | grep -q "Finished server process"; check "api drains and exits cleanly on SIGTERM" $?
$COMPOSE down -v >/dev/null 2>&1   # test project only: remove its volumes

echo
echo "passed: $pass, failed: $fail"
[ "$fail" -eq 0 ]
