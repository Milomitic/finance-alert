"""Application configuration loaded from environment / .env."""
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./data/app.db"
    secret_key: str = Field(default="")
    session_cookie_name: str = "finance_alert_session"
    session_max_age_days: int = 7
    log_level: str = "INFO"
    admin_username: str = "admin"
    admin_password_hash: str = ""
    public_base_url: str = "http://localhost:8000"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_delivery_mode: str = "digest"  # only "digest" implemented in Fase 2
    digest_hour: int = 8
    digest_minute: int = 0
    scan_hour: int = 23
    scan_minute: int = 30
    # FRED (Federal Reserve Economic Data) API key for the macro
    # calendar. Free, gettable from https://fred.stlouisfed.org —
    # rate-limited at 120 req/min. Empty string disables FRED-driven
    # macro events; the calendar then renders only the hardcoded
    # fallback list in `services/calendar_macros.py`.
    fred_api_key: str = ""
    # Finnhub API key — used as a low-latency fallback source for
    # earnings actuals (epsActual / revenueActual) when yfinance hasn't
    # yet scraped the press release. Free tier from https://finnhub.io
    # gives 60 req/min, ample for our ~1100-stock catalog when we only
    # poll the "imminent earnings" subset (~5-20 stocks per refresh).
    # Empty string disables the Finnhub fallback; yfinance remains the
    # sole source for earnings.
    finnhub_api_key: str = ""

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"


settings = Settings()


def ensure_data_dir() -> None:
    """Make sure ./data and ./data/logs exist."""
    Path("./data").mkdir(parents=True, exist_ok=True)
    Path("./data/logs").mkdir(parents=True, exist_ok=True)
