"""Split markdown AI summaries into retrieval chunks with heading paths.

Legacy notes use `AI 总结：…` paths and leave start_sec empty.
Timed notes (`## mm:ss 主题`) strip the clock from the path and store start_sec.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$")
_TIMED_H2_RE = re.compile(r"^##\s+(\d+):([0-5]\d)\b")
_TIME_PREFIX_RE = re.compile(r"^(\d+):([0-5]\d)(?:\s+|$)")
_HEADING_TIME_LINE_RE = re.compile(r"^#{2,3}\s+(\d+):([0-5]\d)\b")
# Exported for search phrase heuristics (same CJK ranges as fts_prepare_text).
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


@dataclass(frozen=True)
class SummaryChunk:
    heading_path: str
    chunk_text: str
    chunk_ord: int
    start_sec: float | None = None


@dataclass(frozen=True)
class TranscriptWindow:
    """Merged raw-transcript window for FTS (Phase C)."""

    start_sec: float
    end_sec: float
    chunk_text: str
    chunk_ord: int
    subtitle_source: str | None


# Window merge targets: ~800–1500 chars, ~45–90s, max ~8 segments.
_WINDOW_MAX_CHARS = 1200
_WINDOW_MAX_SPAN_SEC = 75.0
_WINDOW_MAX_SEGMENTS = 8


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


def _seconds_from_mmss(minutes: str, seconds: str) -> float:
    return float(int(minutes) * 60 + int(seconds))


def parse_heading_start_sec(title: str) -> float | None:
    match = _TIME_PREFIX_RE.match((title or "").strip())
    if match is None:
        return None
    return _seconds_from_mmss(match.group(1), match.group(2))


def parse_chunk_start_sec(heading_path: str | None, chunk_text: str | None) -> float | None:
    """Recover start_sec from heading_path or the chunk's first heading line."""
    from_path = parse_heading_start_sec(heading_path or "")
    if from_path is not None:
        return from_path
    first_line = (chunk_text or "").replace("\r\n", "\n").split("\n", 1)[0].strip()
    match = _HEADING_TIME_LINE_RE.match(first_line)
    if match is not None:
        return _seconds_from_mmss(match.group(1), match.group(2))
    return parse_heading_start_sec(first_line)


def _strip_time_prefix(title: str) -> str:
    stripped = (title or "").strip()
    match = _TIME_PREFIX_RE.match(stripped)
    if match is None:
        return stripped
    rest = stripped[match.end() :].strip()
    return rest or stripped


def _is_timed_format(body: str) -> bool:
    return any(_TIMED_H2_RE.match(line) for line in body.split("\n"))


def chunk_summary_markdown(text: str) -> list[SummaryChunk]:
    """Chunk a summary markdown body into section-level pieces."""
    body = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not body.strip():
        return []
    if _is_timed_format(body):
        return _chunk_timed_markdown(body)

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
                start_sec=c.start_sec,
            )
            for i, c in enumerate(chunks)
        ]
    return chunks


