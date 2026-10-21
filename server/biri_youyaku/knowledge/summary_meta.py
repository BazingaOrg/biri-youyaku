"""Extract list-card metadata from summary markdown (new and legacy formats)."""

from __future__ import annotations

import re

_TLDR_HEADING_RE = re.compile(r"^##\s+TL;DR\s*$", re.IGNORECASE)
_HEADING_RE = re.compile(r"^#{1,6}\s+")


def extract_tldr(markdown: str) -> str | None:
    """New format: first blockquote before any heading. Legacy: paragraph after ``## TL;DR``."""
    body = (markdown or "").replace("\r\n", "\n").replace("\r", "\n")
    quote = _first_quote_before_heading(body)
    if quote:
        return quote
    return _legacy_tldr_paragraph(body)


def _first_quote_before_heading(body: str) -> str | None:
    for line in body.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if _HEADING_RE.match(stripped):
            return None
        if stripped.startswith(">"):
            text = stripped.lstrip(">").strip()
            if text:
                return text
    return None


def _legacy_tldr_paragraph(body: str) -> str | None:
    lines = body.split("\n")
    in_section = False
    collected: list[str] = []
    for line in lines:
        stripped = line.strip()
        if _TLDR_HEADING_RE.match(stripped):
            in_section = True
            continue
        if not in_section:
            continue
        if stripped.startswith("## "):
            break
        if stripped:
            collected.append(stripped)
        elif collected:
            break
    if not collected:
        return None
    return " ".join(collected)
