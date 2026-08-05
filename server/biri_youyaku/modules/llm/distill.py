"""作者蒸馏语料的 LLM 调用层：视频观点提取。

复用 `client.py` 的底层非流式补全（`complete`）与分段阈值判断
（`segmenter.should_chunk` / `split_transcript`），但走蒸馏专用 prompt
（`distill_prompts.py`）而非笔记总结 prompt——两条链路目标不同（观点密度 vs
操作步骤/结构化摘要），不共享 prompt。这里不发邮件、不打标签，那是 summary
链路的职责；也不需要流式/进度回调，蒸馏是后台批处理，没有前端在等 chunk。
"""

from __future__ import annotations

import logging

from biri_youyaku.config import (
    LLM_CHUNK_TOKEN_THRESHOLD,
    LLM_MAX_RETRIES,
    LLM_TIMEOUT_SECONDS,
    settings,
)
from biri_youyaku.modules._http import openai_client
from biri_youyaku.modules.llm.client import complete, resolve_temperature
from biri_youyaku.modules.llm.usage import make_context
from biri_youyaku.modules.llm.distill_prompts import (
    DISTILL_EXTRACT_MERGE_PROMPT,
    DISTILL_EXTRACT_PROMPT,
)
from biri_youyaku.modules.llm.segmenter import should_chunk, split_transcript
from biri_youyaku.modules.transcript import TranscriptItem

logger = logging.getLogger(__name__)


def _client():
    api_key = settings.llm_api_key
    if not api_key:
        raise RuntimeError(
            "LLM_API_KEY 未配置：请在 server/.env 设置 LLM_API_KEY 后重启后端"
            "（OpenAI 兼容供应商皆可；本地 ollama 可填任意非空字符串）。"
        )
    return openai_client(
        api_key=api_key,
        base_url=settings.llm_base_url,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=LLM_MAX_RETRIES,
    )


def _render(template: str, **tokens: str) -> str:
    text = template
    for key, value in tokens.items():
        text = text.replace("{{" + key + "}}", value)
    return text


async def _complete_prompt(prompt: str, *, operation: str, run_id: str | None = None) -> str:
    client = _client()
    api_key = settings.llm_api_key
    return await complete(
        client,
        model=settings.llm_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=resolve_temperature(),
        usage_context=make_context(
            job_id=run_id,
            operation=operation,
            base_url=settings.llm_base_url,
            api_key=api_key,
            model=settings.llm_model,
        ),
    )


def _pseudo_items(text: str) -> list[TranscriptItem]:
    """把拼好的转写文本还原成「一行一个 item」的伪 TranscriptItem 列表，只为了复用
    `should_chunk` / `split_transcript` 现成的分段阈值判断，不重复实现一套分段逻辑。
    `transcript_to_text` 本就是按行 join 各 item.text，这里按行拆回去足够还原粒度。
    """
    lines = [line for line in text.split("\n") if line.strip()]
    if not lines:
        return [TranscriptItem(start=0.0, end=0.0, text=text)]
    return [TranscriptItem(start=0.0, end=0.0, text=line) for line in lines]


async def extract_video_viewpoints(
    title: str, transcript_text: str, language: str, *, run_id: str | None = None
) -> str:
    """单视频观点提取。转写超过 `LLM_CHUNK_TOKEN_THRESHOLD` 时按分段
    提取、再用 MERGE 合并（模式仿 `client._summarize_chunked`，但不需要流式/
    并发进度回调）；分段内部顺序执行——分段间没有并发要求，编排层面的并发
    （同一个 run 里多个视频并行提取）由调用方（distill/orchestrator.py）用
    `asyncio.Semaphore(2)` 控制。
    """
    items = _pseudo_items(transcript_text)
    if not should_chunk(items, LLM_CHUNK_TOKEN_THRESHOLD):
        prompt = _render(
            DISTILL_EXTRACT_PROMPT, title=title, transcript=transcript_text, language=language
        )
        return await _complete_prompt(prompt, operation="distill_extract", run_id=run_id)

    segments = split_transcript(items, LLM_CHUNK_TOKEN_THRESHOLD)
    extracts: list[str] = []
    for index, segment in enumerate(segments, start=1):
        segment_text = "\n".join(item.text for item in segment)
        prompt = _render(
            DISTILL_EXTRACT_PROMPT,
            title=f"{title}（分段 {index}）",
            transcript=segment_text,
            language=language,
        )
        text = await _complete_prompt(prompt, operation="distill_extract", run_id=run_id)
        extracts.append(f"### 分段 {index}\n{text}")

    merge_prompt = _render(
        DISTILL_EXTRACT_MERGE_PROMPT,
        title=title,
        transcript="\n\n".join(extracts),
        language=language,
    )
    return await _complete_prompt(merge_prompt, operation="distill_extract_merge", run_id=run_id)
