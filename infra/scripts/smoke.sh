#!/bin/sh
# End-to-end checks against a running compose stack (local, NGINX_ENFORCE_ORIGIN=off).
# Usage: infra/scripts/smoke.sh [base_url]     default http://127.0.0.1:8080
# Needs: curl, python3. Uses the Cloudflare test Turnstile secret configured in api.env.
set -eu
BASE=${1:-http://127.0.0.1:8080}
JAR=$(mktemp)
trap 'rm -f "$JAR" /tmp/tenq-smoke.*' EXIT
pass=0
fail=0
check() { # name, condition result (0 = ok)
    if [ "$2" -eq 0 ]; then pass=$((pass + 1)); echo "ok   $1"; else fail=$((fail + 1)); echo "FAIL $1"; fi
}
uuid() { python3 -c 'import uuid; print(uuid.uuid4())'; }
status() { curl -s -o /tmp/tenq-smoke.body -D /tmp/tenq-smoke.head -w '%{http_code}' "$@"; }
header() { grep -i "^$1:" /tmp/tenq-smoke.head | tr -d '\r' | cut -d' ' -f2-; }
ask() { # question, then optional extra curl arguments
    q=$1
    shift
    status -b "$JAR" -c "$JAR" -H "Idempotency-Key: $(uuid)" -H 'Content-Type: application/json' \
        -d "{\"question\": \"$q\"}" "$@" "$BASE/api/v1/game/today/questions"
}

echo "== routing and headers"
[ "$(status "$BASE/nginx-health")" = 200 ]; check "nginx health" $?
[ "$(status "$BASE/api/v1/health")" = 200 ]; check "api health through nginx" $?
[ "$(header X-Content-Type-Options)" = nosniff ]; check "security headers present" $?
[ -z "$(header X-Powered-By)" ] && ! grep -qi '^server: .*/' /tmp/tenq-smoke.head; check "no version in Server header" $?
[ "$(status "$BASE/")" = 404 ] && grep -q NOT_FOUND /tmp/tenq-smoke.body; check "non-API path is a JSON 404" $?

echo "== session and game"
code=$(status -c "$JAR" -H 'Content-Type: application/json' -d "{\"turnstile_token\": \"$(uuid)\"}" "$BASE/api/v1/session")
[ "$code" = 201 ] || [ "$code" = 200 ]; check "session created ($code)" $?
[ "$(status -b "$JAR" "$BASE/api/v1/game/today")" = 200 ]; check "game state" $?
grep -qi 'no-store' /tmp/tenq-smoke.head; check "game response not cacheable" $?
before=$(python3 -c 'import json; print(json.load(open("/tmp/tenq-smoke.body"))["used"])')

echo "== edge rate limit (1 question / 2 s per client IP)"
sleep 2
first=$(ask "Is it alive number $before?")
second=$(ask "Is it big number $before?")
[ "$first" = 200 ] && [ "$second" = 429 ]; check "second question within 2 s is limited ($first, $second)" $?
[ "$(header X-RateLimit-Source)" = nginx ] && grep -q '"source":"edge"' /tmp/tenq-smoke.body; check "edge 429 is marked as nginx" $?
sleep 2
third=$(ask "Is it small number $before?" -H 'X-Forwarded-For: 203.0.113.99' -H 'X-Real-IP: 203.0.113.99')
fourth=$(ask "Is it red number $before?" -H 'X-Forwarded-For: 198.51.100.7' -H 'X-Real-IP: 198.51.100.7')
[ "$third" = 200 ] && [ "$fourth" = 429 ]; check "spoofed X-Forwarded-For/X-Real-IP do not bypass the limit ($third, $fourth)" $?

echo "== body limit"
big=$(python3 -c 'print("{\"question\": \"" + "x" * 6000 + "?\"}")')
[ "$(status -b "$JAR" -H "Idempotency-Key: $(uuid)" -H 'Content-Type: application/json' -d "$big" "$BASE/api/v1/game/today/questions")" = 413 ]
check "body over 4 KB rejected at the edge" $?

echo "== state"
status -b "$JAR" "$BASE/api/v1/game/today" > /dev/null
after=$(python3 -c 'import json; print(json.load(open("/tmp/tenq-smoke.body"))["used"])')
[ "$after" -eq $((before + 2)) ]; check "only the 2 accepted questions were charged ($before -> $after)" $?
cp "$JAR" "${TENQ_SMOKE_JAR:-/tmp/tenq-smoke-session.cookies}"

echo
echo "passed: $pass, failed: $fail"
[ "$fail" -eq 0 ]
