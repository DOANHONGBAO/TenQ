# ADR 0014: Proxy trust, session hardening, and anti-abuse limits

- Status: Proposed
- Date: 2026-10-17
- Refines: [ADR 0006](0006-anonymous-identity.md) (identity) and [ADR 0007](0007-vercel-proxy-to-oracle-origin.md) (Vercel to Oracle).

## Context

Phase 06 asks whether Vercel external rewrites give the Oracle origin a client IP it can trust, how to stop direct calls to the origin, and how to harden anonymous sessions without accounts. Facts checked on 2026-10-17:

- vercel.com/docs/headers/request-headers: Vercel overwrites `X-Forwarded-For` and "do[es] not forward external IPs ... to prevent IP spoofing"; `x-real-ip` and `x-vercel-forwarded-for` carry the same value. Custom trusted proxies are Enterprise only.
- vercel.com/docs/routing/rewrites: on external rewrites Vercel forwards `x-real-ip`, `x-forwarded-for`, `x-forwarded-host`, `x-forwarded-proto`. A `routes` entry with a `request.headers` transform can `set` a header such as `x-origin-secret` from an environment variable; "because the `set` operation replaces any existing value, a visitor can't supply their own".
- Turnstile Siteverify: tokens valid 300 s, single use; test secrets answer with hostname `example.com`, no action, and `metadata.result_with_testing_key`.

## Options considered

1. **External rewrite + `x-origin-secret` transform** (Vercel docs' recommended pattern). Free, no function invocations, no extra latency. Trust rests on a static shared secret over TLS.
2. **Minimal Vercel Function gateway** that signs each request with HMAC (method, path, timestamp, body hash) before forwarding. Stronger against secret replay and lets the origin reject stale requests, but every API call becomes a function invocation (Hobby quota), adds cold starts and latency, and adds code to maintain.
3. **Trust `X-Forwarded-For` from anyone.** Rejected: anyone reaching the origin directly can choose their IP.

## Decision

Option 1, with the gateway (option 2) documented as the fallback if the transform stops being available or if the shared secret ever leaks repeatedly.

- The API trusts `x-real-ip` (then `x-forwarded-for`) only when `x-origin-secret` matches one of `TENQ_ORIGIN_SECRETS` (current and previous, constant-time comparison). Otherwise it uses the TCP peer address.
- When `TENQ_ORIGIN_SECRETS` is set (required in production), requests without a valid secret get `403 FORBIDDEN_ORIGIN` before routing; `/api/v1/health` stays open for container health checks. Nginx (Phase 10) enforces the same check and must pass `X-Real-IP` from Vercel through unchanged.
- Sessions: `POST /session` requires a Turnstile token (invisible widget, action `session`); checks success, hostname allow-list, action, `challenge_ts` within 300 s, and refuses test keys in production. Tokens are remembered in Redis for 300 s to refuse replays before calling Cloudflare. Siteverify errors fail closed (`503`).
- Cookie: `<player_id>.<issued_at>.<HMAC>`; expires server-side after 365 days; future timestamps rejected; `TENQ_SESSION_SECRET_PREVIOUS` keeps old cookies valid during rotation and they are re-signed on use. `TENQ_PLAYER_HASH_KEY` is separate, so rotating the cookie secret keeps game state and leaderboard entries.
- IP and User-Agent are only rate-limit subjects: `ip_hash` (daily HMAC) and `device_hash` (ip_hash + UA hash). Session creation is limited per IP hash (30/h) and per device (10/h), so several people behind one NAT can each start a session while one device cannot farm many. Questions: 6/min per player, 40/min per IP hash, 4 in flight per IP hash. Reads: 180/min per IP hash. All are configurable.
- Request bodies are capped at 4 KB (Content-Length and while streaming); unexpected errors return a generic `500` envelope.

## Consequences

- No extra Vercel usage; a leaked origin secret lets an attacker choose `x-real-ip` until it is rotated (dual-secret window).
- Without accounts or hardware-bound identity, one physical device can still obtain more than one game per day by clearing cookies and passing Turnstile again from another network; limits make this slow and visible, not impossible.
- `GET /game/today` no longer creates sessions; clients must call `POST /session` first.
