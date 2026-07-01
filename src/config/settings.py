"""
config/settings.py

Centralized project configuration.

Loads all settings from environment variables (typically defined in a .env file)
to avoid hardcoded credentials, paths, or secrets inside the codebase.

Usage:
    from config.settings import settings
    print(settings.database_url)
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
    Immutable (frozen=True) to ensure consistency.
    """

    # --- Google OAuth / Gmail ---
    google_client_id: str
    google_client_secret: str
    google_project_id: str
    gmail_credentials_path: Path
    gmail_token_path: Path
    gmail_scopes: tuple[str, ...]

    # --- AI / LLMs ---
    gemini_api_key: str | None

    # --- Database (PostgreSQL) ---
    db_name: str
    db_user: str
    db_password: str
    db_host: str
    db_port: int

    # --- Logging ---
    log_level: str
    log_dir: Path

    # --- Dynamic SQLAlchemy URL ---
    @property
    def database_url(self) -> str:
        """
        Build the SQLAlchemy database URL dynamically.
        Falls back to SQLite if PostgreSQL variables are missing.
        """
        if self.db_name and self.db_user:
            return (
                f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )

        # Fallback for tests or missing env vars
        return "sqlite:///tickets.db"


def load_settings() -> Settings:
    """
    Build the Settings object from environment variables.
    """
    return Settings(
        # Gmail OAuth
        google_client_id=_require_env("GOOGLE_CLIENT_ID"),
        google_client_secret=_require_env("GOOGLE_CLIENT_SECRET"),
        google_project_id=_require_env("GOOGLE_PROJECT_ID"),
        gmail_credentials_path=Path(os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")),
        gmail_token_path=Path(os.getenv("GOOGLE_TOKEN_PATH", "token.json")),
        gmail_scopes=("https://www.googleapis.com/auth/gmail.readonly",),

        # AI
        gemini_api_key=os.getenv("GEMINI_API_KEY"),

        # PostgreSQL
        db_name=os.getenv("DB_NAME", ""),
        db_user=os.getenv("DB_USER", ""),
        db_password=os.getenv("DB_PASSWORD", ""),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", 5432)),

        # Logging
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_dir=Path(os.getenv("LOG_DIR", "logs")),
    )


# Global settings instance reused across the entire project
settings = load_settings()
