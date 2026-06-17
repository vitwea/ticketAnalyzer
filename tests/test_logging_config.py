import logging
from pathlib import Path

from src.config.logger import get_logger
from src.config.settings import settings


def test_get_logger_returns_logger_instance(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("LOG_LEVEL", "INFO")

    logger = get_logger("test_logger")

    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_logger"


def test_logging_creates_log_directory(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("LOG_DIR", str(log_dir))
    monkeypatch.setenv("LOG_LEVEL", "INFO")

    logger = get_logger("test_logger")
    logger.info("Test message")

    assert log_dir.exists()
    log_files = list(log_dir.glob("app.log"))
    assert len(log_files) == 1
