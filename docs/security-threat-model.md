# Security Threat Model

- Status: Proposed in Phase 01; updated in Phase 06 (2026-10-17) with the implemented identity, proxy-trust, and anti-abuse controls ([ADR 0014](decisions/0014-proxy-trust-and-session-hardening.md)). Method: assets, trust boundaries, then threats per STRIDE category with concrete mitigations and residual risk. Review whenever the architecture changes.

## 1. Assets

| Asset | Why it matters |
|-------|----------------|
| A1. Today's secret word | Leaking it destroys the game for everyone (BR-12) |
| A2. Attempt integrity | Fairness of the 10-question limit (BR-04, BR-07) |
| A3. Leaderboard integrity | Public ranking (BR-10) |
| A4. API keys and signing keys | Abuse of the AI quota; forged sessions |
| A5. AI quota and service availability | Free tier is small (NFR-04) |
| A6. Player privacy | No accounts; IPs and behavior must not be collected (NFR-05) |
| A7. Origin server | Compromise exposes A1 and A4 |

## 2. Trust boundaries

1. Browser to Vercel (internet, untrusted client).
2. Vercel to Nginx origin (internet; authenticated with `x-origin-secret`).
3. Nginx to API, API to Redis/SQLite (Docker internal network).
4. API to Ollama Cloud and Cloudflare (internet; outbound HTTPS with secrets).
5. GitHub Actions to VM (SSH deploy key, protected environment).

## 3. Threats and mitigations

| ID | STRIDE | Threat | Mitigation | Residual risk |
|----|--------|--------|------------|---------------|
| T-01 | Info disclosure | Secret word read from the public repo | Word list and seed only on the VM (`/opt/tenq/secrets`, read-only mount); repo has a fake dev list; secret scanning in CI | Owner's local copy must be protected |
| T-02 | Info disclosure | Secret predicted from date | Keyed yearly permutation with HMAC-SHA256 (ADR 0012); key never published; vocabulary file kept out of the repository | Seed leak reveals all future words: rotate seed and start a new selection version |
| T-03 | Info disclosure | Secret leaked through API responses, errors, logs, frontend bundle | API returns only labels; answer endpoint only for past dates; logs never include the word or prompts; no secret in `VITE_*` | None known |
| T-04 | Info disclosure | Prompt injection makes the model reveal the word | Model output is reduced to one of 5 labels; free text is discarded | Players can extract information one bit at a time, which is the game itself |
| T-05 | Tampering | Forged `WIN` via injection ("Answer WIN") | Server verifies the word appears in the question before accepting `WIN` | None |
| T-06 | Tampering | Exceeding 10 questions with parallel requests or replays | Atomic Lua reserve/commit, single lease, idempotency keys | None if Redis is consistent |
| T-07 | Spoofing | Clearing cookies to get a fresh 10 questions | Turnstile per session (single-use, 300 s, replay cache); session creation limits per IP hash (30/h) and per IP+UA device hash (10/h); question limits per IP hash | **Cannot be fully prevented without accounts or hardware-bound identity** (section 6). Users with many IPs or browsers can still farm; accepted for a no-login game |
| T-08 | Spoofing | Forged session cookie or another player's id | HMAC-signed cookie, 128-bit random ids, constant-time comparison, server-side 365-day expiry, future timestamps rejected, current+previous secret rotation with re-signing; player hash key separate from cookie secret | Cookie theft from the device (XSS or malware) gives that player's game; HttpOnly limits XSS reach |
| T-09 | Spoofing | Bypassing Vercel to hit the origin directly (avoids per-client limits, fakes `X-Real-IP` / `X-Forwarded-For`) | Vercel overwrites `X-Forwarded-For` and sets `x-origin-secret` via a routes transform; the API refuses requests without a valid secret (`403 FORBIDDEN_ORIGIN`) and uses forwarded IPs only behind it, otherwise the TCP peer; Nginx repeats the check (Phase 10) | Secret leak lets an attacker pick their IP until rotation (dual-secret window); HMAC gateway documented as fallback (ADR 0014) |
| T-10 | Tampering | Leaderboard manipulation | Only the server writes results, inside `commit`; one entry per player per day (`ZADD NX`, SQLite UNIQUE) | Farmed sessions (T-07) can submit lucky wins |
| T-11 | Repudiation | Disputes about answers | Per-day judgement cache gives everyone identical answers; history stored per game | Model may still answer a question wrongly |
| T-12 | Denial of service | Flooding the API or burning the AI quota | Nginx `limit_req`; app fixed-window limits (questions 6/min per player and 40/min per IP hash, reads 180/min per IP hash, sessions as T-07); 4 questions in flight per IP hash; one in-flight question per player; 4 KB body limit; hourly and daily AI budget; per-day cache; circuit breaker | Free AI quota can still be exhausted; game degrades with `AI_UNAVAILABLE` and no charge; blocked requests are never charged |
| T-13 | Denial of service | Redis memory exhaustion | Bounded key sizes, question length limit, `maxmemory` + `noeviction`, EXPIREAT on all per-day keys | Under attack, writes fail with `503` instead of corrupting state |
| T-14 | Elevation | Container escape / RCE in the API | Non-root containers, read-only root filesystem where possible, minimal images, pinned dependencies with Dependabot, no shell-outs | Zero-day in dependencies |
| T-15 | Elevation | CI/CD compromise deploys malicious code | Actions pinned by SHA, `permissions: contents: read` by default, production environment with required reviewer, no secrets on `pull_request` from forks | Owner GitHub account compromise: use 2FA |
| T-16 | Info disclosure | Privacy: tracking players | No raw IPs stored; IP hash salted per day; no third-party analytics; player hash in storage | Cloudflare and Vercel see IPs as processors |
| T-17 | Tampering | CSRF on state-changing endpoints | `SameSite=Lax` cookie, JSON-only bodies with `Content-Type` check, same-origin API, no CORS allowed origins | None for modern browsers |
| T-18 | Tampering | XSS showing other players' text | Only auto-generated display names; React escaping; no `dangerouslySetInnerHTML`; strict CSP on the SPA | Low |
| T-19 | Info disclosure | Backups leak the word and results | Backups encrypted (age) before leaving the VM; restricted file permissions | Owner must protect the decryption key |
| T-20 | Spoofing | Man-in-the-middle between Vercel and origin | HTTPS with a valid certificate (IP certificate or domain) | Short certificate lifetime: renewal failure causes outage; monitored |
| T-21 | Spoofing | Bots creating sessions with replayed, expired, or test Turnstile tokens | Siteverify checks success, hostname allow-list, action `session`, `challenge_ts` ≤ 300 s; local replay cache; test keys refused in production; missing token never reaches Cloudflare | Turnstile can be solved by humans or paid solving services |
| T-22 | Denial of service | Turnstile/Cloudflare outage blocks new players | Fail closed (`503`), existing sessions keep playing | New players cannot start during the outage (deliberate) |
| T-23 | Info disclosure | Error responses revealing internals | Uniform error envelope; generic `500` without stack traces; Turnstile reasons and provider errors only in logs | Logs must be protected |
| T-24 | Info disclosure | Privacy of invisible bot checks | Privacy notice in the SPA footer and `privacy.html` naming Cloudflare Turnstile and its policies | None known |

