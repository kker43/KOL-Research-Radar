from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    kol_db_path: Path = Path("./data/kol_radar.db")
    initial_lookback_days: int = Field(default=60, ge=30, le=90)
    obsidian_vault_path: Path | None = None
    wewe_rss_base_url: str = "http://localhost:4000"
    openai_api_key: str | None = None
    openai_model: str | None = None
    log_level: str = "INFO"
