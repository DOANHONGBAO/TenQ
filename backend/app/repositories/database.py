"""SQLite connection factory and a minimal forward-only migration runner."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def connect(path: Path) -> sqlite3.Connection:
    """Open a connection with the pragmas from docs/data-model.md section 3."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def transaction(path: Path) -> Iterator[sqlite3.Connection]:
    """One connection, one transaction: commit on success, roll back on error, always close."""
    conn = connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def apply_migrations(path: Path) -> list[int]:
    """Apply pending `NNNN_*.sql` files in order. Returns the versions applied now."""
    applied_now: list[int] = []
    with transaction(path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        done = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    for script in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        version = int(script.name[:4])
        if version in done:
            continue
        applied_at = datetime.now(UTC).isoformat()
        sql = script.read_text(encoding="utf-8")
        conn = connect(path)
        try:
            # The script and its bookkeeping row commit together or not at all.
            conn.executescript(
                f"BEGIN;\n{sql}\nINSERT INTO schema_migrations (version, applied_at) "
                f"VALUES ({version}, '{applied_at}');\nCOMMIT;"
            )
        except sqlite3.Error:
            conn.rollback()
            raise
        finally:
            conn.close()
        applied_now.append(version)
    return applied_now
