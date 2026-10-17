# ADR 0011: Operating within free tiers and degrading gracefully

- Status: Proposed
- Date: 2026-10-17

## Context

All services must be free (NFR-02) and are treated as unreliable (NFR-04). Limits checked on 2026-10-17:

- **Ollama Cloud free**: no published numbers; "light usage"; session limits reset every 5 hours, weekly limits every 7 days; 1 concurrent cloud model. Pro is USD 20 per month.
- **Oracle Always Free**: Ampere A1 up to 2 OCPU and 12 GB memory total; 200 GB block storage; 10 TB egress per month; idle instances may be reclaimed when CPU (95th percentile), network, and memory are all below 20% over 7 days.
- **Vercel Hobby**: non-commercial use only; 100 GB Fast Data Transfer and 10 GB Fast Origin Transfer per month.
- **Cloudflare Turnstile free**: unlimited challenges, 20 widgets, 10 hostnames per widget.

## Decision

1. **AI quota**: per-day judgement cache shared by all players, global daily call budget (configurable), concurrency cap, and `503 AI_UNAVAILABLE` without charging when exhausted. Usage is logged hourly to calibrate the budget.
2. **Oracle reclamation**: run a single A1 instance (1 to 2 OCPU, 6 to 12 GB), keep backups and a scripted rebuild so recovery takes under an hour, and watch for reclamation notices. Converting the account to Pay As You Go (which keeps Always Free resources free but requires a payment method) is **not** done without owner approval; if chosen, a budget alert at USD 1 is mandatory.
3. **Vercel**: no ads, payments, or affiliate links; API responses are small and uncached.
4. **Fallback for AI capacity (not enabled)**: a small open model served by Ollama on the same VM uses the same API shape and stays free, at the cost of latency and VM memory. Considered only if the cloud quota proves insufficient.

## Consequences

- The game stays correct when a provider is down; it only becomes temporarily unavailable.
- Real capacity is unknown until measured; Phase 05 adds usage logging, and Phase 11 sets the final budget.
- Any change that could incur cost needs a new decision and owner approval.
