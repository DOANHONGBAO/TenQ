# Requirements

- Status: **Business requirements approved by owner (2026-10-17).** Items marked *Proposed* in section 4 are design defaults awaiting owner confirmation.
- Change control: edits to section 2 require owner approval.

## 1. Product summary

TenQ.ai is a daily, single-player deduction game against an AI judge. Every day all players worldwide try to identify the same secret English word by asking up to 10 English yes/no questions. No registration or login exists.

## 2. Business requirements (approved)

| ID | Requirement |
|----|-------------|
| BR-01 | Single-player game against an AI judge. |
| BR-02 | Exactly one secret English word per game day, identical for all players worldwide. |
| BR-03 | The game day starts and resets at 00:00 UTC. |
| BR-04 | A player may ask at most 10 questions per game day per anonymous session. |
| BR-05 | Only English yes/no questions are accepted. |
| BR-06 | The AI judge answers exactly one of: `YES`, `NO`, `IRRELEVANT`, `PENALTY`, `WIN`. |
| BR-07 | `YES`, `NO`, `IRRELEVANT`, and `PENALTY` each consume one question. |
| BR-08 | `WIN` ends the game; the winning question counts toward the player's question total. |
| BR-09 | If the AI call fails or its result cannot be validated, no question is consumed. |
| BR-10 | The daily leaderboard ranks by number of questions used (ascending), then by completion time measured from the start of play (ascending). |
| BR-11 | No registration or login. |
| BR-12 | Players cannot obtain the secret word before the game day ends. |

## 3. Non-functional requirements

| ID | Requirement |
|----|-------------|
| NFR-01 | Production-grade: real deployment, monitoring, backups, rollback, CI/CD. |
| NFR-02 | Free tiers only; no paid service enabled without owner approval. |
| NFR-03 | Concurrency-safe: simultaneous requests from one player can never exceed 10 consumed questions or double-charge one submission. |
| NFR-04 | External services (Ollama Cloud, Turnstile, Vercel, Oracle) are treated as unreliable and quota-limited. |
| NFR-05 | Privacy: no accounts, no fingerprinting, no raw IP storage; only data needed to run the game. |
| NFR-06 | Secrets (API keys, signing keys, word list, selection seed) never appear in the repository, logs, or client bundle. |
| NFR-07 | Maintainable, typed, tested code suitable for a public portfolio repository. |
| NFR-08 | Target latency: p95 under 5 s for a question including the AI call; under 300 ms for other endpoints. |

## 4. Interpretations and open questions

The business requirements leave some behavior undefined. The design uses the defaults below. Each one is configurable or isolated in one module so the owner can change it without redesign.

| ID | Topic | Proposed default | Status |
|----|-------|------------------|--------|
| OQ-01 | Meaning of `PENALTY` | The input passed format checks but is not a genuine yes/no question about the word: open questions ("What is it?"), several questions at once, requests to reveal, spell, or encode the word, or instructions aimed at the AI. | Proposed |
| OQ-02 | Meaning of `IRRELEVANT` | A genuine yes/no question that cannot be meaningfully answered for the word (e.g. "Is today Monday?"). | Proposed |
| OQ-03 | Meaning of `WIN` | The question explicitly guesses the secret word (exact word or simple plural, case-insensitive). The model's `WIN` is accepted only if the server confirms the word appears in the question; otherwise the result is treated as unvalidated (BR-09). | Proposed |
| OQ-04 | Format rejection | Inputs failing deterministic checks (length 3 to 150 characters, printable ASCII, must end with `?`) are rejected with `INVALID_QUESTION` and do **not** consume a question. Non-English text that passes these checks is judged by the AI and normally yields `PENALTY`. | Proposed |
| OQ-05 | Repeated question | Asking the same normalized question twice in one game is rejected with `DUPLICATE_QUESTION` and does not consume a question. | Proposed |
| OQ-06 | "Start of play" | The server time when the player's first question of the day is submitted. | Proposed |
| OQ-07 | Leaderboard entries | Only `WIN` games appear. Display names are auto-generated from the anonymous id (e.g. `Player-7F3A`); no free-text nicknames in v1. | Proposed |
| OQ-08 | Reveal after the day | The word for a past date can be retrieved after that day ends (UTC). Losing players do not see the word earlier. | Proposed |
| OQ-09 | Letter/length questions | Allowed, since they are yes/no questions ("Does it start with S?"). | Proposed |
| OQ-10 | Session lifetime | Anonymous session cookie lasts 365 days; clearing cookies creates a new session (accepted limitation, see threat model T-07). | Proposed |

## 5. Out of scope (v1)

Accounts, social login, multiplayer, hints, streaks across devices, custom nicknames, multiple languages, mobile apps, monetization (also required by Vercel Hobby's non-commercial terms).

## 6. Traceability

| Requirement | Design | Decision | Verified in phase |
|-------------|--------|----------|-------------------|
| BR-01, BR-06 | architecture.md 4.3 | ADR 0010 | 05 |
| BR-02, BR-12 | data-model.md 3, architecture.md 4.4 | ADR 0008 | 03, 07 |
| BR-03 | architecture.md 4.4 | ADR 0004 | 03, 04 |
| BR-04, NFR-03 | architecture.md 5 | ADR 0003, 0005 | 04 |
| BR-05, OQ-04 | api-contract.md 4.3 | ADR 0010 | 03, 05 |
| BR-07, BR-08, BR-09 | architecture.md 4.2, 5 | ADR 0003, 0010 | 04, 05 |
| BR-10 | data-model.md 2.4 | ADR 0009 | 07 |
| BR-11, NFR-05 | architecture.md 4.5 | ADR 0006 | 06 |
| NFR-02, NFR-04 | architecture.md 7, 8 | ADR 0007, 0011 | 05, 10 |
| NFR-06 | security-threat-model.md | ADR 0008 | 02, 10 |
