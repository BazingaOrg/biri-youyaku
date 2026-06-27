"""启动时为「已完成但没有标签」的历史任务补标签。

后台跑、限速、不阻塞启动；LLM 调用失败的任务不写标签，留待下次启动重试。
"""

import asyncio
import logging

from biri_youyaku.config import settings
from biri_youyaku.jobs import repo
from biri_youyaku.jobs.model import JobOptions
from biri_youyaku.modules.llm import client as llm_client

logger = logging.getLogger(__name__)


async def backfill_missing_tags(*, limit: int = 500, delay_seconds: float = 1.0) -> int:
    """给已完成但无标签的任务补标签，返回成功处理条数。没配 LLM key 直接跳过。"""
    if not settings.llm_api_key:
        return 0
    jobs = repo.list_completed_without_tags(limit=limit)
    if not jobs:
        return 0
    logger.info("标签回填：发现 %d 条待处理", len(jobs))
    # 用**当前**默认供应商配置，而不是每条任务的历史快照——老任务可能记着已停用的
    # 供应商（如 kimi-k2.6 + Moonshot base_url），配上当前的 key 会 401。标签是从已存
    # 总结文本里提炼，跟当初用哪个模型生成无关，用当前可用的供应商即可。
    options = JobOptions.from_settings(settings)
    processed = 0
    for job in jobs:
        summary = repo.read_summary(job)
        if not summary:
            # 没有总结文件可提炼 → 写空标签占位，避免每次启动反复扫到。
            repo.set_tags(job.id, [])
            continue
        try:
            tags = await llm_client.generate_tags(summary, options, raise_on_error=True)
        except Exception:
            # 多半是网络/限流的瞬时失败：不写，下次启动再试。
            logger.warning("标签回填失败（稍后重试）：%s", job.id)
            continue
        repo.set_tags(job.id, tags)  # 即使为空也写，标记已处理
        processed += 1
        await asyncio.sleep(delay_seconds)  # 温柔点，别把 LLM 打爆
    logger.info("标签回填完成：处理 %d 条", processed)
    return processed
