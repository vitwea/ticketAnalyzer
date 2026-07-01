"""
config/settings.py

Centralized project configuration loaded from environment variables (.env).

Usage:
    from src.config.settings import settings
    print(settings.database_url)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _require_env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(
            f"Missing required environment variable '{name}'. "
            f"Copy '.env.example' to '.env' and fill in the required values."
        )
    return value


_DEFAULT_GMAIL_QUERY = (
    "from:mercadona "
    "OR subject:(lidl ticket) "
    "OR from:dia.es "
    "OR subject:(alcampo ticket)"
)


@dataclass(frozen=True)
class Settings:
    # --- Google OAuth / Gmail ---
    google_client_id: str
    google_client_secret: str
    google_project_id: str
    gmail_credentials_path: Path
    gmail_token_path: Path
    gmail_scopes: tuple[str, ...]

    # --- Gmail pipeline ---
    # Override GMAIL_SEARCH_QUERY in .env to add supermarkets without touching code.
    gmail_search_query: str

    # --- AI / OCR  (Google Gemini) ---
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

    @property
    def database_url(self) -> str:
        if self.db_name and self.db_user:
            return (
                f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        return "sqlite:///tickets.db"


def load_settings() -> Settings:
    return Settings(
        google_client_id=_require_env("GOOGLE_CLIENT_ID"),
        google_client_secret=_require_env("GOOGLE_CLIENT_SECRET"),
        google_project_id=_require_env("GOOGLE_PROJECT_ID"),
        gmail_credentials_path=Path(os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")),
        gmail_token_path=Path(os.getenv("GOOGLE_TOKEN_PATH", "token.json")),
        gmail_scopes=("https://www.googleapis.com/auth/gmail.readonly",),

        gmail_search_query=os.getenv("GMAIL_SEARCH_QUERY", _DEFAULT_GMAIL_QUERY),

        gemini_api_key=os.getenv("GEMINI_API_KEY"),

        db_name=os.getenv("DB_NAME", ""),
        db_user=os.getenv("DB_USER", ""),
        db_password=os.getenv("DB_PASSWORD", ""),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", 5432)),

        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_dir=Path(os.getenv("LOG_DIR", "logs")),
    )


settings = load_settings()