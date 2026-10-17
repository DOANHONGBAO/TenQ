# Product Specification

> Status: **Awaiting the approved specification from the project owner.**
> Nothing in this file may be treated as a requirement until the owner replaces this placeholder. Claude must not fill gaps with assumptions.

## Known from project instructions

- Daily AI 10-questions deduction game.
- Zero-login, single-player.
- One secret per game day; players ask up to 10 questions answered by an AI judge.

## Sections expected in the approved specification

1. Game rules (game day boundary and timezone, what a question is, final guesses and whether they consume attempts, win/lose conditions)
2. AI judge behavior (allowed answer set, disallowed question types such as letter/length side channels, language support)
3. Failure policy (AI provider errors, timeouts, quota exhaustion, attempt refunds)
4. Leaderboard (ranking, tie-break, display names, retention)
5. Identity and abuse prevention (cookie lifetime, rate limits, Turnstile placement)
6. Content (secret word source, languages, moderation)
7. Non-functional requirements (latency targets, availability, privacy, data retention)
8. Out of scope