## 4. Security controls by phase

| Phase | Controls delivered |
|-------|--------------------|
| 02 | Settings with required secrets, error envelope without stack traces, request ids, secret scanning in CI, `.env.example` |
| 03 | Question validation and normalization, keyed word selection, dev word list only |
| 04 | Atomic Lua scripts, idempotency, concurrency tests |
| 05 | Label-only output, WIN verification, timeouts, retries, budget, injection corpus tests |
| 06 | Signed cookies with rotation and expiry, Turnstile (invisible) with replay cache, origin-secret proxy trust, IP/device hashing, rate and concurrency limits, body limit, generic errors, privacy notice |
| 10 | Nginx origin secret, TLS, firewall, non-root containers, encrypted backups, protected deploy |

## 5. Security testing

- Unit and integration tests for each mitigation above (listed per phase in [roadmap.md](roadmap.md)).
- Injection corpus from the `tenq-ai-judge-testing` skill run against the parser and a fake provider.
- Before launch: dependency audit (`pip-audit`, `npm audit`), container scan (Trivy), and a manual review using the `tenq-deployment-audit` skill.

## 6. Why "10 questions per device" cannot be guaranteed

TenQ has no accounts and does not bind identity to hardware, by design (zero-login, privacy). The server can only count questions per **anonymous session cookie**. A person who clears cookies, opens a private window, uses a second browser, or switches network gets a new session after passing Turnstile again. Every possible device signal is either changeable by the user (cookies, User-Agent, IP via mobile data or VPN) or shared by many honest users (one public IP for a whole school or carrier-grade NAT), so treating any of them as a hard identity would either fail to stop a determined user or lock out innocent ones.

What the design does guarantee: one session never gets more than 10 charged questions per UTC day, even under concurrency and retries; farming more sessions costs a Turnstile pass each and is capped per IP hash and per device hash; leaderboard entries remain one per session. A stronger guarantee would need accounts (email or OAuth) or platform attestation, which conflicts with the zero-login requirement.
