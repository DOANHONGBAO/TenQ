-- Vocabulary of candidate secret words. Contains secret material: the database file and its
-- backups must be protected like the selection key.
CREATE TABLE words (
    word            TEXT PRIMARY KEY CHECK (length(word) BETWEEN 2 AND 32 AND word NOT GLOB '*[^a-z]*'),
    part_of_speech  TEXT NOT NULL CHECK (part_of_speech IN ('noun', 'verb', 'adjective', 'adverb')),
    category        TEXT NOT NULL,
    definition      TEXT NOT NULL,
    attributes_json TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE daily_puzzles (
    game_date          TEXT PRIMARY KEY CHECK (game_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    word               TEXT NOT NULL CHECK (length(word) BETWEEN 2 AND 32),
    word_list_sha256   TEXT NOT NULL,
    selection_version  INTEGER NOT NULL,
    pinned_at          TEXT NOT NULL
);
