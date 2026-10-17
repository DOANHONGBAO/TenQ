# ADR 0008: Secret word list, keyed selection, and daily pinning

- Status: Proposed
- Date: 2026-10-17

## Context

The repository is public, but the daily word must stay secret until the day ends (BR-12). A naive schedule of 365 words breaks on leap years and repeats predictably. Changing the list must never change a day already in play.

## Options considered

1. **Word list or schedule committed to the repo** — leaks every answer. Rejected.
2. **Pre-generated date-to-word schedule file on the server** — simple, but must be regenerated and has a fixed end date.
3. **`list[day_of_year]`** — fails on day 366 and repeats in the same order every year.
4. **`HMAC(seed, date) mod N`** — unpredictable, but words repeat randomly and some never appear.
5. **Keyed per-cycle permutation**: `day_number = days since epoch`, `cycle = day_number // N`, `position = day_number % N`, `word = shuffle(list, key = HMAC(seed, cycle))[position]`.

## Decision

Option 5, plus pinning:

- Uses an absolute day number, so leap years and any list size work; every word appears once per cycle; each cycle has a new order.
- The shuffle is a deterministic Fisher-Yates driven by an HMAC-SHA256-based stream, so it does not depend on Python's `random` implementation across versions.
- On first use each day the result is stored in SQLite `daily_puzzles` together with the list's SHA-256 and a `selection_version`; afterwards the stored word is authoritative.
- List and seed live only on the VM (`/opt/tenq/secrets`, read-only mount), with an encrypted offline copy held by the owner.

## Consequences

- Nothing in the repository reveals past or future words.
- Editing the list changes only future, unpinned days (list hash differs, recorded per day).
- Seed or list leakage requires rotating the seed and bumping `selection_version` from the next unpinned day.
- Tests use a fake list and a fixed test seed to assert determinism, no repeats within a cycle, and correct leap-day behavior.
