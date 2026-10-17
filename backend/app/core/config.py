"""Application settings loaded from environment variables.

All configuration comes from `TENQ_*` environment variables (or a local `.env`
file during development). Nothing secret has a default value in code.
"""

from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Self

from pydantic import Field, model_validator
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
    def docs_enabled(self) -> bool:
        """Interactive API docs are exposed only outside production."""
        return self.env is not Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    # Values come from the environment; pyright cannot see that `env` is supplied there.
    return Settings()  # type: ignore[call-arg]
