"""Application settings loaded from environment variables.

All configuration comes from `TENQ_*` environment variables (or a local `.env`
file during development). Nothing secret has a default value in code.
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TENQ_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required on purpose: the app must never guess which environment it runs in.
    env: Environment
    app_name: str = "TenQ.ai API"
    log_level: str = Field(default="INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR)$")
    # Comma-separated list in the environment, e.g. "http://localhost:5173".
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    # SQLite file holding the vocabulary and pinned daily puzzles (secret material).
    database_path: Path = Path("data/tenq.sqlite3")
    # 32 random bytes as 64 hex characters. Drives the secret word schedule (ADR 0012).
    # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    word_selection_key: SecretStr

    @field_validator("word_selection_key")
    @classmethod
    def _check_selection_key(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        try:
            decoded = bytes.fromhex(raw)
        except ValueError:
            raise ValueError("TENQ_WORD_SELECTION_KEY must be hex encoded") from None
        if len(decoded) < 32:
            raise ValueError("TENQ_WORD_SELECTION_KEY must be at least 32 bytes (64 hex chars)")
        return value

    @model_validator(mode="before")
    @classmethod
    def _split_cors_origins(cls, data: object) -> object:
        if isinstance(data, dict):
            raw = data.get("cors_origins")
            if isinstance(raw, str):
                data["cors_origins"] = [o.strip() for o in raw.split(",") if o.strip()]
        return data

    @model_validator(mode="after")
    def _check_production_safety(self) -> Self:
        if self.env is Environment.PRODUCTION:
            if self.log_level == "DEBUG":
                raise ValueError("TENQ_LOG_LEVEL=DEBUG is not allowed in production")
            insecure = [o for o in self.cors_origins if not o.startswith("https://")]
            if insecure:
                raise ValueError(f"production CORS origins must use https: {insecure}")
        return self

    @property
    def selection_key_bytes(self) -> bytes:
        return bytes.fromhex(self.word_selection_key.get_secret_value())

    @property
    def docs_enabled(self) -> bool:
        """Interactive API docs are exposed only outside production."""
        return self.env is not Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    # Values come from the environment; pyright cannot see that `env` is supplied there.
    return Settings()  # type: ignore[call-arg]
