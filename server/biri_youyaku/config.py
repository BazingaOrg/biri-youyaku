from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 注：uvicorn 的监听 host/port 由启动命令 `--host / --port` 决定，
    # 不再保留独立的 APP_HOST / APP_PORT 设置以免误导。
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
    llm_base_url: str = "https://api.deepseek.com/v1"
    # DeepSeek 最新基础款（替代已弃用的 deepseek-chat/deepseek-reasoner）。
    # 旗舰 deepseek-v4-pro 也可换用，但贵 3 倍、并发上限低，本场景不必。
    llm_model: str = "deepseek-v4-flash"
    llm_timeout_seconds: int = 300
    llm_max_retries: int = 2
    llm_temperature: float | None = None
    llm_chunk_token_threshold: int = 30000
    # 段级总结并发上限，>1 时长视频分段总结走 asyncio.gather。
    llm_segment_concurrency: int = 3
    # DeepSeek 思考模式开关（仅 deepseek-v4-* 系列有效，其他厂商忽略）。
    # 默认 False：
    #   1. 流式输出体验更好（思考模式下 reasoning_content 不在 content 流，用户要等很久）；
    #   2. 字幕总结是结构化笔记整理，不是复杂推理，flash 非思考模式足够；
    #   3. 思考模式静默忽略 temperature/top_p，与本项目温度配置冲突。
    # 想要更高总结质量可设为 True，代价是流式更慢、token 更多。
    llm_thinking_enabled: bool = False

    summary_language: str = "中文简体"

    # 邮件默认关闭：fork 的人开箱即用不会因为没配 webhook 而 fail；
    # email_default_recipient 默认空：避免「忘了改收件人 → 发到陌生人邮箱」。
    email_enabled: bool = False
    email_webhook_url: str = ""
    email_webhook_token: str = ""
    email_default_recipient: str = ""
    email_subject_template: str = "[Biri-Youyaku] {{title}}"

    # 公网部署防滥用：视频时长上限（秒）。超长视频拖死 ASR/LLM 槽位且总结质量差。
    # 默认 2.5 小时；公网部署可按机器能力收紧，避免超长视频拖死 ASR/LLM 槽位。
    max_video_duration_seconds: int = 9000
    # 在飞任务总数上限（PENDING + 各 RUNNING 阶段总和）。即便单 IP 在限流内灌任务，
    # 也不会让 PENDING 队列无限堆积。超出 → 503 让前端友好提示「忙不过来」。
    max_inflight_jobs: int = 20
    # 公网部署防 SSRF：/v1/llm/models 接受的 base_url 必须以这些 host 结尾。
    # 留空 = 允许任意（仅适合本地）。生产环境务必配齐。
    llm_base_url_allowed_hosts: str = (
        "api.deepseek.com,"
        "api.moonshot.cn,"
        "open.bigmodel.cn,"
        "generativelanguage.googleapis.com,"
        "api.openai.com,"
        "api.anthropic.com,"
        "api.x.ai"
    )

    audio_storage_dir: Path = Path("data/audio")
    summary_storage_dir: Path = Path("data/summaries")
    distill_storage_dir: Path = Path("data/distill")
    db_path: Path = Path("data/biri_youyaku.db")

    audio_retention_days: int = 7
    job_retention_days: int = 180
    max_concurrent_jobs: int = 2
    max_concurrent_summaries: int = 2
    # 蒸馏 _do_prepare_transcripts 阶段并发获取/转写视频的上限。
    distill_transcript_concurrency: int = 3

    # P3 新增：清理 / 维护策略
    # 注：字幕落盘缓存（subtitle_cache_retention_days）已规划但未实现，先不暴露。
    orphan_file_retention_days: int = 3
    stale_running_fail_hours: int = 4
    db_vacuum_interval_days: int = 30
    wal_checkpoint_interval_hours: int = 24
    cleanup_interval_seconds: int = 3600

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.app_cors_origins.split(",") if item.strip()]

    @property
    def llm_allowed_hosts(self) -> list[str]:
        return [
            item.strip().lower()
            for item in self.llm_base_url_allowed_hosts.split(",")
            if item.strip()
        ]

    @field_validator(
        "audio_storage_dir", "summary_storage_dir", "distill_storage_dir", "db_path", mode="before"
    )
    @classmethod
    def default_paths(cls, value: object, info):
        if value not in (None, ""):
            return value
        defaults = {
            "audio_storage_dir": Path("data/audio"),
            "summary_storage_dir": Path("data/summaries"),
            "distill_storage_dir": Path("data/distill"),
            "db_path": Path("data/biri_youyaku.db"),
        }
        return defaults[info.field_name]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
