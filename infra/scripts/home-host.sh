#!/bin/sh
# Temporary production hosting on the owner's own computer (until the Oracle VM exists).
#
#   Players -> https://<project>.vercel.app (frontend, /api rewrite with x-origin-secret)
#           -> https://<machine>.<tailnet>.ts.net (Tailscale Funnel, valid TLS)
#           -> nginx on 127.0.0.1:8080 -> api -> redis   (this compose stack)
#
# Usage: infra/scripts/home-host.sh up | down | status
# Volumes are never removed. Needs: podman-compose (or COMPOSE="docker compose"), tailscale
# logged in with HTTPS + Funnel enabled, and production values in infra/env/*.env.
set -u
cd "$(dirname "$0")/../.."
COMPOSE=${COMPOSE:-podman-compose}
PORT=${TENQ_HTTP_PORT:-8080}

value() { sed -n "s/^$2=//p" "infra/env/$1.env" 2>/dev/null; }

preflight() {
    ok=0
    for f in api redis nginx; do
        [ -f "infra/env/$f.env" ] || { echo "missing infra/env/$f.env"; ok=1; }
    done
    [ "$(value api TENQ_ENV)" = production ] || { echo "api.env: TENQ_ENV must be production"; ok=1; }
    [ "$(value nginx NGINX_ENFORCE_ORIGIN)" = on ] || { echo "nginx.env: NGINX_ENFORCE_ORIGIN must be on"; ok=1; }
    [ -n "$(value nginx NGINX_ORIGIN_SECRET)" ] && \
        [ "$(value nginx NGINX_ORIGIN_SECRET)" = "$(value api TENQ_ORIGIN_SECRETS | cut -d, -f1)" ] || \
        { echo "origin secret must be set and equal in nginx.env and api.env"; ok=1; }
    command -v tailscale >/dev/null || { echo "tailscale is not installed"; ok=1; }
    return $ok
}

wait_ready() {
    for _ in $(seq 1 60); do
        curl -fsS --max-time 3 "http://127.0.0.1:$PORT/nginx-health" >/dev/null 2>&1 && \
            curl -fsS --max-time 5 -o /dev/null -H "X-Origin-Secret: $(value nginx NGINX_ORIGIN_SECRET)" \
                "http://127.0.0.1:$PORT/api/v1/health" && return 0
        sleep 2
    done
    return 1
}

case "${1:-status}" in
    up)
        preflight || exit 1
        $COMPOSE up -d --build >/dev/null 2>&1 || true
        if ! wait_ready; then echo "stack is not healthy; see: $COMPOSE logs api nginx"; exit 1; fi
        # Publish nginx through Funnel (TLS terminated by tailscaled, background config).
        tailscale funnel --bg "http://127.0.0.1:$PORT" >/dev/null || exit 1
        echo "stack healthy; Funnel on:"
        tailscale funnel status
        ;;
    down)
        tailscale funnel reset >/dev/null 2>&1 || true
        $COMPOSE down >/dev/null 2>&1 || true   # keeps volumes (no -v)
        echo "Funnel off, containers stopped, data kept."
        ;;
    status)
        $COMPOSE ps 2>/dev/null
        tailscale funnel status 2>/dev/null || echo "Funnel: not configured"
        ;;
    *) echo "usage: $0 up | down | status"; exit 2 ;;
esac
