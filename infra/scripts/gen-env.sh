#!/bin/sh
# Create infra/env/*.env for LOCAL testing with fresh random secrets (never reuse in prod).
set -eu
cd "$(dirname "$0")/../env"
hex() { python3 -c "import secrets; print(secrets.token_hex($1))"; }
for f in api redis nginx; do
    if [ -e "$f.env" ]; then echo "$f.env exists, leaving it unchanged"; fi
done
[ -e redis.env ] || printf 'REDIS_PASSWORD=%s\n' "$(hex 24)" > redis.env
[ -e nginx.env ] || {
    sed "s/^NGINX_ORIGIN_SECRET=.*/NGINX_ORIGIN_SECRET=$(hex 32)/" nginx.env.example > nginx.env
}
if [ ! -e api.env ]; then
    redis_pw=$(sed -n 's/^REDIS_PASSWORD=//p' redis.env)
    origin=$(sed -n 's/^NGINX_ORIGIN_SECRET=//p' nginx.env)
    sed -e "s/^TENQ_WORD_SELECTION_KEY=.*/TENQ_WORD_SELECTION_KEY=$(hex 32)/" \
        -e "s/^TENQ_SESSION_SECRET=.*/TENQ_SESSION_SECRET=$(hex 32)/" \
        -e "s/^TENQ_PLAYER_HASH_KEY=.*/TENQ_PLAYER_HASH_KEY=$(hex 32)/" \
        -e "s/CHANGE_ME_REDIS_PASSWORD/$redis_pw/" \
        -e "s/^TENQ_ORIGIN_SECRETS=.*/TENQ_ORIGIN_SECRETS=$origin/" \
        api.env.example > api.env
fi
chmod 600 api.env redis.env nginx.env
echo "infra/env/*.env ready (values not printed)."
