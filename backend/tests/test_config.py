import pytest
from pydantic import ValidationError

from app.core.config import Environment, Settings
from tests.conftest import TEST_KEY_HEX


def make(**env: str) -> Settings:
    env.setdefault("word_selection_key", TEST_KEY_HEX)
    return Settings(_env_file=None, **env)  # type: ignore[arg-type]


def test_env_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TENQ_ENV", raising=False)
    with pytest.raises(ValidationError, match="env"):
        Settings(_env_file=None, word_selection_key=TEST_KEY_HEX)  # type: ignore[call-arg, arg-type]


def test_reads_prefixed_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENQ_ENV", "local")
    monkeypatch.setenv("TENQ_WORD_SELECTION_KEY", TEST_KEY_HEX)
    monkeypatch.setenv("TENQ_CORS_ORIGINS", "http://localhost:5173, http://127.0.0.1:5173")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.env is Environment.LOCAL
    assert settings.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]
    assert settings.selection_key_bytes == bytes.fromhex(TEST_KEY_HEX)


def test_selection_key_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TENQ_WORD_SELECTION_KEY", raising=False)
    with pytest.raises(ValidationError, match="word_selection_key"):
        Settings(_env_file=None, env="local")  # type: ignore[call-arg, arg-type]


@pytest.mark.parametrize("bad", ["", "not-hex-at-all", "abcd" * 8])
def test_selection_key_must_be_32_hex_bytes(bad: str) -> None:
    with pytest.raises(ValidationError, match="TENQ_WORD_SELECTION_KEY"):
        make(env="local", word_selection_key=bad)


def test_selection_key_is_hidden_in_repr_and_dump() -> None:
    settings = make(env="local")
    assert TEST_KEY_HEX not in repr(settings)
    assert TEST_KEY_HEX not in str(settings.model_dump())


def test_production_rejects_http_cors_origin() -> None:
    with pytest.raises(ValidationError, match="https"):
        make(env="production", cors_origins="http://example.com")


def test_production_rejects_debug_logging() -> None:
    with pytest.raises(ValidationError, match="DEBUG"):
        make(env="production", log_level="DEBUG")


def test_production_disables_api_docs() -> None:
    assert make(env="production", cors_origins="https://tenq.example").docs_enabled is False
    assert make(env="local").docs_enabled is True
