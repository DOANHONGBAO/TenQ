#!/bin/sh
# Refuse to start with an empty or weak origin secret: an empty value would make the
# "secret matches" map entry match requests that send no secret at all.
set -eu
if [ "${#NGINX_ORIGIN_SECRET}" -lt 32 ]; then
    echo "tenq: NGINX_ORIGIN_SECRET must be set (at least 32 characters)" >&2
    exit 1
fi
case "${NGINX_ENFORCE_ORIGIN}" in
    on|off) ;;
    *) echo "tenq: NGINX_ENFORCE_ORIGIN must be 'on' or 'off'" >&2; exit 1 ;;
esac
