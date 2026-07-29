"""Split markdown AI summaries into retrieval chunks with heading paths.

Rules (Phase B):
- Parse `##` / `###` headings only; never invent headings not in the text.
- Heading path labels: `AI 总结：…` (no mm:ss timestamps).
- No usable `##` headings → single chunk `AI 总结：全文`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


@dataclass(frozen=True)
class SummaryChunk:
    heading_path: str
    chunk_text: str
    chunk_ord: int


def fts_prepare_text(text: str) -> str:
    """Insert spaces around each CJK character so FTS5 unicode61 tokenizes them."""
    if not text:
        return ""
    out: list[str] = []
    for ch in text:
        if _CJK_RE.match(ch):
            out.append(" ")
            out.append(ch)
            out.append(" ")
        else:
            out.append(ch)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _label_for_stack(stack: list[str]) -> str:
    if not stack:
        return "AI 总结：全文"
    return "AI 总结：" + " / ".join(stack)


def chunk_summary_markdown(text: str) -> list[SummaryChunk]:
    """Chunk a summary markdown body into section-level pieces."""
    body = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not body.strip():
        return []

    lines = body.split("\n")
    has_h2 = any(_HEADING_RE.match(line) and line.startswith("## ") for line in lines)
    if not has_h2:
        stripped = body.strip()
        if not stripped:
            return []
        return [
            SummaryChunk(
                heading_path="AI 总结：全文",
                chunk_text=stripped,
                chunk_ord=0,
            )
        ]

    # stack of heading titles for h2/h3
    stack: list[str] = []
    section_lines: list[str] = []
    chunks: list[SummaryChunk] = []
    preamble: list[str] = []
    started = False

    def flush() -> None:
        nonlocal section_lines
        content = "\n".join(section_lines).strip()
        section_lines = []
        if not content and not stack:
            return
        # Skip empty sections after a heading with no body (unless we have title only).
        if not content:
            return
        path = _label_for_stack(stack)
        chunks.append(
            SummaryChunk(
                heading_path=path,
                chunk_text=content,
                chunk_ord=len(chunks),
            )
        )

    for line in lines:
        match = _HEADING_RE.match(line)
        if match is None:
            if not started:
                preamble.append(line)
            else:
                section_lines.append(line)
            continue

        level = len(match.group(1))  # 2 or 3
        title = match.group(2).strip()
        if not title:
            if started:
                section_lines.append(line)
            else:
                preamble.append(line)
            continue

        if not started:
            # Drop preamble without a heading (no invented "intro" path).
            started = True
            preamble = []
        else:
            flush()

        if level == 2:
            stack = [title]
        else:
            # ### under current ##; if no h2 yet, treat as top of stack.
            if stack:
                stack = [stack[0], title]
            else:
                stack = [title]
        # Include heading line in chunk text for context.
        section_lines = [line]

    if started:
        flush()
    elif preamble:
        stripped = "\n".join(preamble).strip()
        if stripped:
            chunks.append(
                SummaryChunk(
                    heading_path="AI 总结：全文",
                    chunk_text=stripped,
                    chunk_ord=0,
                )
            )

    if not chunks:
        stripped = body.strip()
        if stripped:
            return [
                SummaryChunk(
                    heading_path="AI 总结：全文",
                    chunk_text=stripped,
                    chunk_ord=0,
                )
            ]
    else:
        # Re-number ord in case of skips.
        chunks = [
            SummaryChunk(
                heading_path=c.heading_path,
                chunk_text=c.chunk_text,
                chunk_ord=i,
            )
            for i, c in enumerate(chunks)
        ]
    return chunks
