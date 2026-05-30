import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

from biri_youyaku.config import settings
from biri_youyaku.jobs.model import JobOptions
from biri_youyaku.modules._http import openai_client
from biri_youyaku.modules.bilibili.meta import VideoMeta
from biri_youyaku.modules.bilibili.subtitle import TranscriptItem
from biri_youyaku.modules.asr.formatter import transcript_to_text
from biri_youyaku.modules.llm.prompts import (
    SUMMARY_MARKDOWN_PROMPT,
    SUMMARY_MERGE_MARKDOWN_PROMPT,
    SUMMARY_MERGE_PROMPT,
    SUMMARY_PROMPT,
    SUMMARY_REPAIR_PROMPT,
)
from biri_youyaku.modules.llm.segmenter import should_chunk, split_transcript

SummaryChunkCallback = Callable[[str], Awaitable[None]]
TokenUsageCallback = Callable[[dict], Awaitable[None]]


def _force_temp_one_prefixes() -> tuple[str, ...]:
    """从 settings 里解析「必须 temperature=1」的前缀列表（逗号分隔，小写）。"""
    raw = settings.llm_force_temp_one_prefixes or ""
    return tuple(p.strip().lower() for p in raw.split(",") if p.strip())


def resolve_temperature(model: str) -> float:
    if settings.llm_temperature is not None:
        return settings.llm_temperature
    # 命中前缀直接给 1，省掉一次 400→retry 的往返。
    lowered = (model or "").lower()
    if lowered.startswith(_force_temp_one_prefixes()):
        return 1
    return 0.2


def subtitle_source_label(subtitle_source: str | None) -> str:
    if subtitle_source == "platform":
        return "官方字幕"
    if subtitle_source == "asr":
        return "ASR 自动识别"
    return "未知"


def render_prompt(
    template: str,
    *,
    language: str,
    title: str,
    author: str,
    url: str,
    transcript: str,
    subtitle_source: str = "未知",
) -> str:
    return (
        template.replace("{{language}}", language)
        .replace("{{title}}", title)
        .replace("{{author}}", author)
        .replace("{{url}}", url)
        .replace("{{transcript}}", transcript)
        .replace("{{subtitles}}", transcript)
        .replace("{{segment}}", transcript)
        .replace("{{subtitle_source}}", subtitle_source)
    )


def _extract_summary_json(content: str) -> str:
    payload = json.loads(content)
    if not isinstance(payload, dict) or not isinstance(payload.get("summary"), str):
        raise ValueError('LLM output must be a JSON object with a string "summary" field')
    return payload["summary"]


def _is_temperature_rejected_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "temperature" in message and "only 1" in message


def _format_llm_error(exc: Exception) -> str:
    """把 openai/httpx 异常里通常被吞掉的 response body 拼到日志里。"""
    body = getattr(exc, "body", None) or getattr(getattr(exc, "response", None), "text", None)
    status = getattr(getattr(exc, "response", None), "status_code", None) or getattr(exc, "status_code", None)
    parts = [type(exc).__name__]
    if status is not None:
        parts.append(f"HTTP {status}")
    parts.append(str(exc))
    if body:
        parts.append(f"body={body!s:.500}")
    return " | ".join(parts)


def _usage_to_dict(usage) -> dict | None:
    if usage is None:
        return None
    input_tokens = getattr(usage, "prompt_tokens", None)
    output_tokens = getattr(usage, "completion_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)
    if input_tokens is None and hasattr(usage, "input_tokens"):
        input_tokens = usage.input_tokens
    if output_tokens is None and hasattr(usage, "output_tokens"):
        output_tokens = usage.output_tokens
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None
    return {
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "total_tokens": int(total_tokens or 0),
        "cost_estimate": None,
    }


async def _complete(
    client: AsyncOpenAI,
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    on_usage: TokenUsageCallback | None = None,
) -> str:
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )
    except Exception as exc:
        if temperature != 1 and _is_temperature_rejected_error(exc):
            logger.warning("LLM 拒收 temperature=%s，自动切到 1 重试（model=%s）", temperature, model)
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=1,
            )
        else:
            logger.error("LLM 调用失败 model=%s: %s", model, _format_llm_error(exc))
            raise
    usage = _usage_to_dict(getattr(response, "usage", None))
    if usage is not None and on_usage is not None:
        await on_usage(usage)
    return response.choices[0].message.content or ""


async def _complete_stream(
    client: AsyncOpenAI,
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    on_chunk: SummaryChunkCallback,
    on_usage: TokenUsageCallback | None = None,
) -> str:
    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=True,
            stream_options={"include_usage": True},
        )
    except Exception as exc:
        if temperature != 1 and _is_temperature_rejected_error(exc):
            logger.warning("LLM 流式拒收 temperature=%s，自动切到 1 重试（model=%s）", temperature, model)
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=1,
                stream=True,
                stream_options={"include_usage": True},
            )
        else:
            logger.error("LLM 流式调用失败 model=%s: %s", model, _format_llm_error(exc))
            raise

    content = ""
    async for chunk in stream:
        usage = _usage_to_dict(getattr(chunk, "usage", None))
        if usage is not None and on_usage is not None:
            await on_usage(usage)
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content or ""
        if not delta:
            continue
        content += delta
        await on_chunk(content)
    return content


async def _repair_summary_json(
    client: AsyncOpenAI,
    *,
    model: str,
    content: str,
    on_usage: TokenUsageCallback | None = None,
) -> str:
    repaired = await _complete(
        client,
        model=model,
        messages=[
            {"role": "system", "content": SUMMARY_REPAIR_PROMPT},
            {"role": "user", "content": content},
        ],
        temperature=0,
        on_usage=on_usage,
    )
    return _extract_summary_json(repaired)


