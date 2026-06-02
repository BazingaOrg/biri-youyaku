import logging

from biri_youyaku.config import settings


# 这些 logger 在 DEBUG 级别会打 HTTP 请求行 / headers，
# 包含 Authorization: Bearer <key>。为了防止用户把 APP_LOG_LEVEL=DEBUG 之后
# key 落到日志里，统一把它们钉死在 WARNING。
_SENSITIVE_LIBRARY_LOGGERS = (
    "openai",
    "openai._base_client",
    "httpx",
    "httpcore",
)


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.app_log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    for name in _SENSITIVE_LIBRARY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
