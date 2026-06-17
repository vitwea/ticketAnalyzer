import os
import pytest
from pathlib import Path

from src.config.settings import Settings, load_settings, _require_env


def test_require_env_raises_on_missing_variable(monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)

    with pytest.raises(RuntimeError) as exc:
        _require_env("MISSING_VAR")

    assert "Missing required environment variable 'MISSING_VAR'" in str(exc.value)


def test_require_env_returns_default_when_provided(monkeypatch):
    monkeypatch.delenv("OPTIONAL_VAR", raising=False)

    value = _require_env("OPTIONAL_VAR", default="fallback")
    assert value == "fallback"


def test_load_settings_uses_defaults_for_optional_fields(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dummy_client_id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "dummy_client_secret")
    monkeypatch.setenv("GOOGLE_PROJECT_ID", "dummy_project_id")

    monkeypatch.delenv("GOOGLE_CREDENTIALS_PATH", raising=False)
    monkeypatch.delenv("GOOGLE_TOKEN_PATH", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOG_DIR", raising=False)

    settings = load_settings()

    assert isinstance(settings, Settings)
    assert settings.gmail_credentials_path == Path("credentials.json")
    assert settings.gmail_token_path == Path("token.json")
    assert settings.database_url == "sqlite:///tickets.db"
    assert settings.log_level == "INFO"
    assert settings.log_dir == Path("logs")