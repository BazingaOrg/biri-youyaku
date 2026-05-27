import json

from openai import AsyncOpenAI

from biri_youyaku.config import settings
from biri_youyaku.jobs.model import JobOptions
from biri_youyaku.modules.bilibili.meta import VideoMeta
from biri_youyaku.modules.bilibili.subtitle import TranscriptItem
from biri_youyaku.modules.asr.formatter import transcript_to_text
from biri_youyaku.modules.llm.prompts import SUMMARY_PROMPT, SUMMARY_REPAIR_PROMPT


def resolve_temperature(model: str) -> float:
    if settings.llm_temperature is not None:
        return settings.llm_temperature
    if model == "kimi-k2.5":
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


async def _complete(
    client: AsyncOpenAI,
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
) -> str:
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )
    except Exception as exc:
        if temperature != 1 and _is_temperature_rejected_error(exc):
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=1,
            )
        else:
            raise
    return response.choices[0].message.content or ""


async def _repair_summary_json(client: AsyncOpenAI, *, model: str, content: str) -> str:
    repaired = await _complete(
        client,
        model=model,
        messages=[
            {"role": "system", "content": SUMMARY_REPAIR_PROMPT},
            {"role": "user", "content": content},
        ],
        temperature=0,
    )
    return _extract_summary_json(repaired)


async def summarize(
    items: list[TranscriptItem],
    meta: VideoMeta,
    options: JobOptions,
    *,
    api_key: str | None = None,
    subtitle_source: str | None = None,
) -> str:
    resolved_api_key = api_key or settings.llm_api_key
    if not resolved_api_key:
        raise RuntimeError("LLM_API_KEY 未配置")

    transcript = transcript_to_text(items)
    client = AsyncOpenAI(
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
        return await _complete(
            client,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=resolve_temperature(model),
        )

    prompt = render_prompt(
        SUMMARY_PROMPT,
        language=language,
        title=meta.title,
        author=meta.author,
        url=meta.url,
        transcript=transcript,
        subtitle_source=subtitle_source_label(subtitle_source),
    )
    content = await _complete(
        client,
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=resolve_temperature(model),
    )
    try:
        return _extract_summary_json(content)
    except (ValueError, json.JSONDecodeError):
        return await _repair_summary_json(client, model=model, content=content)
