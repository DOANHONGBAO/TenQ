# ADR 0007: Vercel external rewrite to the Oracle origin over HTTPS

- Status: Proposed
- Date: 2026-10-17

## Context

The SPA is hosted on Vercel; the API runs on an Oracle VM with only a public IP. Browsers block or restrict third-party cookies, mixed content is forbidden, and a custom domain costs money (NFR-02).

## Options considered

1. **Browser calls the VM directly (`https://<ip>` or another domain)** — needs CORS; the session cookie becomes third-party and is blocked by Safari and increasingly by Chrome. Rejected.
2. **Custom domain (`app.example.com` + `api.example.com`)** — same-site cookies, clean URLs; requires buying a domain (about USD 10 per year). Optional upgrade with owner approval.
3. **Free dynamic DNS subdomain (e.g. DuckDNS) on the VM** — free, but depends on a volunteer-run service and still needs the proxy or CORS.
4. **Cloudflare Tunnel** — no open ports; requires a domain on Cloudflare for a stable hostname.
5. **Vercel external rewrite `/api/:path*` -> `https://<oracle-ip>/api/:path*`** — browser sees one origin (first-party cookie, no CORS); Vercel documents adding a secret request header so the origin rejects direct traffic, and forwards `x-real-ip` / `x-forwarded-for`.

## Decision

Option 5, with TLS on the origin from a **Let's Encrypt IP address certificate** (generally available since January 2026; 160-hour lifetime; `shortlived` ACME profile; automatic renewal). Nginx rejects requests without the correct `x-origin-secret` and trusts `x-real-ip` only after that check.

## Consequences

- Zero cost, first-party cookies, no CORS configuration.
- Extra hop through Vercel adds some latency; API responses use `Cache-Control: no-store` so Vercel never caches them.
- Proxy traffic counts toward Vercel Hobby usage (Fast Origin Transfer 10 GB per month); fine for about 1 KB responses.
- **Must be verified early** (Phase 10 spike, can be pulled forward): Set-Cookie pass-through, forwarded IP headers, proxy timeout versus the 20 s AI deadline, and certificate renewal on arm64. If any fails, fall back to option 2 (paid, needs approval) or option 3.
- The Oracle public IP should be a reserved IP so it does not change on instance re-creation (verify Always Free eligibility during Phase 10).
