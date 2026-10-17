import pytest
from pydantic import ValidationError

from app.core.config import Environment, Settings


def make(**env: str) -> Settings:
    return Settings(_env_file=None, **env)  # type: ignore[arg-type]


def test_env_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TENQ_ENV", raising=False)
    with pytest.raises(ValidationError, match="env"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_reads_prefixed_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENQ_ENV", "local")
    monkeypatch.setenv("TENQ_CORS_ORIGINS", "http://localhost:5173, http://127.0.0.1:5173")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.env is Environment.LOCAL
    assert settings.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_production_rejects_http_cors_origin() -> None:
    with pytest.raises(ValidationError, match="https"):
        make(env="production", cors_origins="http://example.com")


def test_production_rejects_debug_logging() -> None:
    with pytest.raises(ValidationError, match="DEBUG"):
        make(env="production", log_level="DEBUG")


def test_production_disables_api_docs() -> None:
    assert make(env="production", cors_origins="https://tenq.example").docs_enabled is False
    assert make(env="local").docs_enabled is True
