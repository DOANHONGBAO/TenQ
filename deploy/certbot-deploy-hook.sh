#!/bin/sh
# Certbot deploy hook: runs after every successful issue/renewal.
# Install: sudo install -m 755 deploy/certbot-deploy-hook.sh /etc/letsencrypt/renewal-hooks/deploy/tenq.sh
# Copies the certificate where the unprivileged nginx container (uid 101) can read it, then
# reloads nginx without dropping connections.
set -eu
DEST=/opt/tenq/tls
install -d -m 750 -o 101 -g 101 "$DEST"
install -m 644 -o 101 -g 101 "$RENEWED_LINEAGE/fullchain.pem" "$DEST/fullchain.pem"
install -m 600 -o 101 -g 101 "$RENEWED_LINEAGE/privkey.pem" "$DEST/privkey.pem"
container=$(docker ps -q --filter label=com.docker.compose.project=tenq --filter label=com.docker.compose.service=nginx)
[ -n "$container" ] && docker kill -s HUP "$container" >/dev/null
echo "tenq: certificate installed and nginx reloaded"
