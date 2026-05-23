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
    # Signal engine: minimum confidence (0-100) for a detected signal to
    # become an alert. Below this the signal is computed but not surfaced.
    signal_min_confidence: int = 60
    # Signal engine recency guard: a detected signal is only surfaced if its
    # signal_date is within this many calendar days of the latest OHLCV bar.
    # Stops the first scan after a deploy/backfill from flooding the feed with
    # months-old setups (the ~260-bar window contains a year of history).
    signal_max_age_days: int = 7
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
    # Marketaux API key — used as a fallback news source when yfinance returns
    # 0 headlines for a ticker. Free tier from https://www.marketaux.com gives
    # 100 req/day, sufficient for a single-user local-first context.
    # Empty string disables the fallback; yfinance remains the sole source.
    marketaux_api_key: str = ""
    # Twelve Data API key — TIER-3 fallback for EPS actuals, behind
    # yfinance (primary) and Finnhub (fallback #1). A SEPARATE provider
    # from Finnhub, so a Finnhub rate-limit/outage no longer leaves a
    # freshly-released EPS actual unfilled. Free tier from
    # https://twelvedata.com gives 800 req/day, 8 req/min — ample since
    # only the narrow "actual just lagging" subset hits it. Note: the
    # free /earnings endpoint is EPS-only (no revenue). Empty string
    # disables this tier; yfinance + Finnhub remain the sources.
    twelvedata_api_key: str = ""

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"


settings = Settings()


def ensure_data_dir() -> None:
    """Make sure ./data and ./data/logs exist."""
    Path("./data").mkdir(parents=True, exist_ok=True)
    Path("./data/logs").mkdir(parents=True, exist_ok=True)
