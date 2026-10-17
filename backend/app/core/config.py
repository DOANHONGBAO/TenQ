"""Application settings loaded from environment variables.

All configuration comes from `TENQ_*` environment variables (or a local `.env`
file during development). Nothing secret has a default value in code.
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    AliasChoices,
    Field,
    SecretStr,
    ValidationInfo,
    field_validator,
    model_validator,
)
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
        # Empty values in .env (e.g. TENQ_OLLAMA_MODEL=) mean "not set".
        env_ignore_empty=True,
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
    # Signs the anonymous session cookie and derives player hashes. Same format as above.
    session_secret: SecretStr
    redis_url: SecretStr = SecretStr("redis://127.0.0.1:6379/0")
    # A question holds a lease while it is judged; the lease must outlast the judge deadline.
    question_lease_ms: int = Field(default=30_000, ge=1_000, le=120_000)
    judge_timeout_s: float = Field(default=20.0, gt=0, le=60)
    # "mock" runs the full judge pipeline against MockOllamaProvider (no network, no key).
    ai_judge: Literal["mock", "ollama"] = "mock"
    # Accepts TENQ_OLLAMA_API_KEY or the provider's conventional OLLAMA_API_KEY.
    ollama_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("TENQ_OLLAMA_API_KEY", "OLLAMA_API_KEY")
    )
    ollama_base_url: str = Field(default="https://ollama.com", pattern=r"^https?://")
    # No default on purpose: free access differs per account; check with check_ollama_models.
    ollama_model: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._:/-]{1,100}$")
    # Some thinking models need "low"/"false"; empty means the field is not sent.
    ollama_think: str | None = Field(default=None, pattern=r"^(true|false|low|medium|high)$")
    # Thinking models count reasoning tokens here too; too small truncates the JSON.
    ollama_num_predict: int = Field(default=512, ge=16, le=4096)
    ai_daily_budget: int = Field(default=500, ge=0)
    ai_hourly_budget: int = Field(default=80, ge=0)
    ai_max_concurrency: int = Field(default=1, ge=1, le=10)

    @field_validator("word_selection_key", "session_secret")
    @classmethod
    def _check_hex_key(cls, value: SecretStr, info: ValidationInfo) -> SecretStr:
        name = f"TENQ_{str(info.field_name).upper()}"
        try:
            decoded = bytes.fromhex(value.get_secret_value())
        except ValueError:
            raise ValueError(f"{name} must be hex encoded") from None
        if len(decoded) < 32:
            raise ValueError(f"{name} must be at least 32 bytes (64 hex chars)")
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
        if self.judge_timeout_s * 1000 >= self.question_lease_ms:
            raise ValueError("TENQ_QUESTION_LEASE_MS must be longer than TENQ_JUDGE_TIMEOUT_S")
        if self.word_selection_key.get_secret_value() == self.session_secret.get_secret_value():
            raise ValueError("TENQ_SESSION_SECRET must differ from TENQ_WORD_SELECTION_KEY")
        if self.env is Environment.PRODUCTION:
            if self.log_level == "DEBUG":
                raise ValueError("TENQ_LOG_LEVEL=DEBUG is not allowed in production")
            insecure = [o for o in self.cors_origins if not o.startswith("https://")]
            if insecure:
                raise ValueError(f"production CORS origins must use https: {insecure}")
            if self.ai_judge != "ollama":
                raise ValueError("production requires TENQ_AI_JUDGE=ollama (no mock judge)")
        if self.ai_judge == "ollama" and (self.ollama_api_key is None or not self.ollama_model):
            raise ValueError("TENQ_AI_JUDGE=ollama needs TENQ_OLLAMA_API_KEY and TENQ_OLLAMA_MODEL")
        return self

    @property
    def selection_key_bytes(self) -> bytes:
        return bytes.fromhex(self.word_selection_key.get_secret_value())

    @property
    def session_secret_bytes(self) -> bytes:
        return bytes.fromhex(self.session_secret.get_secret_value())

    @property
    def ollama_think_value(self) -> bool | str | None:
        if self.ollama_think in ("true", "false"):
            return self.ollama_think == "true"
        return self.ollama_think

    @property
    def docs_enabled(self) -> bool:
        """Interactive API docs are exposed only outside production."""
        return self.env is not Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    # Values come from the environment; pyright cannot see that `env` is supplied there.
    return Settings()  # type: ignore[call-arg]