def _chunk_timed_markdown(body: str) -> list[SummaryChunk]:
    lines = body.split("\n")
    stack: list[str] = []
    stack_starts: list[float | None] = []
    section_lines: list[str] = []
    section_start: float | None = None
    chunks: list[SummaryChunk] = []
    preamble: list[str] = []
    started = False

    def path_label() -> str:
        if not stack:
            return "全文"
        return " / ".join(stack)

    def flush() -> None:
        nonlocal section_lines
        content = "\n".join(section_lines).strip()
        section_lines = []
        if not content:
            return
        chunks.append(
            SummaryChunk(
                heading_path=path_label(),
                chunk_text=content,
                chunk_ord=len(chunks),
                start_sec=section_start,
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

        title_raw = match.group(2).strip()
        if not title_raw:
            if started:
                section_lines.append(line)
            else:
                preamble.append(line)
            continue

        if not started:
            quote_text = "\n".join(preamble).strip()
            if quote_text:
                chunks.append(
                    SummaryChunk(
                        heading_path="TL;DR",
                        chunk_text=quote_text,
                        chunk_ord=0,
                        start_sec=None,
                    )
                )
            started = True
            preamble = []
        else:
            flush()

        level = len(match.group(1))
        start_sec = parse_heading_start_sec(title_raw)
        title = _strip_time_prefix(title_raw)
        if level == 2:
            stack = [title]
            stack_starts = [start_sec]
            section_start = start_sec
        elif stack:
            stack = [stack[0], title]
            inherited = start_sec if start_sec is not None else stack_starts[0]
            stack_starts = [stack_starts[0], start_sec]
            section_start = inherited
        else:
            stack = [title]
            stack_starts = [start_sec]
            section_start = start_sec
        section_lines = [line]

    if started:
        flush()
    elif preamble:
        stripped = "\n".join(preamble).strip()
        if stripped:
            chunks.append(
                SummaryChunk(
                    heading_path="全文",
                    chunk_text=stripped,
                    chunk_ord=0,
                    start_sec=None,
                )
            )

    if not chunks:
        stripped = body.strip()
        if stripped:
            return [
                SummaryChunk(
                    heading_path="全文",
                    chunk_text=stripped,
                    chunk_ord=0,
                    start_sec=None,
                )
            ]
        return []
    return [
        SummaryChunk(
            heading_path=c.heading_path,
            chunk_text=c.chunk_text,
            chunk_ord=i,
            start_sec=c.start_sec,
        )
        for i, c in enumerate(chunks)
    ]


def window_transcript_segments(
    segments: list[dict],
    *,
    max_chars: int = _WINDOW_MAX_CHARS,
    max_span_sec: float = _WINDOW_MAX_SPAN_SEC,
    max_segments: int = _WINDOW_MAX_SEGMENTS,
) -> list[TranscriptWindow]:
    """Merge consecutive raw segments into FTS windows along boundaries.

    Keeps start=first.start, end=last.end; joins non-empty raw_text with spaces.
    Empty / whitespace-only segments are skipped for text but do not invent times.
    """
    items: list[tuple[float, float, str, str | None]] = []
    for raw in segments or []:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("raw_text") or raw.get("text") or "").strip()
        if not text:
            continue
        start = float(raw.get("start") or 0.0)
        end = float(raw.get("end") or start)
        if end < start:
            end = start
        source = raw.get("source")
        source_s = str(source) if source is not None else None
        items.append((start, end, text, source_s))

    if not items:
        return []

    windows: list[TranscriptWindow] = []
    buf_texts: list[str] = []
    buf_sources: list[str | None] = []
    win_start = items[0][0]
    win_end = items[0][1]
    char_count = 0
    seg_count = 0

    def flush() -> None:
        nonlocal buf_texts, buf_sources, char_count, seg_count
        if not buf_texts:
            return
        # Prefer non-null source if all same; else first non-null.
        sources = [s for s in buf_sources if s]
        subtitle_source: str | None = None
        if sources:
            if all(s == sources[0] for s in sources):
                subtitle_source = sources[0]
            else:
                subtitle_source = sources[0]
        windows.append(
            TranscriptWindow(
                start_sec=win_start,
                end_sec=win_end,
                chunk_text=" ".join(buf_texts),
                chunk_ord=len(windows),
                subtitle_source=subtitle_source,
            )
        )
        buf_texts = []
        buf_sources = []
        char_count = 0
        seg_count = 0

    for start, end, text, source in items:
        add_len = len(text) + (1 if buf_texts else 0)
        would_chars = char_count + add_len
        would_span = end - win_start if buf_texts else (end - start)
        would_segs = seg_count + 1

        if buf_texts and (
            would_chars > max_chars or would_span > max_span_sec or would_segs > max_segments
        ):
            flush()
            win_start = start
            win_end = end
            buf_texts = [text]
            buf_sources = [source]
            char_count = len(text)
            seg_count = 1
            continue

        if not buf_texts:
            win_start = start
        win_end = end
        buf_texts.append(text)
        buf_sources.append(source)
        char_count += add_len
        seg_count += 1

    flush()
    return windows
