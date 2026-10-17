# Data Model

- Status: Proposed in Phase 01. Redis holds live, per-day state; SQLite holds durable records ([ADR 0009](decisions/0009-redis-durability-and-sqlite-results.md)).

## 1. Identifiers

| Name | Definition | Stored where |
|------|------------|--------------|
| `player_id` | 128 random bits, base64url | Only inside the signed cookie |
| `player_hash` | `hex(HMAC-SHA256(TENQ_PLAYER_HASH_KEY, player_id))[:32]` | Redis keys, SQLite |
| `display_name` | `"Player-" + upper(player_hash[:6])` | Derived; stored in results for history |
| `game_date` | UTC date `YYYY-MM-DD` | Keys and rows |
| `qhash` | `hex(SHA-256(normalized_question))[:32]` | Duplicate detection |
| `judge_key` | `hex(SHA-256(game_date + "\n" + normalized_question + "\n" + prompt_version + "\n" + model))` | Judgement cache |
| `ip_hash` | `hex(HMAC-SHA256(TENQ_IP_HASH_KEY, game_date + "\n" + ip))[:32]` | Rate limit keys only (daily-rotating) |

Raw player ids and raw IPs never appear in Redis, SQLite, or logs.

## 2. Redis

Prefix `tenq:v1:`. All per-day keys expire at **00:00 UTC two days after `game_date`** (`EXPIREAT`), giving a full day of grace for in-flight requests, leaderboard reads, and the SQLite retry queue. Fixed 24-hour TTLs are not used ([ADR 0004](decisions/0004-utc-game-day-and-expiration.md)).

### 2.1 Keys

| Key | Type | Content | Expiry |
|-----|------|---------|--------|
| `game:{date}:{player_hash}` | HASH | `status` (`not_started`/`in_progress`/`won`/`lost`), `used`, `started_at_ms`, `finished_at_ms`, `lb_member`, `lease_token`, `lease_until_ms`, `lease_qhash`, `lease_started_ms` | day + 2 |
| `hist:{date}:{player_hash}` | LIST | JSON `{"n":1,"q":"Is it alive?","a":"NO","t":1792...}` per committed question | day + 2 |
| `qset:{date}:{player_hash}` | SET | `qhash` of committed questions | day + 2 |
| `idem:{date}:{player_hash}:{key}` | HASH | `state` (`pending`/`done`), `body` (SHA-256 of the question), `token` (while pending), `number` and `answer` (when done) | day + 2 |
| `judge:{date}:{judge_key}` | STRING | One validated label; `judge_key = sha256(date, puzzle_id, normalized question, prompt_version, model)` | day + 2 |
| `judgelock:{date}:{judge_key}` | STRING | Stampede lock token | 25 s |
| `lb:{date}` | ZSET | member `{finished_at_ms:013d}:{player_hash}`, score `questions * 1e9 + duration_ms` | day + 2 |
| `rl:{scope}:{subject}:{window}` | STRING | Fixed-window counter | window length |
| `aibudget:day:{date}` | STRING | AI HTTP attempts made today (retries included) | day + 2 |
| `aibudget:hour:{date}T{HH}` | STRING | AI HTTP attempts in that UTC hour | 2 h |
| `results:retry` | LIST | JSON results whose SQLite write failed | none (drained by worker) |

The secret word is **not** stored in Redis; the API holds it in memory, loaded from SQLite.

### 2.2 Script contracts

All scripts receive the current server time as an argument (injectable clock, deterministic tests).

`reserve(game, hist, qset, idem, rl_player, rl_ip; now_ms, lease_ms, lease_token, body_hash, qhash, max_questions, limits...)`

1. If `idem` exists: different `body_hash` -> `IDEMPOTENCY_KEY_REUSED`; `done` -> `REPLAY` with stored `number` and `answer`; `pending` that owns the live lease -> `QUESTION_IN_PROGRESS`; `pending` left by a crashed request (lease gone or expired) -> deleted and processing continues.
2. Rate limit counters: Phase 06.
3. If `game` missing -> treat as `not_started`, `used=0` (written together with the lease in step 7).
4. `status` `won` -> `GAME_FINISHED`; `lost` or `used >= max` -> `ATTEMPT_LIMIT_REACHED`.
5. `lease_until_ms > now_ms` -> `QUESTION_IN_PROGRESS`.
6. `SISMEMBER qset qhash` -> `DUPLICATE_QUESTION`.
7. Set `lease_token`, `lease_until_ms = now_ms + lease_ms`, `lease_qhash`, `lease_started_ms`; write `idem` as `pending` with the token. Return `RESERVED`.

`commit(game, hist, qset, idem, lb; now_ms, lease_token, answer, entry_json, response_json, max_questions)`