async def _complete_json_summary(
    client: AsyncOpenAI,
    *,
    model: str,
    prompt: str,
    on_usage: TokenUsageCallback | None = None,
) -> str:
    content = await _complete(
        client,
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=resolve_temperature(model),
        on_usage=on_usage,
    )
    try:
        return _extract_summary_json(content)
    except (ValueError, json.JSONDecodeError):
        return await _repair_summary_json(client, model=model, content=content, on_usage=on_usage)


async def _summarize_segment_markdown(
    client: AsyncOpenAI,
    *,
    model: str,
    prompt: str,
    on_usage: TokenUsageCallback | None,
) -> str:
    """段级总结直接出 markdown，不再走 JSON wrap → 省一轮 JSON repair。

    合并阶段才需要严格结构，段级只是中间产物。
    """
    return await _complete(
        client,
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=resolve_temperature(model),
        on_usage=on_usage,
    )


async def _summarize_chunked(
    client: AsyncOpenAI,
    *,
    items: list[TranscriptItem],
    meta: VideoMeta,
    model: str,
    language: str,
    subtitle_source: str | None,
    on_chunk: SummaryChunkCallback | None = None,
    on_usage: TokenUsageCallback | None = None,
) -> str:
    segments = list(split_transcript(items, settings.llm_chunk_token_threshold))
    concurrency = max(1, int(settings.llm_segment_concurrency))
    semaphore = asyncio.Semaphore(concurrency)

    async def _one_segment(index: int, segment: list[TranscriptItem]) -> tuple[int, str]:
        prompt = render_prompt(
            SUMMARY_MARKDOWN_PROMPT,
            language=language,
            title=f"{meta.title}（分段 {index}）",
            author=meta.author,
            url=meta.url,
            transcript=transcript_to_text(segment),
            subtitle_source=subtitle_source_label(subtitle_source),
        )
        async with semaphore:
            text = await _summarize_segment_markdown(client, model=model, prompt=prompt, on_usage=on_usage)
        return index, text

    # 段级总结并行：长视频 5-6 段串行通常 5-10min，并行 2-3 路压到 2-3min
    tasks = [
        asyncio.create_task(_one_segment(idx, seg))
        for idx, seg in enumerate(segments, start=1)
    ]
    pairs = await asyncio.gather(*tasks)
    pairs.sort(key=lambda p: p[0])
    segment_summaries = [f"### 分段 {idx}\n{text}" for idx, text in pairs]

    merge_prompt = render_prompt(
        SUMMARY_MERGE_MARKDOWN_PROMPT if on_chunk is not None else SUMMARY_MERGE_PROMPT,
        language=language,
        title=meta.title,
        author=meta.author,
        url=meta.url,
        transcript="\n\n".join(segment_summaries),
        subtitle_source=subtitle_source_label(subtitle_source),
    )
    if on_chunk is not None:
        return await _complete_stream(
            client,
            model=model,
            messages=[{"role": "user", "content": merge_prompt}],
            temperature=resolve_temperature(model),
            on_chunk=on_chunk,
            on_usage=on_usage,
        )
    return await _complete_json_summary(client, model=model, prompt=merge_prompt, on_usage=on_usage)


async def summarize(
    items: list[TranscriptItem],
    meta: VideoMeta,
    options: JobOptions,
    *,
    api_key: str | None = None,
    subtitle_source: str | None = None,
    on_chunk: SummaryChunkCallback | None = None,
    on_usage: TokenUsageCallback | None = None,
) -> str:
    resolved_api_key = api_key or settings.llm_api_key
    if not resolved_api_key:
        raise RuntimeError("LLM_API_KEY 未配置")

    transcript = transcript_to_text(items)
    # 按 (api_key, base_url, timeout, max_retries) 复用 client，HTTP 连接池命中
    client = openai_client(
        api_key=resolved_api_key,
        base_url=options.llm_base_url or settings.llm_base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
    model = options.llm_model or settings.llm_model
    language = options.summary_language or settings.summary_language

    if options.prompt_template:
        prompt = render_prompt(
            options.prompt_template,
            language=language,
            title=meta.title,
            author=meta.author,
            url=meta.url,
            transcript=transcript,
            subtitle_source=subtitle_source_label(subtitle_source),
        )
        if on_chunk is not None:
            return await _complete_stream(
                client,
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=resolve_temperature(model),
                on_chunk=on_chunk,
                on_usage=on_usage,
            )
        return await _complete(
            client,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=resolve_temperature(model),
            on_usage=on_usage,
        )

    if should_chunk(items, settings.llm_chunk_token_threshold):
        return await _summarize_chunked(
            client,
            items=items,
            meta=meta,
            model=model,
            language=language,
            subtitle_source=subtitle_source,
            on_chunk=on_chunk,
            on_usage=on_usage,
        )

    prompt = render_prompt(
        SUMMARY_MARKDOWN_PROMPT if on_chunk is not None else SUMMARY_PROMPT,
        language=language,
        title=meta.title,
        author=meta.author,
        url=meta.url,
        transcript=transcript,
        subtitle_source=subtitle_source_label(subtitle_source),
    )
    if on_chunk is not None:
        return await _complete_stream(
            client,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=resolve_temperature(model),
            on_chunk=on_chunk,
            on_usage=on_usage,
        )

    return await _complete_json_summary(client, model=model, prompt=prompt, on_usage=on_usage)
