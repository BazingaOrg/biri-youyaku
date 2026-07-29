"""Opt-in knowledge chat over summary FTS hits (stateless SSE)."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from biri_youyaku.config import settings
from biri_youyaku.knowledge.search import Hit, hit_to_dict, search_summaries
from biri_youyaku.modules._http import openai_client
from biri_youyaku.modules.llm.client import _build_create_kwargs, resolve_temperature

logger = logging.getLogger("biri_youyaku.knowledge.chat")

SYSTEM_PROMPT = (
    "你是基于用户本地「AI 视频总结」的问答助手。"
    "只能依据给定总结片段回答；标注来源为「AI 总结：…」；"
    "禁止编造视频时间戳；不确定则说明「总结中提到」或拒答；"
    "不要把总结当作外部核实事实。"
)

REFUSE_NO_HITS = (
    "在已登记的 AI 视频总结中没有找到与问题相关的内容，无法回答。"
    "可以换个关键词，或先总结更多相关视频。"
)

DEFAULT_TOP_K = 6


@dataclass(frozen=True)
class Citation:
    id: str
    source_level: str
    heading_path: str
    document_id: str
    title: str | None
    locator: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_level": self.source_level,
            "heading_path": self.heading_path,
            "document_id": self.document_id,
            "title": self.title,
            "locator": self.locator,
        }


def citations_from_hits(hits: list[Hit]) -> list[Citation]:
    return [
        Citation(
            id=hit.chunk_id,
            source_level="summary",
            heading_path=hit.heading_path,
            document_id=hit.document_id,
            title=hit.title,
            locator=hit.heading_path,
        )
        for hit in hits
    ]


def validate_citation_ids(citation_ids: list[str], *, allowed: set[str]) -> list[str]:
    """Keep only IDs present in this retrieval snapshot (server-side)."""
    return [cid for cid in citation_ids if cid in allowed]


def _build_context(hits: list[Hit]) -> str:
    parts: list[str] = []
    for i, hit in enumerate(hits, start=1):
        title = hit.title or "(无标题)"
        parts.append(
            f"[{i}] chunk_id={hit.chunk_id}\n"
            f"视频：{title}\n"
            f"来源：{hit.heading_path}\n"
            f"内容：\n{hit.chunk_text}\n"
        )
    return "\n---\n".join(parts)


def _user_message(query: str, hits: list[Hit]) -> str:
    return (
        f"用户问题：{query}\n\n"
        f"以下是从本地「AI 视频总结」检索到的片段（仅可依据这些回答）：\n\n"
        f"{_build_context(hits)}\n\n"
        "请用中文回答。引用时使用「AI 总结：…」形式的 heading_path，"
        "不要编造 mm:ss 时间戳。若证据不足请说明「总结中提到」或明确无法回答。"
    )


async def stream_chat(
    query: str,
    *,
    limit: int = DEFAULT_TOP_K,
) -> AsyncIterator[dict[str, str]]:
    """Yield SSE event dicts: {event, data} with JSON data payloads."""
    q = (query or "").strip()
    if not q:
        yield {
            "event": "error",
            "data": json.dumps({"message": "问题不能为空"}, ensure_ascii=False),
        }
        return

    if not settings.knowledge_chat_enabled:
        yield {
            "event": "error",
            "data": json.dumps(
                {
                    "message": "知识问答未启用（KNOWLEDGE_CHAT_ENABLED=false）",
                    "code": "chat_disabled",
                },
                ensure_ascii=False,
            ),
        }
        return

    yield {
        "event": "status",
        "data": json.dumps({"phase": "searching"}, ensure_ascii=False),
    }

    hits = search_summaries(q, limit=limit)
    allowed_ids = {h.chunk_id for h in hits}
    citations = [c for c in citations_from_hits(hits) if c.id in allowed_ids]

    if not hits:
        yield {
            "event": "status",
            "data": json.dumps(
                {"phase": "refuse", "reason": "no_hits"}, ensure_ascii=False
            ),
        }
        yield {
            "event": "delta",
            "data": json.dumps({"text": REFUSE_NO_HITS}, ensure_ascii=False),
        }
        yield {
            "event": "citations",
            "data": json.dumps({"citations": []}, ensure_ascii=False),
        }
        yield {
            "event": "done",
            "data": json.dumps(
                {"refused": True, "reason": "no_hits", "hits": []},
                ensure_ascii=False,
            ),
        }
        return

    yield {
        "event": "status",
        "data": json.dumps(
            {"phase": "generating", "hit_count": len(hits)},
            ensure_ascii=False,
        ),
    }
    yield {
        "event": "citations",
        "data": json.dumps(
            {"citations": [c.as_dict() for c in citations]},
            ensure_ascii=False,
        ),
    }

    if not settings.llm_api_key:
        yield {
            "event": "error",
            "data": json.dumps(
                {"message": "LLM_API_KEY 未配置，无法生成回答"},
                ensure_ascii=False,
            ),
        }
        return

    client = openai_client(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=float(settings.llm_timeout_seconds),
        max_retries=int(settings.llm_max_retries),
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _user_message(q, hits)},
    ]

    try:
        model = settings.llm_model
        temperature = resolve_temperature()
        base_kwargs = _build_create_kwargs(
            model,
            temperature,
            messages=messages,
            stream=True,
        )
        stream = await client.chat.completions.create(**base_kwargs)
        assembled: list[str] = []
        async for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            if choice is None:
                continue
            delta = getattr(choice.delta, "content", None) or ""
            if not delta:
                continue
            assembled.append(delta)
            yield {
                "event": "delta",
                "data": json.dumps(
                    {"text": "".join(assembled), "append": delta},
                    ensure_ascii=False,
                ),
            }
        final_text = "".join(assembled)
    except Exception as exc:
        logger.exception("knowledge chat LLM failed")
        yield {
            "event": "error",
            "data": json.dumps(
                {"message": f"生成回答失败：{type(exc).__name__}"},
                ensure_ascii=False,
            ),
        }
        return

    yield {
        "event": "done",
        "data": json.dumps(
            {
                "refused": False,
                "text": final_text,
                "citations": [c.as_dict() for c in citations],
                "hits": [hit_to_dict(h) for h in hits],
            },
            ensure_ascii=False,
        ),
    }
