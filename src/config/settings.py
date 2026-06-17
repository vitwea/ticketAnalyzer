"""
config/settings.py

Centralized project configuration.

Loads all settings from environment variables (typically defined in a .env file)
to avoid hardcoded credentials, paths, or secrets inside the codebase.

Usage:
    from config.settings import settings

    print(settings.gmail_credentials_path)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env file into environment variables (if present)
load_dotenv()


def _require_env(name: str, default: str | None = None) -> str:
    """
    Retrieve an environment variable or raise a clear error if it is missing.

    Args:
        name: Name of the environment variable.
        default: Optional default value if the variable is not set.

    Returns:
        The value of the environment variable.

    Raises:
        RuntimeError: If the variable is required and not provided.
    """
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(
            f"Missing required environment variable '{name}'. "
            f"Copy '.env.example' to '.env' and fill in the required values."
        )
    return value


@dataclass(frozen=True)
class Settings:
    """
    Container for all project configuration values.

    This object is immutable (frozen=True) to ensure configuration
    remains consistent throughout the application lifecycle.
    """

    # Google OAuth / Gmail
    google_client_id: str
    google_client_secret: str
    google_project_id: str
    gmail_credentials_path: Path
    gmail_token_path: Path
    gmail_scopes: tuple[str, ...]

    # AI / LLMs
    anthropic_api_key: str | None

    # Database
    database_url: str

    # Logging
    log_level: str
    log_dir: Path


def load_settings() -> Settings:
    """
    Build the Settings object from environment variables.

    Returns:
        A fully populated Settings instance.
    """
    return Settings(
        google_client_id=_require_env("GOOGLE_CLIENT_ID"),
        google_client_secret=_require_env("GOOGLE_CLIENT_SECRET"),
        google_project_id=_require_env("GOOGLE_PROJECT_ID"),
        gmail_credentials_path=Path(os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")),
        gmail_token_path=Path(os.getenv("GOOGLE_TOKEN_PATH", "token.json")),
        gmail_scopes=("https://www.googleapis.com/auth/gmail.readonly",),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///tickets.db"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_dir=Path(os.getenv("LOG_DIR", "logs")),
    )


# Global settings instance reused across the entire project
settings = load_settings()
