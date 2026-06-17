import logging
from pathlib import Path

import src.config.logger as logger_module
import src.config.settings as settings_module
from src.config.logger import get_logger
from src.config.settings import load_settings


def _make_settings(base, **overrides):
    """Helper to build a new Settings instance overriding specific fields."""
    data = {f: getattr(base, f) for f in base.__dataclass_fields__}
    data.update(overrides)
    return type(base)(**data)


def test_get_logger_returns_logger_instance(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"

    monkeypatch.setattr(logger_module, "_CONFIGURED", False)
    monkeypatch.setattr(
        settings_module, "settings", _make_settings(settings_module.settings, log_dir=log_dir)
    )
    monkeypatch.setattr(
        logger_module, "settings", settings_module.settings
    )

    logger = get_logger("test_logger")

    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_logger"


def test_logging_creates_log_directory(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"

    monkeypatch.setattr(logger_module, "_CONFIGURED", False)
    new_settings = _make_settings(settings_module.settings, log_dir=log_dir)
    monkeypatch.setattr(settings_module, "settings", new_settings)
    monkeypatch.setattr(logger_module, "settings", new_settings)

    logger = get_logger("test_logger")
    logger.info("Test message")

    assert log_dir.exists()
    log_files = list(log_dir.glob("app.log"))
    assert len(log_files) == 1