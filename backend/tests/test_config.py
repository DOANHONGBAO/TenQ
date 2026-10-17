import pytest
from pydantic import ValidationError

from app.core.config import Environment, Settings
from tests.conftest import TEST_KEY_HEX, TEST_SESSION_HEX


def make(**env: str) -> Settings:
    env.setdefault("word_selection_key", TEST_KEY_HEX)
    env.setdefault("session_secret", TEST_SESSION_HEX)
    return Settings(_env_file=None, **env)  # type: ignore[arg-type]


def test_env_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TENQ_ENV", raising=False)
    with pytest.raises(ValidationError, match="env"):
        Settings(_env_file=None, word_selection_key=TEST_KEY_HEX, session_secret=TEST_SESSION_HEX)  # type: ignore[call-arg, arg-type]


def test_reads_prefixed_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENQ_ENV", "local")
    monkeypatch.setenv("TENQ_WORD_SELECTION_KEY", TEST_KEY_HEX)
    monkeypatch.setenv("TENQ_SESSION_SECRET", TEST_SESSION_HEX)
    monkeypatch.setenv("TENQ_CORS_ORIGINS", "http://localhost:5173, http://127.0.0.1:5173")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.env is Environment.LOCAL
    assert settings.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]
    assert settings.selection_key_bytes == bytes.fromhex(TEST_KEY_HEX)


def test_selection_key_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TENQ_WORD_SELECTION_KEY", raising=False)
    with pytest.raises(ValidationError, match="word_selection_key"):
        Settings(_env_file=None, env="local", session_secret=TEST_SESSION_HEX)  # type: ignore[call-arg, arg-type]


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


def test_api_docs_only_outside_production() -> None:
    assert make(env="local").docs_enabled is True
    assert make(env="test").docs_enabled is True


def test_session_secret_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TENQ_SESSION_SECRET", raising=False)
    with pytest.raises(ValidationError, match="session_secret"):
        Settings(_env_file=None, env="local", word_selection_key=TEST_KEY_HEX)  # type: ignore[call-arg, arg-type]


def test_secrets_must_differ() -> None:
    with pytest.raises(ValidationError, match="must differ"):
        make(env="local", session_secret=TEST_KEY_HEX)


def test_lease_must_outlast_judge_timeout() -> None:
    with pytest.raises(ValidationError, match="LEASE"):
        make(env="local", question_lease_ms="5000", judge_timeout_s="5")


def test_production_rejects_mock_judge() -> None:
    with pytest.raises(ValidationError, match="no mock judge"):
        make(env="production", cors_origins="https://tenq.example")


def test_ollama_judge_needs_key_and_model() -> None:
    with pytest.raises(ValidationError, match="TENQ_OLLAMA_API_KEY and TENQ_OLLAMA_MODEL"):
        make(env="local", ai_judge="ollama", ollama_model="some-model")
    settings = make(
        env="production",
        cors_origins="https://tenq.example",
        ai_judge="ollama",
        ollama_api_key="test-key-not-real",
        ollama_model="some-model",
    )
    assert "test-key-not-real" not in repr(settings)


def test_ollama_api_key_accepts_provider_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "from-provider-variable")
    settings = make(env="local")
    assert settings.ollama_api_key is not None
    assert settings.ollama_api_key.get_secret_value() == "from-provider-variable"


def test_redis_url_is_hidden_in_repr() -> None:
    settings = make(env="local", redis_url="redis://:hunter2hunter2@db:6379/0")
    assert "hunter2hunter2" not in repr(settings)
