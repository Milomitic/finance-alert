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

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"


settings = Settings()


def ensure_data_dir() -> None:
    """Make sure ./data and ./data/logs exist."""
    Path("./data").mkdir(parents=True, exist_ok=True)
    Path("./data/logs").mkdir(parents=True, exist_ok=True)
