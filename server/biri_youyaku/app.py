from collections.abc import AsyncIterator
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from biri_youyaku.auth import _expected_token
from biri_youyaku.config import settings
from biri_youyaku.db import init_db
from biri_youyaku.rate_limit import limiter
from biri_youyaku.jobs.cleanup import (
    cleanup_loop,
    cleanup_once,
    clean_tempfile_residues,
    fail_stale_running_once,
    scan_orphans_once,
)
from biri_youyaku.distill.orchestrator import recover_unfinished_runs
from biri_youyaku.jobs.runner import recover_unfinished_jobs
from biri_youyaku.logging import configure_logging
from biri_youyaku.modules._http import aclose_all
from biri_youyaku.routes import (
    config_public_router,
    config_router,
    distill_router,
    healthz_router,
    jobs_router,
    up_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log = logging.getLogger("biri_youyaku.startup")
    token = _expected_token()
    log.info(
        "API_TOKEN auth %s (token length=%d)",
        "enabled" if token else "disabled",
        len(token),
    )
    # LLM key 自检：未配置时启动期就 WARN 一行，省得用户跑到「点了创建任务才失败」
    # 才发现 .env 没填。开发或纯 ASR demo 场景允许空着启动，所以不抛错只 warn。
    if not settings.llm_api_key:
        log.warning(
            "LLM_API_KEY 未配置 → 创建任务时会失败。"
            "请在 server/.env 里填 LLM_API_KEY（默认 DeepSeek；OpenAI / 本地 ollama 等 OpenAI 兼容接口也行）。"
        )
    # 邮件配置一致性自检：开关打开却没配 webhook / token / 收件人时给一条警告，
    # 避免后端启动「看起来正常」但每个 job 走到 EMAILING 都报错。
    if settings.email_enabled:
        missing = []
        if not (settings.email_webhook_url or "").strip():
            missing.append("EMAIL_WEBHOOK_URL")
        if not (settings.email_webhook_token or "").strip():
            missing.append("EMAIL_WEBHOOK_TOKEN")
        if not (settings.email_default_recipient or "").strip():
            missing.append("EMAIL_DEFAULT_RECIPIENT")
        if missing:
            log.warning(
                "EMAIL_ENABLED=true 但下列必填项为空 → 邮件将失败：%s。请在 .env 配齐或设 EMAIL_ENABLED=false。",
                ", ".join(missing),
            )
    init_db()
    # 启动期：清掉上次崩溃残留 + 跑一遍常规清理 + 兜底僵尸 + 扫孤儿
    clean_tempfile_residues()
    await cleanup_once()
    await fail_stale_running_once()
    await scan_orphans_once()
    recover_unfinished_jobs()
    recover_unfinished_runs()
    cleanup_task = asyncio.create_task(cleanup_loop())
    warmup_task = asyncio.create_task(_warmup_asr())
    tags_task = asyncio.create_task(_backfill_tags())
    try:
        yield
    finally:
        for task in (cleanup_task, warmup_task, tags_task):
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # warmup 失败不阻塞退出
                pass
        # 关闭共享 client 释放 socket，避免 pytest / reload 留连接
        await aclose_all()


async def _backfill_tags() -> None:
    """后台为历史任务补主题标签（不阻塞启动，失败只 log）。"""
    log = logging.getLogger("biri_youyaku.startup")
    try:
        from biri_youyaku.jobs.tags_backfill import backfill_missing_tags

        await backfill_missing_tags()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log.warning("标签回填任务异常（忽略）：%s", exc)


async def _warmup_asr() -> None:
    """异步预加载 ASR 模型。

    第一次推理通常要 5-15s 加载 funasr / faster-whisper 权重；放后台跑可以让第一个
    真实请求直接命中已驻留内存的模型。失败只 log，不影响服务可用。
    """
    log = logging.getLogger("biri_youyaku.startup")
    try:
        # 推迟 import：sandbox / 未装 ASR 依赖的部署不会因为加载这一行就拉链
        from biri_youyaku.modules.asr import get_transcriber

        transcriber = get_transcriber(settings.asr_model)
        warmup = getattr(transcriber, "warmup", None)
        if warmup is None:
            log.info(
                "ASR warmup skipped: transcriber %s has no warmup hook", type(transcriber).__name__
            )
            return
        await asyncio.to_thread(warmup)
        log.info("ASR warmup completed: %s", type(transcriber).__name__)
    except Exception as exc:
        log.warning("ASR warmup failed (will load on first use): %s", exc)


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """全局兜底：未捕获异常一律返回通用 500，详细堆栈只进日志。
    避免把内部路径 / API key / 堆栈片段直接吐给客户端。
    """
    logging.getLogger("biri_youyaku.error").exception(
        "Unhandled exception on %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请稍后重试"},
    )


def create_app() -> FastAPI:
    app = FastAPI(title="Biri-Youyaku Server", version="0.1.0", lifespan=lifespan)
    # slowapi：超额自动 429，每路由用 @limiter.limit("...") 声明阈值
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(config_public_router)
    app.include_router(config_router)
    app.include_router(distill_router)
    app.include_router(healthz_router)
    app.include_router(jobs_router)
    app.include_router(up_router)
    return app


app = create_app()
