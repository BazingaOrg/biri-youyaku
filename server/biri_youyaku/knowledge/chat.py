"""Opt-in knowledge chat over layered summary + transcript evidence (stateless SSE)."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from biri_youyaku.config import settings
from biri_youyaku.knowledge.retrieve import (
    EvidenceHit,
    evidence_hit_to_dict,
    query_needs_transcript_evidence,
    retrieve,
)
from biri_youyaku.modules._http import openai_client
from biri_youyaku.modules.llm.client import build_create_kwargs, resolve_temperature

logger = logging.getLogger("biri_youyaku.knowledge.chat")

SYSTEM_PROMPT = (
    "你是基于用户本地视频知识库的问答助手。"
    "证据分两类：① AI 视频总结（source_level=summary，定位为「AI 总结：…」），"
    "是二次压缩笔记，不是逐字原文；② 转写片段（source_level=transcript，"
    "定位为「转写：mm:ss–mm:ss」），来自平台字幕或 ASR。"
    "对数字、步骤、命令、引述、时间等事实性问题，优先依据转写证据回答，"
    "并引用转写定位；仅有总结时须降级措辞（如「总结中提到」），不得编造未在"
    "引用中出现的时间戳。subtitle_source=asr 时提示可能存在识别误差、降低确定性。"
    "禁止发明证据中不存在的时间、数字或命令。证据不足则明确无法回答。"
)

REFUSE_NO_HITS = (
    "在已登记的视频总结与转写中没有找到与问题相关的内容，无法回答。"
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
    start_sec: float | None = None
    end_sec: float | None = None
    subtitle_source: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "source_level": self.source_level,
            "heading_path": self.heading_path,
            "document_id": self.document_id,
            "title": self.title,
            "locator": self.locator,
        }
        if self.start_sec is not None:
            out["start_sec"] = self.start_sec
        if self.end_sec is not None:
            out["end_sec"] = self.end_sec
        if self.subtitle_source is not None:
            out["subtitle_source"] = self.subtitle_source
        return out


def citations_from_hits(hits: list[EvidenceHit]) -> list[Citation]:
    out: list[Citation] = []
    for hit in hits:
        heading = hit.heading_path or hit.locator
        out.append(
            Citation(
                id=hit.chunk_id,
                source_level=hit.source_level,
                heading_path=heading,
                document_id=hit.document_id,
                title=hit.title,
                locator=hit.locator,
                start_sec=hit.start_sec,
                end_sec=hit.end_sec,
                subtitle_source=hit.subtitle_source,
            )
        )
    return out


def validate_citation_ids(citation_ids: list[str], *, allowed: set[str]) -> list[str]:
    """Keep only IDs present in this retrieval snapshot (server-side)."""
    return [cid for cid in citation_ids if cid in allowed]


def _build_context(hits: list[EvidenceHit]) -> str:
    parts: list[str] = []
    for i, hit in enumerate(hits, start=1):
        title = hit.title or "(无标题)"
        level = hit.source_level
        locator = hit.locator
        asr_note = ""
        if level == "transcript" and (hit.subtitle_source or "") == "asr":
            asr_note = "（ASR 转写，可能有识别误差）"
        parts.append(
            f"[{i}] chunk_id={hit.chunk_id}\n"
            f"视频：{title}\n"
            f"source_level={level}\n"
            f"定位：{locator}{asr_note}\n"
            f"内容：\n{hit.chunk_text}\n"
        )
    return "\n---\n".join(parts)


def _user_message(query: str, hits: list[EvidenceHit]) -> str:
    has_transcript = any(h.source_level == "transcript" for h in hits)
    only_summary = hits and not has_transcript
    factual = query_needs_transcript_evidence(query, summary_hit_count=len(hits))
    degrade = ""
    if only_summary and factual:
        degrade = (
            "注意：本次仅检索到 AI 总结片段、没有转写证据；"
            "回答须使用「总结中提到」等降级措辞，不要给出未出现在证据中的 mm:ss。\n"
        )
    cite_hint = (
        "引用时：总结用「AI 总结：…」，转写用「转写：mm:ss–mm:ss」；"
        "不得编造未在证据中出现的时间戳。"
    )
    if has_transcript:
        cite_hint += "事实、数字、步骤、引述优先依据转写片段。"
    return (
        f"用户问题：{query}\n\n"
        f"{degrade}"
        f"以下是从本地知识库检索到的片段（仅可依据这些回答）：\n\n"
        f"{_build_context(hits)}\n\n"
        f"请用中文回答。{cite_hint}"
        "若证据不足请说明无法回答。"
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

    hits = retrieve(q, mode="chat", limit=limit)
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
        base_kwargs = build_create_kwargs(
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
                "hits": [evidence_hit_to_dict(h) for h in hits],
            },
            ensure_ascii=False,
        ),
    }
