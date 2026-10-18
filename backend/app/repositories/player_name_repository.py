"""SQLite storage of winners' public names (table `player_names`, migration 0003)."""

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.repositories.database import transaction


class PlayerNameRepository(Protocol):
    def names_for(self, player_hashes: Iterable[str]) -> dict[str, str]: ...
    def set_name(self, player_hash: str, name: str, updated_at: datetime) -> None: ...


class SqlitePlayerNameRepository:
    def __init__(self, path: Path) -> None:
        self._path = path

    def names_for(self, player_hashes: Iterable[str]) -> dict[str, str]:
        hashes = list(dict.fromkeys(player_hashes))
        if not hashes:
            return {}
        with transaction(self._path) as conn:
            # One bound JSON parameter instead of a variable-length IN list.
            rows = conn.execute(
                "SELECT player_hash, name FROM player_names "
                "WHERE player_hash IN (SELECT value FROM json_each(?))",
                (json.dumps(hashes),),
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def set_name(self, player_hash: str, name: str, updated_at: datetime) -> None:
        with transaction(self._path) as conn:
            conn.execute(
                "INSERT INTO player_names (player_hash, name, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(player_hash) DO UPDATE SET name = excluded.name, "
                "updated_at = excluded.updated_at",
                (player_hash, name, updated_at.isoformat()),
            )
