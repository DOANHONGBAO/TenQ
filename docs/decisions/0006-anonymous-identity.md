# ADR 0006: Anonymous identity with a signed random-id cookie

- Status: Proposed
- Date: 2026-10-17

## Context

No login (BR-11), but the server must count questions per player (BR-04) and protect privacy (NFR-05).

## Options considered

1. **Browser fingerprinting** — survives cookie clearing, but is invasive, unreliable, and conflicts with NFR-05. Rejected.
2. **IP address as identity** — breaks for shared networks (offices, mobile carriers), leaks personal data. Rejected as identity; used only hashed for rate limits.
3. **JWT with claims** — self-contained, but state already lives in Redis; JWT adds algorithm pitfalls without benefit.
4. **Random 128-bit id in an HMAC-signed HttpOnly cookie** — minimal, revocable by key rotation, no personal data.
5. **`localStorage` token** — readable by any XSS; rejected in favor of HttpOnly.

## Decision

Option 4. Cookie `tenq_sid` (`HttpOnly; Secure; SameSite=Lax; Path=/api; Max-Age=1 year`), created only after Turnstile verification. Storage uses `player_hash` (keyed HMAC of the id). IPs are used only as `HMAC(ip_key, date + ip)` for rate limits, so the hash changes daily and cannot be linked across days.

## Consequences

- Clearing cookies yields a new player (accepted limitation, threat T-07), limited by Turnstile and per-IP-hash limits.
- No personal data is stored, which keeps privacy obligations small.
- Cookies are first-party thanks to the Vercel proxy (ADR 0007); third-party cookie blocking does not affect the game.
