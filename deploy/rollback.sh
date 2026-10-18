#!/bin/sh
# Roll back to a previous deployed commit (default: the one recorded before the current).
#   sh deploy/rollback.sh            # previous_sha
#   sh deploy/rollback.sh <sha>      # a specific earlier release
# Reuses the tagged image when it still exists, so no rebuild is needed. Volumes untouched.
set -eu
STATE=/opt/tenq/state
TARGET=${1:-$(cat "$STATE/previous_sha" 2>/dev/null || true)}
[ -n "$TARGET" ] || { echo "rollback: no previous release recorded; pass a SHA" >&2; exit 2; }
exec sh "$(dirname "$0")/remote-deploy.sh" "$TARGET"
