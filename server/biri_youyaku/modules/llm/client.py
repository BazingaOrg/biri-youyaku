import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable

from openai import AsyncOpenAI

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
    TAGS_PROMPT,
)
from biri_youyaku.modules.llm.segmenter import should_chunk, split_transcript

logger = logging.getLogger(__name__)

SummaryChunkCallback = Callable[[str], Awaitable[None]]
TokenUsageCallback = Callable[[dict], Awaitable[None]]
# (done, total) 分段总结进度：长视频段级总结阶段没有流式 token，靠这个让前端
# 不至于盯着一动不动的「正在生成总结」。
SegmentProgressCallback = Callable[[int, int], Awaitable[None]]


def resolve_temperature(model: str) -> float:
    if settings.llm_temperature is not None:
        return settings.llm_temperature
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


def _thinking_kwargs(model: str) -> dict:
    """DeepSeek-v4 系列的思考模式开关。其他模型/厂商一律不传 extra_body。

    返回:
      - {} 表示不附加任何参数（其他厂商；或本就走默认行为）
      - {"extra_body": {"thinking": {"type": "enabled"}}, "temperature": None}
        表示开启思考模式 + temperature 不传（思考模式会静默忽略，避免误导）
      - {"extra_body": {"thinking": {"type": "disabled"}}} 显式关闭
    """
    lowered = (model or "").lower()
    if not lowered.startswith("deepseek-v4"):
        return {}
    if settings.llm_thinking_enabled:
        return {"extra_body": {"thinking": {"type": "enabled"}}, "skip_temperature": True}
    return {"extra_body": {"thinking": {"type": "disabled"}}}


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


def _build_create_kwargs(model: str, temperature: float, **base) -> dict:
    """组装 chat.completions.create 的 kwargs，统一处理思考模式与 temperature。"""
    kwargs = dict(base)
    kwargs["model"] = model
    thinking = _thinking_kwargs(model)
    if thinking.pop("skip_temperature", False):
        # 思考模式静默忽略 temperature/top_p，不传更干净，也方便日志识别。
        pass
    else:
        kwargs["temperature"] = temperature
    if "extra_body" in thinking:
        kwargs["extra_body"] = thinking["extra_body"]
    return kwargs


async def _complete(
    client: AsyncOpenAI,
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    on_usage: TokenUsageCallback | None = None,
) -> str:
    base_kwargs = _build_create_kwargs(model, temperature, messages=messages)
    try:
        response = await client.chat.completions.create(**base_kwargs)
    except Exception as exc:
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
    base_kwargs = _build_create_kwargs(
        model,
        temperature,
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
    )
    try:
        stream = await client.chat.completions.create(**base_kwargs)
    except Exception as exc:
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
    on_segment: SegmentProgressCallback | None = None,
) -> str:
    segments = list(split_transcript(items, settings.llm_chunk_token_threshold))
    total = len(segments)
    concurrency = max(1, int(settings.llm_segment_concurrency))
    semaphore = asyncio.Semaphore(concurrency)
    done_count = 0

    if on_segment is not None:
        await on_segment(0, total)

    async def _one_segment(index: int, segment: list[TranscriptItem]) -> tuple[int, str]:
        nonlocal done_count
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
        # 单线程 asyncio：done_count 自增在两个 await 之间是原子的
        done_count += 1
        if on_segment is not None:
            await on_segment(done_count, total)
        return index, text

    # 段级总结并行：长视频 5-6 段串行通常 5-10min，并行 2-3 路压到 2-3min。
    # 某段抛错时取消其它分段并 drain，避免孤儿协程继续占用 semaphore / 烧 token /
    # 在 job 已 FAILED 后回调 on_usage。
    tasks = [
        asyncio.create_task(_one_segment(idx, seg))
        for idx, seg in enumerate(segments, start=1)
    ]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        first_error: BaseException | None = None
        for task in done:
            first_error = task.exception()
            if first_error is not None:
                break
        if first_error is not None:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            raise first_error
        pairs = sorted((task.result() for task in tasks), key=lambda p: p[0])
    except BaseException:
        pending = [task for task in tasks if not task.done()]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        raise
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
    on_segment: SegmentProgressCallback | None = None,
) -> str:
    resolved_api_key = api_key or settings.llm_api_key
    if not resolved_api_key:
        raise RuntimeError(
            "LLM_API_KEY 未配置：请在 server/.env 设置 LLM_API_KEY 后重启后端"
            "（OpenAI 兼容供应商皆可；本地 ollama 可填任意非空字符串）。"
        )

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
            on_segment=on_segment,
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


def _parse_tags(content: str) -> list[str]:
    raw = re.split(r"[、,，\n;；/]+", content.strip())
    seen: set[str] = set()
    tags: list[str] = []
    for item in raw:
        # 去掉可能的编号/项目符号/引号
        tag = re.sub(r"^[\s\-*0-9.、)）(（\"'`]+", "", item).strip().strip("\"'` ")
        if not tag or len(tag) > 12 or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
        if len(tags) >= 6:
            break
    return tags


async def generate_tags(
    summary_md: str,
    options: JobOptions,
    *,
    api_key: str | None = None,
    raise_on_error: bool = False,
) -> list[str]:
    """从已生成的笔记里提炼 3-6 个主题标签。

    没配 key / 空笔记 → []。LLM 报错时默认返回 []（主流程非致命）；回填场景传
    raise_on_error=True，让调用方区分「确实没标签」与「这次调用失败、下次再试」。
    """
    resolved_api_key = api_key or settings.llm_api_key
    text = (summary_md or "").strip()
    if not resolved_api_key or not text:
        return []
    client = openai_client(
        api_key=resolved_api_key,
        base_url=options.llm_base_url or settings.llm_base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
    model = options.llm_model or settings.llm_model
    prompt = TAGS_PROMPT.replace("{{summary}}", text[:4000])  # 截断省 token
    try:
        content = await _complete(
            client, model=model, messages=[{"role": "user", "content": prompt}], temperature=0
        )
    except Exception as exc:
        logger.warning("生成标签失败 model=%s: %s", model, _format_llm_error(exc))
        if raise_on_error:
            raise
        return []
    return _parse_tags(content)
