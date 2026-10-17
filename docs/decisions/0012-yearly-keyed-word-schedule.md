# ADR 0012: Keyed yearly word schedule with an explicit leap-day rule

- Status: Proposed
- Date: 2026-10-17
- Supersedes: the selection formula in [ADR 0008](0008-secret-word-management.md) (`cycle = day_number // N`). ADR 0008's pinning, list fingerprint, and secret storage remain in force.

## Context

The owner's Phase 03 brief asks for exactly 365 curated words stored in SQLite with metadata for the AI judge, a deterministic **yearly** permutation driven by HMAC-SHA256 with a server-side key, and an explicit, documented leap-year behavior. A 366-day year cannot use 365 words without one repeat. The repository is public, so the code must not let anyone derive the schedule.

## Options considered

1. **ADR 0008 cycles** (`cycle = days since epoch // 365`): no repeats in any 365-day window, but cycles drift away from calendar years, which the owner asked for.
2. **`HMAC(key, date) mod 365`**: unpredictable, but about 37% of words never appear in a year and repeats cluster.
3. **Keyed yearly permutation, leap day reuses an early-year word**: every word once per common year; in leap years exactly one planned repeat, far from the original.
4. **Keyed yearly permutation, leap day reuses the previous year's word for the same slot**: harder to reason about and can collide with nearby days.

## Decision

Option 3.

- `perm_Y` = Fisher-Yates shuffle of `range(365)` driven by an HMAC-SHA256 counter stream: `HMAC(key, "tenq:v1:perm:{Y}:{counter}")`, 64-bit draws, rejection sampling for uniformity. Python's `random` is not used, so results do not change between Python versions.
- Day-of-year `d` in 1..365 uses `words[perm_Y[d - 1]]`, where `words` is the vocabulary sorted alphabetically.
- **Leap day rule**: day 366 (31 December of a leap year) uses `perm_Y[s]` with `s = 2 + HMAC-derived value in [0, 180]`, i.e. the word of a day between 3 January and 2 July. The only repeat in a leap year is therefore at least 183 days after its first use, and its position is unpredictable without the key.
- **Year boundary rule**: if `perm_Y[0]` equals the last word of year `Y - 1`, positions 0 and 1 are swapped, so 31 December and 1 January never share a word. The swap never touches positions 2 and later, and `s >= 2`, so the previous year's last word is computed from its raw permutation without recursion.
- Key: `TENQ_WORD_SELECTION_KEY`, 32 random bytes as hex, required at startup in every environment. It is never committed, logged, or returned.
- The chosen word is pinned per date in SQLite on first use (ADR 0008), so restarts, list edits, and future algorithm changes never alter a day that has started. `selection_version = 1`.

## Consequences

- No word repeats within a common year; one planned, far-apart repeat in leap years; no repeat on consecutive days, including across years. All three are covered by unit tests over 2024 to 2040.
- Knowing the code, the date, and even the word list does not reveal the schedule without the key.
- The word list must contain exactly 365 words; seeding rejects anything else.
- Key leak reveals every future word: rotate the key and bump `selection_version`; pinned days keep their words.
- Across years the same word may reappear after a short gap (for example late December and early January). This is accepted: players face a fresh, unknown order each year.
