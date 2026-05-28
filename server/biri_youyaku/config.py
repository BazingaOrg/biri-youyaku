from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_host: str = "0.0.0.0"
    app_port: int = 17821
    app_log_level: str = "INFO"
    app_cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    api_token: str = ""

    bili_sessdata: str = ""
    bili_buvid3: str = ""
    bili_bili_jct: str = ""

    asr_model: str = "sensevoice"
    asr_device: str = "auto"
    asr_language_default: str = "auto"
    sensevoice_model_dir: str = ""

    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: int = 300
    llm_max_retries: int = 2
    llm_temperature: float | None = None
    llm_chunk_token_threshold: int = 30000

    summary_language: str = "中文简体"

    email_enabled: bool = True
    email_webhook_url: str = ""
    email_webhook_token: str = ""
    email_default_recipient: str = "zhangyouxiu66@gmail.com"
    email_subject_template: str = "[Biri-Youyaku] {{title}}"

    audio_storage_dir: Path = Path("data/audio")
    summary_storage_dir: Path = Path("data/summaries")
    db_path: Path = Path("data/biri_youyaku.db")

    audio_retention_days: int = 7
    job_retention_days: int = 180
    max_concurrent_jobs: int = 2
    max_concurrent_summaries: int = 2

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.app_cors_origins.split(",") if item.strip()]

    @field_validator("audio_storage_dir", "summary_storage_dir", "db_path", mode="before")
    @classmethod
    def default_paths(cls, value: object, info):
        if value not in (None, ""):
            return value
        defaults = {
            "audio_storage_dir": Path("data/audio"),
            "summary_storage_dir": Path("data/summaries"),
            "db_path": Path("data/biri_youyaku.db"),
        }
        return defaults[info.field_name]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
