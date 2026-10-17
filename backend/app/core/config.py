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
    # Signs the anonymous session cookie. Same format as above. Rotate by moving the old
    # value to TENQ_SESSION_SECRET_PREVIOUS and setting a new one.
    session_secret: SecretStr
    session_secret_previous: SecretStr | None = None
    # Derives player and daily IP hashes. Never rotated casually: it keys stored game state.
    player_hash_key: SecretStr
    # Shared secret(s) that Vercel adds as X-Origin-Secret (comma-separated: current,previous).
    # Required in production; when set, requests without it are refused (FORBIDDEN_ORIGIN).
    origin_secrets: SecretStr | None = None
    # Cloudflare Turnstile. Local/test: official test secret 1x0000000000000000000000000000000AA.
    turnstile_secret_key: SecretStr
    turnstile_allowed_hostnames: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1"]
    )
    turnstile_expected_action: str = Field(default="session", pattern=r"^[A-Za-z0-9_-]{1,32}$")
    # Anti-abuse limits (fixed windows, counted in Redis).
    max_body_bytes: int = Field(default=4096, ge=512, le=65536)
    session_limit_per_ip_hour: int = Field(default=30, ge=1)
    session_limit_per_device_hour: int = Field(default=10, ge=1)
    question_limit_per_player_minute: int = Field(default=6, ge=1)
    question_limit_per_ip_minute: int = Field(default=40, ge=1)
    read_limit_per_ip_minute: int = Field(default=180, ge=1)
    question_concurrency_per_ip: int = Field(default=4, ge=1)
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

    @field_validator(
        "word_selection_key", "session_secret", "session_secret_previous", "player_hash_key"
    )
    @classmethod
    def _check_hex_key(cls, value: SecretStr | None, info: ValidationInfo) -> SecretStr | None:
        if value is None:
            return None
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
    def _split_lists(cls, data: object) -> object:
        if isinstance(data, dict):
            for name in ("cors_origins", "turnstile_allowed_hostnames"):
                raw = data.get(name)
                if isinstance(raw, str):
                    data[name] = [o.strip() for o in raw.split(",") if o.strip()]
        return data

    @model_validator(mode="after")
    def _check_production_safety(self) -> Self:
        if self.judge_timeout_s * 1000 >= self.question_lease_ms:
            raise ValueError("TENQ_QUESTION_LEASE_MS must be longer than TENQ_JUDGE_TIMEOUT_S")
        keys = [
            self.word_selection_key.get_secret_value(),
            self.session_secret.get_secret_value(),
            self.player_hash_key.get_secret_value(),
        ]
        if len(set(keys)) != len(keys):
            raise ValueError(
                "TENQ_WORD_SELECTION_KEY, TENQ_SESSION_SECRET and TENQ_PLAYER_HASH_KEY must differ"
            )
        for secret in self.origin_secret_list:
            if len(secret) < 32:
                raise ValueError("each TENQ_ORIGIN_SECRETS value must be at least 32 characters")
        if self.env is Environment.PRODUCTION:
            if self.log_level == "DEBUG":
                raise ValueError("TENQ_LOG_LEVEL=DEBUG is not allowed in production")
            insecure = [o for o in self.cors_origins if not o.startswith("https://")]
            if insecure:
                raise ValueError(f"production CORS origins must use https: {insecure}")
            if not self.origin_secret_list:
                raise ValueError("production requires TENQ_ORIGIN_SECRETS (proxy trust)")
            if self.turnstile_uses_test_key:
                raise ValueError("production must not use a Turnstile test secret")
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
    def previous_session_secret_bytes(self) -> tuple[bytes, ...]:
        if self.session_secret_previous is None:
            return ()
        return (bytes.fromhex(self.session_secret_previous.get_secret_value()),)

    @property
    def player_hash_key_bytes(self) -> bytes:
        return bytes.fromhex(self.player_hash_key.get_secret_value())

    @property
    def origin_secret_list(self) -> tuple[str, ...]:
        if self.origin_secrets is None:
            return ()
        raw = self.origin_secrets.get_secret_value()
        return tuple(s.strip() for s in raw.split(",") if s.strip())

    @property
    def turnstile_uses_test_key(self) -> bool:
        # Cloudflare's published dummy secrets: 1x/2x/3x followed by zeros and "AA".
        return self.turnstile_secret_key.get_secret_value().startswith(("1x000", "2x000", "3x000"))

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
