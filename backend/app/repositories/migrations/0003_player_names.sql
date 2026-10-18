-- Public names chosen by winners for the leaderboard (owner request 2026-10-18, OQ-07).
-- Keyed by the keyed player hash; no other personal data is stored.
CREATE TABLE IF NOT EXISTS player_names (
    player_hash TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