1. `lease_token` mismatch or lease expired -> `STALE_LEASE` (nothing changes; caller returns `AI_UNAVAILABLE`).
2. `used += 1`; on the first charge set `started_at_ms = lease_started_ms`; `RPUSH hist`; `SADD qset lease_qhash`.
3. `answer == WIN` -> `status=won`, `finished_at_ms`, `ZADD lb NX` with member `{finished_at_ms:013d}:{player_hash}` (stored as `lb_member`). Else if `used == max` -> `status=lost`, `finished_at_ms`. Else `status=in_progress`.
4. Clear lease fields; set `idem` to `done` with `number` and `answer`. Return `used` and `status`.

`release(game, idem; lease_token)`

1. If `lease_token` matches: clear lease fields and `DEL idem`. Otherwise no-op.

Scripts are loaded once with `SCRIPT LOAD` and called with `EVALSHA` (redis-py `register_script` handles reloads after a Redis restart).

### 2.3 Memory estimate

About 2 KB per active player per day (hash, 10 history entries, set, idempotency records). 10,000 players a day is about 20 MB per day, about 40 MB with the two-day retention. Redis runs with `maxmemory 256mb` and `maxmemory-policy noeviction`: under memory pressure writes fail loudly (`503`) instead of silently evicting game state.

### 2.4 Leaderboard score

`score = questions * 1_000_000_000 + duration_ms`. `duration_ms` stays far below 1e9, so questions always dominate. The maximum score (about 1.1e10) is far below 2^53, so the float score is exact. Redis orders equal scores by member, byte by byte; because the member starts with the zero-padded `finished_at_ms`, ties go to whoever finished first, then to the player hash, so the ranking is total and deterministic. `ZRANGE lb:{date} 0 N-1 WITHSCORES` returns the ranking; `ZRANK` returns the caller's rank.

## 3. SQLite

File `/data/tenq.sqlite3` on a named volume. Pragmas: `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`, `busy_timeout=5000`. Migrations are numbered SQL files applied in order and recorded in `schema_migrations`.

```sql
CREATE TABLE schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL
);

-- Contains the secret word: database file and backups are protected accordingly.
CREATE TABLE daily_puzzles (
    game_date          TEXT PRIMARY KEY CHECK (game_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    word               TEXT NOT NULL CHECK (length(word) BETWEEN 2 AND 32),
    word_list_sha256   TEXT NOT NULL,
    selection_version  INTEGER NOT NULL,
    pinned_at          TEXT NOT NULL
);

-- Curated vocabulary (secret). Seeded from the private JSON file; exactly 365 rows.
CREATE TABLE words (
    word            TEXT PRIMARY KEY CHECK (length(word) BETWEEN 2 AND 32 AND word NOT GLOB '*[^a-z]*'),
    part_of_speech  TEXT NOT NULL CHECK (part_of_speech IN ('noun', 'verb', 'adjective', 'adverb')),
    category        TEXT NOT NULL,
    definition      TEXT NOT NULL,
    attributes_json TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE game_results (
    id              INTEGER PRIMARY KEY,
    game_date       TEXT NOT NULL REFERENCES daily_puzzles (game_date),
    player_hash     TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    outcome         TEXT NOT NULL CHECK (outcome IN ('won', 'lost')),
    questions_used  INTEGER NOT NULL CHECK (questions_used BETWEEN 1 AND 10),
    started_at      TEXT NOT NULL,
    finished_at     TEXT NOT NULL,
    duration_ms     INTEGER NOT NULL CHECK (duration_ms >= 0),
    UNIQUE (game_date, player_hash)
);

CREATE INDEX idx_results_leaderboard
    ON game_results (game_date, outcome, questions_used, duration_ms, finished_at);
```

- Pinning: `INSERT OR IGNORE INTO daily_puzzles ...` then `SELECT word ...`. The primary key makes concurrent pinning safe.
- Results: `INSERT OR IGNORE` makes the write idempotent, so the retry worker can replay safely.
- Historical leaderboard: `WHERE game_date = ? AND outcome = 'won' ORDER BY questions_used, duration_ms, finished_at LIMIT ?`.
- Access is synchronous `sqlite3` run in a thread pool; writes happen only at game completion and daily pinning, so contention is negligible.

## 4. Secret files (outside the repository)

| File | Format | Notes |
|------|--------|-------|
| `/opt/tenq/secrets/words.json` (local: `backend/secrets/words.json`) | JSON array of `{word, part_of_speech, category, definition, attributes[]}`; `word` matches `[a-z]{2,32}` | Validated by `app.scripts.seed_words` (exactly 365, unique, definition must not contain the word) and loaded into `words`; the SHA-256 of the sorted word list is recorded on each pinned puzzle |
| `TENQ_WORD_SELECTION_KEY` (VM `.env`) | 32 random bytes, hex | Used only for HMAC in word selection (ADR 0012) |

The repository ships no words: `seed_words --dev` generates obviously fake `zzdev...` entries for development and tests.
