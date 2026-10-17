-- Progressive hints per word (JSON array of 4 strings, hardest first). Secret material.
ALTER TABLE words ADD COLUMN hints_json TEXT NOT NULL DEFAULT '[]';
